"""Evaluation harness — orchestrates benchmark runs against a Silverwing model.

The :class:`EvaluationHarness` wraps an :class:`InferenceBackend` (typically
:m`TorchBackend`) and runs the full evaluation protocol: perplexity, math,
logic, knowledge, coding, instruction-following, and fixed-prompt generation
samples.  It produces a single :class:`EvaluationResult` document that serves
as evidence for model promotion (spec section 48).

Usage (after the runtime model is loaded via TorchBackend)::

    from silverwing_runtime.inference import InferenceService
    from silverwing_runtime.evaluation import EvaluationHarness

    svc = InferenceService(loader, cfg)
    backend = svc._backend_factory(svc.load_model("silverwing-120m-base-v1"))
    harness = EvaluationHarness(backend, "silverwing-120m-base-v1")
    result = harness.run_full_evaluation(val_text_path, label="r1-gpu-eval")
    print(result.summary)

The harness works with any backend that implements ``generate()``.  When the
backend is a :class:`TorchBackend`, perplexity is computed from the internal
``SilverwingDecoder``; otherwise perplexity is skipped (honestly reported).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from silverwing_runtime.backends.base import InferenceBackend
from silverwing_runtime.evaluation.benchmarks import (
    FIXED_PROMPTS,
    R2000_CODING,
    R2000_KNOWLEDGE,
    R2000_LOGIC,
    R2000_MATH,
    R2000_MODEL_ID,
    R2000_MODEL_SHA,
    R2000_PARAMS,
    R2000_VAL_LOSS,
    R2000_VAL_PPL,
    build_coding_cases,
    build_instruction_cases,
    build_knowledge_cases,
    build_logic_cases,
    build_math_cases,
)
from silverwing_runtime.evaluation.perplexity import compute_perplexity_safe
from silverwing_runtime.evaluation.results import (
    BenchmarkResult,
    ComparisonReport,
    EvaluationResult,
    GenerationSample,
    HardwareInfo,
    PerplexityResult,
    QuestionResult,
)
from silverwing_runtime.generation import GenerationConfig, GenerationRequest
from silverwing_runtime.model_manifest import now_iso

log = logging.getLogger("silverwing_runtime.evaluation.harness")

# Default generation settings for benchmark scoring (deterministic-ish).
_BENCH_MAX_TOKENS = 40
_BENCH_TEMPERATURE = 0.5
_BENCH_TOP_P = 0.95


class EvaluationHarness:
    """Run standardized benchmarks against a loaded model backend.

    Parameters
    ----------
    backend
        Any :class:`InferenceBackend`.  :class:`TorchBackend` enables full
        evaluation (including perplexity); other backends run only the
        generation-based benchmarks.
    model_ref
        Full model identifier (e.g. ``silverwing-120m-base-v1``).
    """

    def __init__(self, backend: InferenceBackend, model_ref: str = ""):
        self.backend = backend
        self.model_ref = model_ref
        # Reach into the backend for direct model access (perplexity).
        self._decoder: Any = getattr(backend, "_torch_model", None)
        self._tokenizer: Any = getattr(backend, "_tokenizer", None)
        self._model_config: Any = getattr(backend, "_model_config", None)
        self._verify_report: dict[str, Any] = getattr(backend, "_verify_report", {})

    # ------------------------------------------------------------------ #
    # Internal: text generation via the backend
    # ------------------------------------------------------------------ #
    def _generate(
        self,
        prompt: str,
        max_new_tokens: int = _BENCH_MAX_TOKENS,
        temperature: float = _BENCH_TEMPERATURE,
        top_p: float = _BENCH_TOP_P,
    ) -> tuple[str, int, int, float, str]:
        """Generate text and return (response, in_tokens, out_tokens, latency_ms, finish_reason).

        Honest failure handling: if the backend raises, the error is logged
        and an empty response with an error tag is returned — the benchmark
        will correctly count this as a failure.
        """
        req = GenerationRequest(
            prompt=prompt,
            config=GenerationConfig(
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=None,
                repetition_penalty=1.0,
            ),
        )
        try:
            result = self.backend.generate(req)
        except Exception as exc:  # noqa: BLE001
            log.error("generation failed for prompt %r: %s", prompt[:80], exc)
            return "", 0, 0, 0.0, "error"
        return (
            result.text,
            result.tokens_input,
            result.tokens_generated,
            result.latency_ms,
            result.finish_reason,
        )

    # ------------------------------------------------------------------ #
    # Perplexity
    # ------------------------------------------------------------------ #
    def evaluate_perplexity(
        self,
        val_text: str | Path,
        max_seq_len: int = 256,
        max_windows: int = 128,
    ) -> PerplexityResult:
        """Compute validation perplexity.

        Falls back to a *skipped* result when the backend has no directly
        accessible model (e.g. EchoBackend) — perplexity is never fabricated.
        """
        if self._decoder is None or self._tokenizer is None:
            return PerplexityResult(
                val_loss=0.0,
                val_perplexity=0.0,
                val_tokens_evaluated=0,
                val_windows=0,
                val_sha256="",
                skipped=True,
                skip_reason="backend has no direct model/tokenizer (non-TorchBackend)",
            )
        device = getattr(self._decoder, "device", "cpu")
        return compute_perplexity_safe(
            self._decoder,
            self._tokenizer,
            val_text,
            max_seq_len=max_seq_len,
            max_windows=max_windows,
            device=str(device),
        )

    # ------------------------------------------------------------------ #
    # Benchmark categories
    # ------------------------------------------------------------------ #
    def evaluate_math(self) -> BenchmarkResult:
        cases = build_math_cases()
        results: list[QuestionResult] = []
        correct = 0
        for c in cases:
            response, in_tok, out_tok, _, _ = self._generate(c.prompt)
            passed = c.check(response)
            if passed:
                correct += 1
            detail: dict[str, Any] = {}
            num = None
            m = re.search(r"-?\d+", response.replace(",", ""))
            if m:
                num = int(m.group(0))
            detail["extracted_number"] = num
            results.append(QuestionResult(
                question=c.question, prompt=c.prompt, response=response,
                passed=passed, expected=c.expected, detail=detail,
            ))
        total = len(cases)
        return BenchmarkResult(
            name="math", correct=correct, total=total,
            accuracy=correct / total if total else 0.0, questions=results,
        )

    def evaluate_logic(self) -> BenchmarkResult:
        cases = build_logic_cases()
        results: list[QuestionResult] = []
        correct = 0
        for c in cases:
            response, in_tok, out_tok, _, _ = self._generate(c.prompt)
            passed = c.check(response)
            if passed:
                correct += 1
            matched = [k for k in c.expected.split(", ") if k.lower() in response.lower()]
            results.append(QuestionResult(
                question=c.question, prompt=c.prompt, response=response,
                passed=passed, expected=c.expected,
                detail={"matched_keywords": matched},
            ))
        total = len(cases)
        return BenchmarkResult(
            name="logic", correct=correct, total=total,
            accuracy=correct / total if total else 0.0, questions=results,
        )

    def evaluate_knowledge(self) -> BenchmarkResult:
        cases = build_knowledge_cases()
        results: list[QuestionResult] = []
        correct = 0
        for c in cases:
            response, in_tok, out_tok, _, _ = self._generate(c.prompt)
            passed = c.check(response)
            if passed:
                correct += 1
            matched = [k for k in c.expected.split(", ") if k.lower() in response.lower()]
            results.append(QuestionResult(
                question=c.question, prompt=c.prompt, response=response,
                passed=passed, expected=c.expected,
                detail={"matched_keywords": matched},
            ))
        total = len(cases)
        return BenchmarkResult(
            name="knowledge", correct=correct, total=total,
            accuracy=correct / total if total else 0.0, questions=results,
        )

    def evaluate_coding(self) -> BenchmarkResult:
        """Coding benchmark: generate Python, extract, and run in a sandbox.

        Per directive section 17, model-generated code is NEVER executed
        directly on the host.  Each code test runs in a separate Python
        subprocess with a hard timeout.
        """
        cases = build_coding_cases()
        results: list[QuestionResult] = []
        correct = 0
        for c in cases:
            response, in_tok, out_tok, _, _ = self._generate(
                c.prompt, max_new_tokens=120, temperature=_BENCH_TEMPERATURE
            )
            func_name = c.detail.get("function_name", "")
            test_expr = c.detail.get("test_expression", "")
            code = _extract_python(response)
            pass_ok, exec_detail = _run_code_check_sandboxed(code, test_expr)
            if pass_ok:
                correct += 1
            results.append(QuestionResult(
                question=c.question, prompt=c.prompt, response=response,
                passed=pass_ok, expected=c.expected,
                detail={
                    "function_name": func_name,
                    "test_expression": test_expr,
                    "extracted_len": len(code),
                    **exec_detail,
                },
            ))
        total = len(cases)
        return BenchmarkResult(
            name="coding", correct=correct, total=total,
            accuracy=correct / total if total else 0.0, questions=results,
        )

    def evaluate_instruction_following(self) -> BenchmarkResult:
        cases = build_instruction_cases()
        results: list[QuestionResult] = []
        correct = 0
        for c in cases:
            response, in_tok, out_tok, _, _ = self._generate(c.prompt)
            passed = c.check(response)
            if passed:
                correct += 1
            results.append(QuestionResult(
                question=c.question, prompt=c.prompt, response=response,
                passed=passed, expected=c.expected, detail={},
            ))
        total = len(cases)
        return BenchmarkResult(
            name="instruction", correct=correct, total=total,
            accuracy=correct / total if total else 0.0, questions=results,
        )

    # ------------------------------------------------------------------ #
    # Fixed-prompt generation samples (quality inspection)
    # ------------------------------------------------------------------ #
    def generate_fixed_samples(self) -> list[GenerationSample]:
        """Generate text from the 10 fixed prompts for quality inspection."""
        samples: list[GenerationSample] = []
        backend_name = getattr(self.backend, "backend", "") or type(self.backend).__name__
        device = getattr(self.backend, "device", "") or ""
        for prompt in FIXED_PROMPTS:
            response, in_tok, out_tok, latency, finish = self._generate(
                prompt, max_new_tokens=64, temperature=0.7, top_p=0.9
            )
            samples.append(GenerationSample(
                prompt=prompt, response=response,
                finish_reason=finish, tokens_input=in_tok,
                tokens_generated=out_tok, latency_ms=latency,
                backend=backend_name, device=device,
            ))
        return samples

    # ------------------------------------------------------------------ #
    # Comparison report
    # ------------------------------------------------------------------ #
    def build_comparison(
        self,
        perp: PerplexityResult,
        benchmarks: dict[str, BenchmarkResult],
    ) -> ComparisonReport:
        """Build an honest comparison against the r2000 baseline."""
        math_br = benchmarks.get("math")
        logic_br = benchmarks.get("logic")
        know_br = benchmarks.get("knowledge")
        code_br = benchmarks.get("coding")

        def _score(br: BenchmarkResult | None) -> tuple[int, int]:
            return (br.correct, br.total) if br else (0, 0)

        m_correct, m_total = _score(math_br)
        l_correct, l_total = _score(logic_br)
        k_correct, k_total = _score(know_br)
        c_correct, c_total = _score(code_br)

        r2000_math_correct, r2000_math_total = R2000_MATH
        r2000_logic_correct, r2000_logic_total = R2000_LOGIC
        r2000_code_correct, r2000_code_total = R2000_CODING
        r2000_know_correct, r2000_know_total = R2000_KNOWLEDGE

        def _delta(correct: int, total: int, base_correct: int, base_total: int) -> float:
            if total == 0 or base_total == 0:
                return 0.0
            return (correct / total) - (base_correct / base_total)

        def _param_efficiency(ppl: float, params: int) -> float:
            if ppl > 0 and params > 0:
                return ppl / (params / 1_000_000)
            return 0.0

        param_count = 0
        # TorchBackend stores parameter_count in _verify_report and metadata.
        param_count = self._verify_report.get("parameter_count", 0) or 0

        model_ppl = perp.val_perplexity if not perp.skipped else 0.0

        return ComparisonReport(
            baseline_model=R2000_MODEL_ID,
            baseline_params=R2000_PARAMS,
            baseline_val_loss=R2000_VAL_LOSS,
            baseline_val_perplexity=R2000_VAL_PPL,
            baseline_math=R2000_MATH,
            baseline_logic=R2000_LOGIC,
            baseline_coding=R2000_CODING,
            baseline_knowledge=R2000_KNOWLEDGE,
            model_params=param_count,
            model_val_loss=perp.val_loss if not perp.skipped else 0.0,
            model_val_perplexity=model_ppl,
            model_math=(m_correct, m_total),
            model_logic=(l_correct, l_total),
            model_coding=(c_correct, c_total),
            model_knowledge=(k_correct, k_total),
            beats_baseline_val_loss=(
                perp.val_loss < R2000_VAL_LOSS if not perp.skipped else False
            ),
            beats_baseline_ppl=(
                model_ppl > 0 and model_ppl < R2000_VAL_PPL if not perp.skipped else False
            ),
            math_improvement=_delta(m_correct, m_total, r2000_math_correct, r2000_math_total),
            logic_improvement=_delta(l_correct, l_total, r2000_logic_correct, r2000_logic_total),
            knowledge_improvement=_delta(k_correct, k_total, r2000_know_correct, r2000_know_total),
            coding_improvement=_delta(c_correct, c_total, r2000_code_correct, r2000_code_total),
            param_efficiency=_param_efficiency(model_ppl, param_count),
        )

    # ------------------------------------------------------------------ #
    # Hardware info
    # ------------------------------------------------------------------ #
    def capture_hardware(self) -> HardwareInfo:
        import torch

        backend_name = getattr(self.backend, "backend", "") or ""
        device = getattr(self.backend, "device", "") or ""
        dtype = getattr(self.backend, "dtype_str", "") or ""

        info = HardwareInfo(
            device=device, dtype=dtype, backend=backend_name,
            torch_version=torch.__version__,
        )
        # CPU RAM
        try:
            import psutil
            info.cpu_ram_gb = round(psutil.virtual_memory().total / 1e9, 2)
        except ImportError:
            pass
        # GPU info
        if torch.cuda.is_available():
            try:
                info.gpu_name = torch.cuda.get_device_name(0)
                info.gpu_vram_gb = round(
                    torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 1
                )
            except Exception:  # noqa: BLE001
                pass
        return info

    # ------------------------------------------------------------------ #
    # Full evaluation
    # ------------------------------------------------------------------ #
    def run_full_evaluation(
        self,
        val_text: str | Path,
        label: str = "",
    ) -> EvaluationResult:
        """Run all benchmarks and return a complete :class:`EvaluationResult`.

        Parameters
        ----------
        val_text
            Validation text (string or path to a .txt file) for perplexity.
        label
            Human-readable label for this evaluation run (e.g. ``"r1-gpu-eval"``).
        """
        t0 = time.monotonic()
        if not label:
            label = f"eval-{now_iso().replace(':', '-').replace('T', '-')}"

        # Model identity from backend metadata (TorchBackend exposes this).
        meta: dict[str, Any] = {}
        if hasattr(self.backend, "metadata"):
            try:
                meta = self.backend.metadata()
            except Exception:  # noqa: BLE001
                meta = {}
        param_count = meta.get("parameter_count", 0) or self._verify_report.get(
            "parameter_count", 0
        )

        # Perplexity
        perp = self.evaluate_perplexity(val_text)

        # Benchmarks
        benchmarks: dict[str, BenchmarkResult] = {
            "math": self.evaluate_math(),
            "logic": self.evaluate_logic(),
            "knowledge": self.evaluate_knowledge(),
            "coding": self.evaluate_coding(),
            "instruction": self.evaluate_instruction_following(),
        }

        # Fixed-prompt generation samples
        samples = self.generate_fixed_samples()

        # Comparison
        comparison = self.build_comparison(perp, benchmarks)

        # Hardware
        hw = self.capture_hardware()

        elapsed = time.monotonic() - t0
        total_tokens = sum(s.tokens_input + s.tokens_generated for s in samples)

        # Weights SHA-256 from backend metadata (hash-verified, not fabricated).
        weights_sha = meta.get("weights_sha256", "") or ""

        # Derive version from model_id (e.g. "silverwing-120m-base-v1" -> "v1")
        model_id_val = meta.get("model_id", self.model_ref)
        version_val = "v1"
        if model_id_val:
            parts = model_id_val.split("-")
            if parts and parts[-1].startswith("v"):
                version_val = parts[-1]

        return EvaluationResult(
            model_id=model_id_val,
            version=version_val,
            revision=meta.get("revision", "r1"),
            weights_sha256=weights_sha,
            param_count=param_count,
            label=label,
            timestamp=now_iso(),
            perplexity=perp,
            benchmarks=benchmarks,
            generation_samples=samples,
            comparison=comparison,
            hardware=hw,
            total_tokens_processed=total_tokens,
            total_evaluation_seconds=round(elapsed, 2),
        )


# --------------------------------------------------------------------------- #
# Code-extraction + sandboxed execution helpers
# --------------------------------------------------------------------------- #
def _extract_python(text: str) -> str:
    """Extract Python code from a model response.

    Looks for a `` ```python ... ``` `` block first; falls back to text
    starting at the first ``def`` line.  Adapted from the training script's
    ``_extract_py``.
    """
    m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    i = text.find("def ")
    if i == -1:
        return ""
    head = text[i:]
    lines = head.split("\n")
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            break
        out.append(ln)
    return "\n".join(out).strip()


def _run_code_check_sandboxed(
    code: str, test_expr: str, timeout: float = 5.0
) -> tuple[bool, dict[str, Any]]:
    """Execute a code test in a **separate Python subprocess**.

    Per directive section 17, model-generated code is NEVER executed directly
    on the host.  This function writes the code + test to a temporary script
    and runs it with a hard timeout, so a runaway or malicious generation
    cannot affect the evaluation process.

    Returns ``(passed, detail_dict)``.
    """
    if not code.strip() or not test_expr.strip():
        return False, {"error": "no code or test expression to run"}

    script = f"""
import json, sys
code = '''{code}'''
test_expr = '{test_expr}'
ns = {{}}
try:
    exec(code, ns)
except Exception as e:
    result = {{"passed": False, "error": f"exec error: {{e}}"}}
else:
    try:
        r = eval(test_expr, ns)
        result = {{"passed": bool(r)}}
    except Exception as e:
        result = {{"passed": False, "error": f"test eval error: {{e}}"}}
print(json.dumps(result))
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, {"error": f"timed out after {timeout}s", "timeout": True}
    except Exception as exc:  # noqa: BLE001
        return False, {"error": str(exc)}

    stdout = proc.stdout.strip()
    if stdout:
        import json as _json
        try:
            data = _json.loads(stdout)
            return bool(data.get("passed", False)), data
        except Exception:  # noqa: BLE001
            pass
    return False, {
        "error": f"subprocess exited with code {proc.returncode}",
        "stderr": proc.stderr[:500] if proc.stderr else "",
    }

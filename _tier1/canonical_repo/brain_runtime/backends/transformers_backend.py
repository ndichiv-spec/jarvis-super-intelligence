"""Real Qwen3-4B backend via Hugging Face ``transformers``.

This is the production inference path for the JARVIS Brain runtime.  It loads
the Qwen3-4B Base or SFT checkpoint from its Hugging Face repository (selected
by ``JARVIS_BRAIN_MODEL``) and serves OpenAI-compatible chat completions.

Weights are NEVER stored in the source tree (spec section 7): the model is
fetched from the durable HF repository through the cache at
``JARVIS_BRAIN_MODEL_CACHE``.  The local JARVIS PC (8 GB RAM, no GPU, no cached
Qwen3-4B shards) cannot satisfy this loader — on such a host the server must be
started in explicit ``stub`` mode instead; this backend never silently degrades.

Heavy imports (``torch`` / ``transformers``) are lazy so that simply importing
this module (and thus collecting / running the test suite) stays cheap.
"""

from __future__ import annotations

import os
import time

from brain_runtime.backends.base import BrainBackend
from brain_runtime.generation import BrainGenerationConfig, BrainResult
from brain_runtime.model_registry import BrainCatalog


class TransformersBackend(BrainBackend):
    """Qwen3-4B inference backed by ``transformers.AutoModelForCausalLM``."""

    def __init__(
        self,
        model_catalog: BrainCatalog | None = None,
        model_id: str = "",
        device: str = "auto",
        model_cache: str = "",
        local_files_only: bool = False,
    ) -> None:
        self._catalog = model_catalog or BrainCatalog()
        self._requested_model_id = model_id
        self.device = device
        self._model_cache = model_cache
        self._local_files_only = local_files_only
        self.backend = "transformers"
        self.parameters = 0
        self.revision = ""
        self.tokenizer = None
        self.model = None

    # ------------------------------------------------------------------ #
    def _resolve(self) -> str:
        """Return the HF repository id for the configured Brain model."""
        entry = self._catalog.lookup(self._requested_model_id) or self._catalog.lookup(
            os.environ.get("JARVIS_BRAIN_MODEL")
        )
        if entry is None:
            raise RuntimeError(
                f"JARVIS_BRAIN_MODEL={self._requested_model_id!r} is not a known "
                "JARVIS Brain model id (jarvis-brain-qwen3-4b-v1 / -sft-v1)."
            )
        self.model_id = entry.full_id
        self.revision = entry.revision or "main"
        self.parameters = entry.parameter_count
        return entry.repository

    def load(self) -> None:
        """Download/acquire the tokenizer + weights (raises on resource failure)."""
        import torch  # noqa: WPS433 - lazy: heavy + CPU-only host may lack it
        from transformers import AutoModelForCausalLM, AutoTokenizer

        repo = self._resolve()
        cache = self._model_cache or None

        # Honest device selection. On CPU-only hosts torch has no CUDA; we stay
        # on CPU (Qwen3-4B will not fit in ~8 GB RAM, so load() will raise and
        # the runtime reports offline rather than fabricating output).
        if self.device in ("auto", ""):
            self.device = "cuda" if (torch.cuda.is_available() and device_count() > 0) else "cpu"
        torch_dtype = torch.bfloat16 if self.device == "cuda" else torch.float32

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                repo, revision=self.revision or None, cache_dir=cache,
                use_fast=True, local_files_only=self._local_files_only,
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                repo,
                revision=self.revision or None,
                cache_dir=cache,
                torch_dtype=torch_dtype,
                device_map=self.device,
                trust_remote_code=False,
                local_files_only=self._local_files_only,
            )
        except Exception as exc:
            # Release partial state so the runtime can report offline cleanly.
            self.close()
            raise RuntimeError(
                f"Could not load JARVIS Brain model {repo!r} on {self.device}: "
                f"{type(exc).__name__}"
            ) from exc

        self.loaded = True

    def warmup(self, prompt: str) -> str:
        cfg = BrainGenerationConfig(model=self.model_id, max_tokens=16, temperature=0.0)
        result = self.generate([{"role": "user", "content": prompt}], cfg)
        return result.text

    def generate(self, messages: list[dict], configuration: BrainGenerationConfig) -> BrainResult:
        if not self.loaded:
            raise RuntimeError("Brain backend is not loaded")
        # Qwen3 ships a chat template in its tokenizer.
        if getattr(self.tokenizer, "chat_template", None) is not None:
            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            text = "".join(f"<|{m.get('role','user')}>\n{m.get('content','')}" for m in messages)
        inputs = self.tokenizer(text, return_tensors="pt")
        device = next(self.model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        import torch  # noqa: WPS433
        max_new = min(int(configuration.max_tokens), 8192)
        start = time.time()
        with torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new,
                temperature=configuration.temperature,
                top_p=configuration.top_p,
                do_sample=configuration.temperature > 0,
            )
        text_out = self.tokenizer.decode(output_ids[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
        latency_ms = round((time.time() - start) * 1000, 2)
        in_tokens = int(inputs["input_ids"].shape[-1])
        out_tokens = int(output_ids.shape[-1] - inputs["input_ids"].shape[-1])
        return BrainResult(
            text=text_out,
            model=self.model_id,
            revision=self.revision,
            finish_reason="stop",
            tokens_input=in_tokens,
            tokens_generated=out_tokens,
            latency_ms=latency_ms,
            device=self.device,
            backend=self.backend,
        )

    def close(self) -> None:
        self.tokenizer = None
        self.model = None
        self.loaded = False

    def __del__(self) -> None:  # pragma: no cover - best effort
        try:
            self.close()
        except Exception:
            pass


def device_count() -> int:
    """Number of available CUDA devices (lazy torch import)."""
    try:
        import torch  # noqa: WPS433
        return int(torch.cuda.device_count())
    except Exception:
        return 0

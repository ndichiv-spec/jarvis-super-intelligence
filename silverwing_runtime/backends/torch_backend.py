"""TorchBackend — real Silverwing inference via torch + safetensors.

Production default (``SILVERWING_BACKEND=torch``).  Loads the actual trained
checkpoint through the runtime's registry/storage abstraction, verifies the
tokenizer and weights, validates the architecture parameter count, performs a
strict checkpoint load (with the controlled compatibility step for
independently-serialized tied embeddings), then serves autoregressive
generation with a KV cache.

If the backend cannot load it reports ``unhealthy`` and surfaces the real
error; it NEVER silently falls back to EchoBackend (section 16).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import torch

from silverwing_runtime.backends.architecture import (
    ArchitectureError,
    ModelConfig,
    SilverwingDecoder,
    build_silverwing,
    count_parameters,
)
from silverwing_runtime.backends.base import InferenceBackend
from silverwing_runtime.backends.tokenizer import (
    SilverwingTokenizer,
    tokenizer_assets,
)
from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.generation import (
    GenerationConfig,
    GenerationRequest,
    GenerationResult,
)
from silverwing_runtime.hashutil import HashVerificationError
from silverwing_runtime.model_loader import LoadedModel

log = logging.getLogger("silverwing_runtime.torch_backend")


class TorchBackendError(RuntimeError):
    pass


class TorchBackend(InferenceBackend):
    """In-memory, single-load torch backend.  Model is loaded once and reused."""

    backend = "torch"

    def __init__(self, model: LoadedModel, config: RuntimeConfig):
        self.model = model
        self.config = config
        self.device = ""
        self.dtype_str = ""
        self._torch_model: SilverwingDecoder | None = None
        self._dtype: Any = None
        self._model_config: ModelConfig | None = None
        self._tokenizer: SilverwingTokenizer | None = None
        self._verify_report: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Loading pipeline (section 9)
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        from safetensors.torch import load_file

        manifest = self.model.entry
        asset_dir = self.model.asset_dir
        start = time.monotonic()

        # 1) Model configuration from the registered artifact (not the repo).
        config_path = asset_dir / "config.json"
        if not config_path.exists():
            raise TorchBackendError(
                f"config.json missing from model assets {asset_dir}"
            )
        try:
            mcfg = ModelConfig.from_json(config_path)
        except Exception as exc:
            raise TorchBackendError(f"invalid model config {config_path}: {exc}") from exc
        if manifest.config_sha256:
            from silverwing_runtime.hashutil import sha256_file

            actual = sha256_file(config_path)
            if actual.lower() != manifest.config_sha256.lower():
                raise HashVerificationError(
                    "config.json SHA-256 mismatch "
                    f"(expected {manifest.config_sha256}, got {actual})"
                )

        # 2) Tokenizer: the exact asset paired with the checkpoint.
        tok = tokenizer_assets(asset_dir, manifest.tokenizer_sha256)
        if tok.vocab_size != mcfg.vocab_size:
            raise TorchBackendError(
                "tokenizer mismatch: tokenizer vocab "
                f"{tok.vocab_size} != model vocab {mcfg.vocab_size} "
                f"(model {manifest.full_id})"
            )

        # 3) Build the architecture and force-validate parameters (section 5).
        try:
            decoder = build_silverwing(mcfg)
        except ArchitectureError as exc:
            raise TorchBackendError(f"architecture mismatch: {exc}") from exc
        actual_params = count_parameters(decoder)
        if manifest.parameter_count and actual_params != manifest.parameter_count:
            raise TorchBackendError(
                "architecture mismatch: constructed parameter count "
                f"{actual_params} != registered {manifest.parameter_count} "
                f"(model {manifest.full_id})"
            )

        # 4) Device + dtype (section 8).  CPU is reported as CPU, never GPU.
        device, dtype = self._resolve_device(self.config.device)
        self.device = device
        self._dtype = dtype
        self.dtype_str = {
            torch.float32: "fp32",
            torch.float16: "fp16",
            torch.bfloat16: "bf16",
        }.get(dtype, str(dtype))

        # 5) Strict checkpoint load with controlled tie-compatibility.
        weights = asset_dir / "model.safetensors"
        if not weights.exists():
            raise TorchBackendError(f"weights missing from model assets {weights}")
        state = load_file(str(weights), device="cpu")
        missing, unexpected, tied_ok = self._load_state_dict_compat(decoder, state)
        if missing or unexpected or not tied_ok:
            raise TorchBackendError(
                "checkpoint validation failed "
                f"missing={missing} unexpected={unexpected} tied_equal={tied_ok}"
            )

        decoder.to(dtype).to(device)
        decoder.eval()
        self._torch_model = decoder
        self._model_config = mcfg
        self._tokenizer = tok
        self._verify_report = {
            "member": manifest.full_id,
            "revision": manifest.revision,
            "model_id": manifest.model_id,
            "parameter_count": actual_params,
            "parameter_verified": actual_params == manifest.parameter_count,
            "weights_sha256": self.model.sha256_verified_str,
            "tokenizer_sha256": tok.sha256,
            "config_sha256": manifest.config_sha256 or "",
            "missing_keys": missing,
            "unexpected_keys": unexpected,
            "load_ms": round((time.monotonic() - start) * 1000, 2),
        }
        log.info(
            "torch backend loaded %s params=%d device=%s dtype=%s in %.1fs",
            manifest.full_id,
            actual_params,
            self.device,
            self.dtype_str,
            (time.monotonic() - start),
        )

    @staticmethod
    def _load_state_dict_compat(
        decoder: SilverwingDecoder, state: dict[str, Any]
    ) -> tuple[list[str], list[str], bool]:
        """Load checkpoint with strict validation.

        Tied embeddings are serialized independently in the checkpoint, so we
        run a CONTROLLED compatibility step: load with ``strict=False`` then
        explicitly verify ``lm_head.weight == embed_tokens.weight``.  Nothing
        is silently ignored.
        """
        loaded = decoder.load_state_dict(state, strict=False)
        missing = list(loaded.missing_keys)
        unexpected = list(loaded.unexpected_keys)
        if not missing and not unexpected:
            tied_ok = torch.allclose(
                state["lm_head.weight"], state["embed_tokens.weight"]
            )
            return missing, unexpected, bool(tied_ok)
        return missing, unexpected, False

    @staticmethod
    def _resolve_device(hint: str) -> tuple[str, Any]:
        if hint in ("cuda", "cuda:0"):
            if not torch.cuda.is_available():
                raise TorchBackendError(
                    "device 'cuda' requested but CUDA is not available"
                )
            device = "cuda"
        elif hint in ("", "auto"):
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = hint
        if device.startswith("cuda"):
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        else:
            dtype = torch.float32
        return device, dtype

    def unload(self) -> None:
        self._torch_model = None
        if self.device.startswith("cuda"):
            torch.cuda.empty_cache()

    def close(self) -> None:
        self.unload()

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def _encode_prompt(self, prompt: str) -> list[int]:
        ids = self._tokenizer.encode(prompt)
        bos = self._model_config.bos_token_id
        return ([bos] + ids) if bos is not None else list(ids)

    def _seed_kv(
        self, input_ids: list[int]
    ) -> tuple[list[tuple[Any, Any]], Any, int]:
        model = self._torch_model
        assert model is not None
        kvc: list[tuple[Any, Any]] = [(None, None)] * model.config.n_layers
        logits = None
        for pos, tok in enumerate(input_ids):
            logits, kvc = model.step(
                torch.tensor([tok], device=model.device, dtype=torch.long), kvc, pos
            )
        return kvc, logits, len(input_ids)

    def _decode(
        self,
        input_ids: list[int],
        gen_cfg: GenerationConfig,
    ) -> tuple[list[int], str, list[Any]]:
        model = self._torch_model
        assert model is not None
        ctx = model.config.max_position_embeddings
        if len(input_ids) >= ctx:
            raise TorchBackendError(
                f"prompt of {len(input_ids)} tokens exceeds model context {ctx}"
            )
        max_new = gen_cfg.max_new_tokens
        budget = ctx - len(input_ids)
        max_new = min(max_new, budget)

        kvc, last_logits, pos = self._seed_kv(input_ids)
        if last_logits is None:
            raise TorchBackendError("empty prompt produced no logits")
        seen = set(input_ids)
        generated: list[int] = []
        finish = "length"
        for _ in range(max_new):
            nxt = self._sample_next(last_logits, gen_cfg, seen)
            if nxt == model.config.eos_token_id:
                finish = "stop"
                break
            generated.append(nxt)
            seen.add(nxt)
            last_logits, kvc = model.step(
                torch.tensor([nxt], device=model.device, dtype=torch.long), kvc, pos
            )
            pos += 1
        return generated, finish, kvc

    @staticmethod
    def _sample_next(
        logits: Any,
        cfg: GenerationConfig,
        seen: set[int],
    ) -> int:
        logits = logits.float().reshape(-1).clone()
        rp = cfg.repetition_penalty
        if rp != 1.0 and seen:
            for tid in list(seen):
                logits[tid] /= rp
        if cfg.temperature <= 1e-6:
            return int(torch.argmax(logits).item())
        logits = logits / cfg.temperature
        if cfg.top_k and cfg.top_k > 0:
            k = min(cfg.top_k, logits.numel())
            kth = torch.topk(logits, k).values[-1]
            logits = torch.where(logits < kth, torch.tensor(float("-inf"), device=logits.device), logits)
        if cfg.top_p is not None and 0.0 < cfg.top_p < 1.0:
            sorted_l, sorted_i = torch.sort(logits, descending=True, stable=True)
            cum = torch.cumsum(torch.softmax(sorted_l, dim=-1), dim=-1)
            cutoff = cum - torch.softmax(sorted_l, dim=-1) > cfg.top_p
            sorted_l = torch.where(cutoff, torch.tensor(float("-inf"), device=logits.device), sorted_l)
            logits = logits.scatter(0, sorted_i, sorted_l)
        probs = torch.softmax(logits, dim=-1)
        if torch.any(torch.isnan(probs)):
            return int(torch.argmax(logits).item())
        return int(torch.multinomial(probs, num_samples=1).item())

    # ------------------------------------------------------------------ #
    # Backend API
    # ------------------------------------------------------------------ #
    def warmup(self, prompt: str) -> str:
        """Run one short verified generation before reporting healthy."""
        assert self._torch_model is not None
        ids = self._encode_prompt(prompt)
        # Validate: full forward finite + KV path agrees with full forward.
        self._verify_logits(ids)
        gen_cfg = GenerationConfig(max_new_tokens=4, temperature=0.0)
        generated, finish, _ = self._decode(ids, gen_cfg)
        text = self._tokenizer.decode(generated)
        if finish not in ("stop", "length") or not generated:
            raise TorchBackendError(f"warmup generation invalid ({finish=})")
        return text or "warmup-ok"

    def _verify_logits(self, ids: list[int]) -> None:
        model = self._torch_model
        assert model is not None

        input_t = torch.tensor([ids], device=model.device, dtype=torch.long)
        full = model.full_forward(input_t)
        if not bool(torch.isfinite(full).all()):
            raise TorchBackendError("warmup: full forward logits contain NaN/Inf")
        _kvc, last_logits, _ = self._seed_kv(ids)
        if not bool(torch.isfinite(last_logits).all()):
            raise TorchBackendError("warmup: KV path logits contain NaN/Inf")
        last_full = full[0, -1, :]
        if bool(torch.argmax(last_logits) != torch.argmax(last_full)):
            raise TorchBackendError(
                "warmup: KV cache diverges from full forward (logits disagree)"
            )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if self._torch_model is None or self._tokenizer is None:
            raise TorchBackendError("torch backend is not loaded")
        cfg = request.config or GenerationConfig()
        start = time.monotonic()
        try:
            input_ids = self._encode_prompt(request.prompt)
            tokens_input = len(input_ids)
            generated, finish, _ = self._decode(input_ids, cfg)
        except TorchBackendError:
            raise
        except RuntimeError as exc:
            text = str(exc).lower()
            if "out of memory" in text or "cuda oom" in text:
                raise TorchBackendError("CUDA out of memory") from exc
            raise TorchBackendError(f"generation failed: {exc}") from exc

        out_text = self._tokenizer.decode(generated)
        return GenerationResult(
            text=out_text,
            finish_reason=finish,
            tokens_input=tokens_input,
            tokens_generated=len(generated),
            latency_ms=round((time.monotonic() - start) * 1000, 2),
            metadata=self._response_metadata(backend="torch"),
        )

    def metadata(self) -> dict[str, Any]:
        entry = self.model.entry
        m = self._model_config
        return {
            "model_id": entry.model_id,
            "revision": entry.revision,
            "architecture": entry.architecture,
            "parameter_count": count_parameters(self._torch_model) if self._torch_model else 0,
            "parameter_verified": bool(self._verify_report.get("parameter_verified")),
            "context_length": m.max_position_embeddings if m else entry.context_length,
            "vocab_size": m.vocab_size if m else entry.vocab_size,
            "tokenizer_version": entry.tokenizer_version,
            "tokenizer_sha256": self._tokenizer.sha256 if self._tokenizer else "",
            "weights_sha256": entry.model_sha256,
            "device": self.device,
            "dtype": self.dtype_str or "",
            "backend": self.backend,
            "loaded": self._torch_model is not None,
        }

    def _response_metadata(self, backend: str) -> dict[str, Any]:
        return {
            "backend": backend,
            "device": self.device,
            "dtype": self.dtype_str or "",
            "model_label": "Silverwing-120M-Base",
            "weights_sha256_verified": self.model.sha256_verified_str,
            "tokenizer_sha256": self._tokenizer.sha256 if self._tokenizer else "",
        }

    @property
    def status_fields(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "backend": self.backend,
            "dtype": self.dtype_str or "",
        }
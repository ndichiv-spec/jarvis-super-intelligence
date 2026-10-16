"""Perplexity evaluation for the Silverwing model.

Computes validation cross-entropy loss and perplexity by running the model's
``full_forward`` over contiguous windows of a validation text.  This mirrors
the perplexity computation in the training script (section 3 of
``silverwing_120m_gpu_r1.py``) but uses the runtime's own ``SilverwingDecoder``
architecture (no duplicate model code).

The computation is model-direct (not via the HTTP API): it requires access to
the internal ``_torch_model`` (``SilverwingDecoder``) and ``_tokenizer``
attributes on a :class:`TorchBackend`.  When those are unavailable (e.g. the
``EchoBackend`` is in use), perplexity is reported as *skipped* rather than
fabricated.
"""

from __future__ import annotations

import hashlib
import logging
import math
from pathlib import Path
from typing import Any

from silverwing_runtime.evaluation.results import PerplexityResult

log = logging.getLogger("silverwing_runtime.evaluation.perplexity")


def compute_perplexity(
    model: Any,
    tokenizer: Any,
    val_text: str | Path,
    max_seq_len: int = 256,
    max_windows: int = 128,
    device: str | torch.device = "cpu",
) -> PerplexityResult:
    """Compute validation loss and perplexity.

    Parameters
    ----------
    model
        A ``SilverwingDecoder`` (or compatible) with a ``full_forward`` method
        returning logits of shape ``[1, seq, vocab]``.
    tokenizer
        A ``SilverwingTokenizer`` (or compatible) with an ``encode`` method.
    val_text
        Validation text content, or a path to a text file.
    max_seq_len
        Tokens per evaluation window (default 256, matching the training
        script).
    max_windows
        Maximum number of windows to evaluate (caps evaluation time).
    device
        Torch device for computation.

    Returns
    -------
    PerplexityResult
        ``val_loss``, ``val_perplexity``, token/window counts, and the SHA-256
        of the validation text.
    """
    # Imported lazily: torch is only required when a real model is actually
    # evaluated.  Modules that merely import this helper (or run the harness
    # against a non-torch backend) must not require torch.
    import torch

    if isinstance(val_text, Path):
        if not val_text.exists():
            raise FileNotFoundError(f"validation file not found: {val_text}")
        text = val_text.read_text(encoding="utf-8", errors="replace")
        val_sha = hashlib.sha256(val_text.read_bytes()).hexdigest()
    else:
        # If the string resolves to an existing file path, read it;
        # otherwise treat it as raw validation text.
        candidate = Path(val_text)
        if candidate.exists() and candidate.is_file():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            val_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
        else:
            text = val_text
            val_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

    val_ids = tokenizer.encode(text)
    n = min(len(val_ids), (max_seq_len + 1) * max_windows)
    if n < max_seq_len + 1:
        log.warning(
            "validation text only has %d tokens (need %d+ for one window); "
            "perplexity will be unreliable", len(val_ids), max_seq_len + 1
        )

    total_loss = 0.0
    count = 0
    tokens_evaluated = 0
    model.eval()
    with torch.no_grad():
        for i in range(0, n - (max_seq_len + 1), max_seq_len + 1):
            batch = torch.tensor(
                val_ids[i : i + max_seq_len + 1],
                dtype=torch.long, device=device,
            )
            if len(batch) < 2:
                break
            input_ids = batch[:-1].unsqueeze(0)  # [1, seq]
            labels = batch[1:].unsqueeze(0)      # [1, seq] (shifted)
            logits = model.full_forward(input_ids)  # [1, seq, vocab]
            loss = torch.nn.functional.cross_entropy(
                logits.reshape(-1, logits.size(-1)),
                labels.reshape(-1),
                ignore_index=0,  # pad_token_id
            )
            total_loss += loss.item()
            count += 1
            tokens_evaluated += len(batch) - 1

    avg_loss = total_loss / max(count, 1)
    # Clamp to avoid math.exp overflow on very high loss (120M base is degenerate).
    ppl = math.exp(min(avg_loss, 20.0))

    return PerplexityResult(
        val_loss=avg_loss,
        val_perplexity=ppl,
        val_tokens_evaluated=tokens_evaluated,
        val_windows=count,
        val_sha256=val_sha,
    )


def compute_perplexity_safe(
    model: Any,
    tokenizer: Any,
    val_text: str | Path,
    max_seq_len: int = 256,
    max_windows: int = 128,
    device: str = "cpu",
) -> PerplexityResult:
    """Like :func:`compute_perplexity` but catches exceptions and returns a
    *skipped* result instead of raising — used when the model may not support
    direct perplexity (e.g. EchoBackend)."""
    try:
        return compute_perplexity(
            model, tokenizer, val_text, max_seq_len, max_windows, device
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("perplexity evaluation skipped: %s", exc)
        return PerplexityResult(
            val_loss=0.0,
            val_perplexity=0.0,
            val_tokens_evaluated=0,
            val_windows=0,
            val_sha256="",
            skipped=True,
            skip_reason=str(exc),
        )

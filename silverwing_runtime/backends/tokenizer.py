"""Silverwing tokenizer handling for the torch backend.

The serving tokenizer is the exact asset paired with the checkpoint, loaded
with the canonical ``tokenizers`` library (reads the complete tokenizer.json:
ByteLevel pre-tokenizer, BPE merges, decoder).  It is never retrained,
rebuilt or remapped (section 6).

Token counts are derived from actual tokenizer activity, never fabricated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from silverwing_runtime.hashutil import verify_sha256


class TokenizerLoadError(RuntimeError):
    pass


class SilverwingTokenizer:
    """Wraps a HuggingFace ``tokenizer.json`` (BPE) with hash verification."""

    def __init__(self, path: Path, expected_sha256: str):
        self._path = Path(path)
        self._expected_sha256 = expected_sha256.lower()
        if expected_sha256:
            if not verify_sha256(self._path, self._expected_sha256):
                raise TokenizerLoadError(
                    f"tokenizer {self._path.name} failed SHA-256 verification "
                    f"(expected {self._expected_sha256})"
                )
        from tokenizers import Tokenizer

        try:
            self._tok = Tokenizer.from_file(str(self._path))
        except Exception as exc:
            raise TokenizerLoadError(
                f"failed to load tokenizer from {self._path}: {exc}"
            ) from exc

    # -- identity ----------------------------------------------------------
    @property
    def sha256(self) -> str:
        return self._expected_sha256

    @property
    def vocab_size(self) -> int:
        return self._tok.get_vocab_size()

    @property
    def eos_token_id(self) -> int | None:
        try:
            return self._tok.token_to_id("<eos>")
        except Exception:
            return None

    @property
    def bos_token_id(self) -> int | None:
        try:
            return self._tok.token_to_id("<bos>")
        except Exception:
            return None

    @property
    def pad_token_id(self) -> int | None:
        try:
            return self._tok.token_to_id("<pad>")
        except Exception:
            return None

    # -- tokenization ------------------------------------------------------
    def encode(self, text: str) -> list[int]:
        """Token ids for ``text`` (actual tokenizer activity)."""
        return list(self._tok.encode(text).ids)

    def encode_count(self, text: str) -> int:
        return len(self.encode(text))

    def decode(self, ids: list[int]) -> str:
        if not ids:
            return ""
        return self._tok.decode(list(ids))

    def id_to_token(self, token_id: int) -> str:
        return self._tok.id_to_token(token_id) or f"<{token_id}>"


def tokenizer_assets(asset_dir: Path, expected_sha256: str) -> SilverwingTokenizer:
    """Load the tokenizer from the *materialized asset directory*."""
    path = asset_dir / "tokenizer.json"
    if not path.exists():
        raise TokenizerLoadError(
            f"tokenizer.json missing from model assets {asset_dir}"
        )
    return SilverwingTokenizer(path, expected_sha256)
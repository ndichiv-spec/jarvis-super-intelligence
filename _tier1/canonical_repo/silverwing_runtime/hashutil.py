"""SHA-256 verification utilities.

Every artifact in a model manifest is verified before it is served.  This
module is intentionally tiny and dependency-free so it can be reused by the
registry, the cache and the platform client.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

log = logging.getLogger("silverwing_runtime.hashutil")

_CHUNK = 1024 * 1024  # 1 MiB


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 of a file in streaming chunks (memory-safe)."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> bool:
    """Return True iff the file at ``path`` matches ``expected`` (hex sha256).

    Never raises for a mismatched file; callers decide policy.
    """
    if not expected:
        log.warning("No expected hash given for %s; skipping verification", path)
        return True
    actual = sha256_file(path)
    ok = actual.lower() == expected.strip().lower()
    if not ok:
        log.error(
            "SHA-256 mismatch for %s: expected %s, got %s",
            path,
            expected,
            actual,
        )
    return ok


class HashVerificationError(RuntimeError):
    """Raised when a downloaded artifact does not match its manifest hash."""

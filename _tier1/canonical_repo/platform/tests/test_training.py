import pytest

pytest.importorskip(
    "core.training_engine",
    reason="Legacy training engine is not part of the canonical platform.",
)

from core.training_engine import get_training_engine

e = get_training_engine()
print("Training Engine stats:", e.get_stats())

"""Model lifecycle registry for JARVIS (spec §16, §30, §31, §34).

Owns the governed lifecycle of every model that matters to the platform:

* **external provider models** (OpenAI/NVIDIA/HF/... discovered entries),
* **local models** (weights on this machine),
* **JARVIS base / candidate / production** brain models,
* **training checkpoints, adapters, datasets, evaluation artifacts**.

Silverwing keeps its own identity family and is never merged into the
``jarvis`` lineage (spec §33). Promotion from candidate to production is
human-gated (spec §30): ``CANDIDATE -> EVALUATED -> PROMOTION_REVIEW ->
HUMAN_APPROVAL -> PRODUCTION``.
"""

from .registry import ModelRecord, ModelRegistry
from .types import (
    LifecycleStage,
    ModelLifecycleType,
    PromotionState,
)

__all__ = [
    "LifecycleStage",
    "ModelLifecycleType",
    "ModelRecord",
    "ModelRegistry",
    "PromotionState",
]
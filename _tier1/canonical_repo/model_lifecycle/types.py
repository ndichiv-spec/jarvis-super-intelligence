"""Enumerations for the governed model lifecycle (spec §16, §30)."""

from __future__ import annotations

from enum import Enum


class ModelLifecycleType(str, Enum):
    """What a model *is* inside the lifecycle.  Stable lowercase values."""

    EXTERNAL_PROVIDER_MODEL = "external_provider_model"
    LOCAL_MODEL = "local_model"
    JARVIS_BASE = "jarvis_base"
    JARVIS_CANDIDATE = "jarvis_candidate"
    JARVIS_PRODUCTION = "jarvis_production"
    TRAINING_CHECKPOINT = "training_checkpoint"
    ADAPTER = "adapter"
    DATASET = "dataset"
    EVALUATION_ARTIFACT = "evaluation_artifact"

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS: dict[ModelLifecycleType, str] = {
    ModelLifecycleType.EXTERNAL_PROVIDER_MODEL: "external provider model",
    ModelLifecycleType.LOCAL_MODEL: "local model",
    ModelLifecycleType.JARVIS_BASE: "JARVIS base model",
    ModelLifecycleType.JARVIS_CANDIDATE: "JARVIS candidate",
    ModelLifecycleType.JARVIS_PRODUCTION: "JARVIS production",
    ModelLifecycleType.TRAINING_CHECKPOINT: "training checkpoint",
    ModelLifecycleType.ADAPTER: "adapter",
    ModelLifecycleType.DATASET: "dataset",
    ModelLifecycleType.EVALUATION_ARTIFACT: "evaluation artifact",
}


class LifecycleStage(str, Enum):
    """Current stage of a lifecycle record (spec §30)."""

    BASE = "base"  # immutable base / seed model
    TRAINING = "training"  # an active training/fine-tune phase
    CANDIDATE = "candidate"  # produced candidate, not yet fully evaluated
    EVALUATION = "evaluation"  # evaluated vs baseline (spec §31)
    PROMOTED = "promoted"  # human-approved; production (or staged) model
    REJECTED = "rejected"  # failed evaluation / human rejection / regression
    HELD = "held"  # paused / parked for later


class PromotionState(str, Enum):
    """Human-gating state for candidate -> production (spec §30)."""

    NONE = "none"  # not in promotion process
    PROMOTION_REVIEW = "promotion_review"  # evaluated; awaiting promotion review
    HUMAN_APPROVAL = "human_approval"  # promotion review passed; human must approve
    APPROVED = "approved"  # human approved -> production eligible
    REJECTED = "rejected"  # human rejected promotion
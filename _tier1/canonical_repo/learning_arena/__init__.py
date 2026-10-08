"""JARVIS Learning Arena — the platform where learning happens (spec §25-§31).

The Learning Arena is where the Teacher Node's lessons are applied: it
manages learning tasks, captures experiences, computes rewards, catalogs
failures, evaluates model revisions, and tracks dataset/model lineage.

Components:
  * :mod:`tasks`            — Task lifecycle + TaskArena (scheduling)
  * :mod:`experiences`      — ArenaExperienceArena (capture task outcomes)
  * :mod:`lessons`          — LessonArena (apply lessons to scheduling)
  * :mod:`feedback`          — FeedbackArena (automated/human/synthetic feedback)
  * :mod:`rewards`          — RewardEngine (compute reward signals)
  * :mod:`failures`          — FailureArena (catalog + categorize failures)
  * :mod:`evaluations`       — EvaluationArena + benchmarks
  * :mod:`datasets`          — DatasetArena (versioning, validation, lineage)
  * :mod:`training_runs`     — TrainingRunArena (run lifecycle + experience capture)
*  :mod:`model_revisions`   — ModelRevisionArena (registry + lineage)

The governed loop adds:
  * :mod:`problem_generator` — 36-domain, 1-6 difficulty curriculum generator
  * :mod:`verification`      — deterministic (canonical + sandbox) verification
  * :mod:`lesson_gate`       — lesson classification (CANDIDATE/VERIFIED/...)
  * :mod:`dataset_builder`   — immutable curriculum dataset revisions
  * :mod:`evaluator`         — candidate-vs-baseline evaluation
  * :mod:`learning_loop`     — end-to-end governed learning episodes

The arena integrates with the Teacher Node via dependency injection —
it never imports teacher_node at module level (only at method call time)
to avoid circular imports.
"""

from __future__ import annotations

from .datasets import (
    Dataset,
    DatasetArena,
    DatasetStatus,
    DatasetValidation,
)
from .evaluations import (
    Benchmark,
    EvalResult,
    EvalSpec,
    EvalStatus,
    EvaluationArena,
)
from .experiences import (
    ArenaExperience,
    ExperienceArena,
)
from .failures import (
    FailureArena,
    FailureCategory,
    FailureRecord,
)
from .feedback import (
    Feedback,
    FeedbackArena,
    FeedbackQuery,
    FeedbackSource,
)
from .lessons import LessonArena
from .model_revisions import (
    ModelRevision,
    ModelRevisionArena,
    RevisionEvent,
    RevisionStatus,
)
from .rewards import (
    DEFAULT_WEIGHTS,
    OUTCOME_REWARDS,
    RewardComponents,
    RewardEngine,
)
from .tasks import (
    ResourceSpec,
    Task,
    TaskArena,
    TaskSpec,
    TaskStatus,
)
from .problem_generator import (
    DIFFICULTY_ORDER,
    DIFFICULTY_SCALE,
    DIFFICULTY_SCALE_LABELS,
    DOMAIN_CATEGORIES,
    DomainInfo,
    Problem,
    ProblemGenerator,
    ProblemMetadata,
    difficulty_from_scale,
    scale_of,
)
from .training_runs import (
    TrainingConfig,
    TrainingMetrics,
    TrainingRun,
    TrainingRunArena,
    TrainingStatus,
)
from .dataset_builder import (
    CurriculumDatasetBuilder,
    DatasetExample,
    DatasetRevision,
)
from .evaluator import (
    CurriculumEvaluator,
    EvalItemResult,
    EvaluationResult,
)
from .learning_loop import LearningEpisode, LearningLoop
from .lesson_gate import (
    CurriculumLesson,
    LessonClass,
    LessonGate,
)
from .verification import (
    VerificationOutcome,
    VerificationResult,
    verify_problem,
)

__version__ = "0.1.0"

__all__ = [
    "ArenaExperience",
    "Benchmark",
    "CurriculumDatasetBuilder",
    "CurriculumEvaluator",
    "CurriculumLesson",
    "Dataset",
    "DatasetArena",
    "DatasetExample",
    "DatasetRevision",
    "DatasetStatus",
    "DatasetValidation",
    "DEFAULT_WEIGHTS",
    "DIFFICULTY_ORDER",
    "DIFFICULTY_SCALE",
    "DIFFICULTY_SCALE_LABELS",
    "DOMAIN_CATEGORIES",
    "DomainInfo",
   "EvalResult",
    "EvalSpec",
    "EvalStatus",
    "EvalItemResult",
    "EvaluationArena",
    "EvaluationResult",
    "ExperienceArena",
    "FailureArena",
    "FailureCategory",
    "FailureRecord",
    "Feedback",
    "FeedbackArena",
    "FeedbackQuery",
    "FeedbackSource",
    "LessonArena",
    "LessonClass",
    "LessonGate",
    "LearningEpisode",
    "LearningLoop",
    "ModelRevision",
    "ModelRevisionArena",
    "OUTCOME_REWARDS",
    "Problem",
    "ProblemGenerator",
    "ProblemMetadata",
    "ResourceSpec",
    "RewardComponents",
    "RewardEngine",
    "RevisionEvent",
    "RevisionStatus",
    "Task",
    "TaskArena",
    "TaskSpec",
    "TaskStatus",
    "TrainingConfig",
    "TrainingMetrics",
    "TrainingRun",
    "TrainingRunArena",
    "TrainingStatus",
    "VerificationOutcome",
    "VerificationResult",
    "difficulty_from_scale",
    "scale_of",
    "verify_problem",
]

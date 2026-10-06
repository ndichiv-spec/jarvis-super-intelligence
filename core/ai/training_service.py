from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ModelType(str, Enum):
    LANGUAGE_MODEL = "language_model"
    VISION_MODEL = "vision_model"
    EMBEDDING_MODEL = "embedding_model"


@dataclass
class TrainingConfig:
    model_type: ModelType
    base_model: str
    dataset_path: str
    epochs: int = 1
    batch_size: int = 8


class TrainingService:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._experiments: dict[str, dict[str, Any]] = {}

    async def train_model(self, model_name: str, config: TrainingConfig) -> str:
        job_id = f"job-{uuid.uuid4()}"
        self._jobs[job_id] = {
            "id": job_id,
            "model_name": model_name,
            "model_type": config.model_type,
            "status": "pending",
            "base_model": config.base_model,
        }
        return job_id

    async def get_training_status(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job["status"] == "pending":
            job["status"] = "preparing"
        elif job["status"] == "preparing":
            job["status"] = "training"
        return dict(job)

    async def list_training_jobs(self) -> list[dict[str, Any]]:
        return [dict(job) for job in self._jobs.values()]

    async def create_automl_experiment(self, dataset_path: str, target_column: str, task_type: str) -> str:
        experiment_id = f"automl-{uuid.uuid4()}"
        self._experiments[experiment_id] = {
            "id": experiment_id,
            "dataset_path": dataset_path,
            "target_column": target_column,
            "task_type": task_type,
            "status": "created",
        }
        return experiment_id


training_service = TrainingService()

__all__ = ["ModelType", "TrainingConfig", "TrainingService", "training_service"]

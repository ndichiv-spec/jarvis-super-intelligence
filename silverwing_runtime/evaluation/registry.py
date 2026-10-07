"""Evaluation Registry — persists and queries model evaluation results.

The registry is the durable backing for the Evaluation Harness.  Each
evaluation run produces an :class:`EvaluationResult` that is stored as a
JSON document keyed by ``(model_id, revision, label)``.  The registry
supports:

* recording a new evaluation result,
* listing all evaluations for a model,
* retrieving the latest evaluation,
* comparing two checkpoint evaluations,
* generating a human-readable promotion evidence report (spec section 48).

Results are stored under ``<model_repo>/evaluations/`` by default (or the
directory specified by ``SILVERWING_EVAL_DIR``), keeping them alongside the
model manifests they describe.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from silverwing_runtime.evaluation.results import EvaluationResult

log = logging.getLogger("silverwing_runtime.evaluation.registry")

_DEFAULT_REGISTRY_DIR = Path("silverwing_runtime/evaluation")  # relative fallback


def _default_eval_dir(model_repo: Path | None = None) -> Path:
    """Return the directory where evaluation results are persisted."""
    env_dir = __import__("os").environ.get("SILVERWING_EVAL_DIR")
    if env_dir:
        return Path(env_dir)
    if model_repo is not None:
        return model_repo / "evaluations"
    return Path("evaluations")


class EvaluationRegistry:
    """Filesystem-backed registry of model evaluation results.

    Parameters
    ----------
    base_dir
        Directory where evaluation JSON files are stored.  Created if it
        does not exist.
    """

    def __init__(self, base_dir: Path | str | None = None):
        self._dir = Path(base_dir) if base_dir else _default_eval_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @property
    def base_dir(self) -> Path:
        return self._dir

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #
    def _entry_path(self, model_id: str, revision: str, label: str) -> Path:
        safe_model = model_id.replace("/", "--")
        safe_rev = revision.replace("/", "--")
        safe_label = label.replace("/", "-").replace("\\", "-")
        return self._dir / safe_model / safe_rev / f"{safe_label}.json"

    def _index_path(self, model_id: str, revision: str) -> Path:
        safe_model = model_id.replace("/", "--")
        safe_rev = revision.replace("/", "--")
        return self._dir / safe_model / safe_rev / "index.json"

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def record(self, result: EvaluationResult) -> Path:
        """Persist an evaluation result and update the index.

        Returns the path to the written JSON document.
        """
        path = self._entry_path(
            result.model_id, result.revision, result.label
        )
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(result.model_dump_json(indent=2))
            self._update_index(result)
        log.info("recorded evaluation %s/%s@%s", result.model_id, result.label, result.revision)
        return path

    def list_evaluations(self, model_id: str, revision: str | None = None) -> list[dict[str, Any]]:
        """List all evaluation entries for a model (optionally filtered by revision)."""
        safe_model = model_id.replace("/", "--")
        model_path = self._dir / safe_model
        if not model_path.exists():
            return []
        results: list[dict[str, Any]] = []
        # When revision is None, iterate over all revision subdirectories.
        if revision is None:
            rev_dirs = sorted(
                p for p in model_path.iterdir() if p.is_dir()
            )
        else:
            rev_dir = model_path / revision.replace("/", "--")
            rev_dirs = [rev_dir] if rev_dir.exists() else []
        for rd in rev_dirs:
            idx = self._index_path(model_id, rd.name)
            if idx.exists():
                try:
                    with open(idx, encoding="utf-8") as f:
                        data = json.load(f)
                    entries = data.get("evaluations", [])
                    results.extend(entries)
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not read index %s: %s", idx, exc)
        return results

    def get(
        self, model_id: str, revision: str, label: str
    ) -> EvaluationResult | None:
        """Retrieve a specific evaluation result by (model_id, revision, label)."""
        path = self._entry_path(model_id, revision, label)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return EvaluationResult(**data)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            log.warning("could not load evaluation %s: %s", path, exc)
            return None

    def latest(self, model_id: str, revision: str | None = None) -> EvaluationResult | None:
        """Return the most recent evaluation for a model (optionally a revision)."""
        entries = self.list_evaluations(model_id, revision)
        if not entries:
            return None
        # Sort by timestamp descending.
        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        latest_entry = entries[0]
        return self.get(model_id, latest_entry["revision"], latest_entry["label"])

    def compare(self, model_id: str) -> dict[str, Any]:
        """Compare all evaluation runs for a model across checkpoints.

        Returns a summary dict with per-run metrics, making it easy to see
        training progress at a glance.
        """
        entries = self.list_evaluations(model_id)
        runs: list[dict[str, Any]] = []
        for entry in entries:
            result = self.get(model_id, entry["revision"], entry["label"])
            if result is None:
                continue
            bench_summary = {
                name: {"correct": br.correct, "total": br.total, "accuracy": br.accuracy}
                for name, br in result.benchmarks.items()
            }
            runs.append({
                "label": result.label,
                "revision": result.revision,
                "timestamp": result.timestamp,
                "val_loss": result.perplexity.val_loss,
                "val_perplexity": result.perplexity.val_perplexity,
                "perplexity_skipped": result.perplexity.skipped,
                "benchmarks": bench_summary,
                "beats_r2000_val_loss": result.comparison.beats_baseline_val_loss,
                "beats_r2000_ppl": result.comparison.beats_baseline_ppl,
                "elapsed_seconds": result.total_evaluation_seconds,
            })
        return {
            "model_id": model_id,
            "total_runs": len(runs),
            "runs": runs,
        }

    def promotion_evidence(self, model_id: str, revision: str = "latest") -> dict[str, Any]:
        """Generate a promotion evidence report for model promotion decisions.

        Per spec section 48: model promotion requires evaluation evidence.
        This report consolidates the key gating metrics into a single document
        suitable for review.

        Parameters
        ----------
        model_id
            The model to evaluate for promotion.
        revision
            Specific revision, or ``"latest"`` for the most recent evaluation.
        """
        if revision == "latest":
            result = self.latest(model_id)
        else:
            result = self.latest(model_id, revision)

        if result is None:
            return {
                "model_id": model_id,
                "revision": revision,
                "status": "no_evaluation_found",
                "message": f"No evaluation results found for {model_id}@{revision}",
            }

        # Promotion gates (spec section 48):
        # 1. Validation perplexity below r2000 baseline
        # 2. Math/logic/coding/knowledge at least match r2000
        # 3. No EchoBackend substitution in results
        # 4. Weights SHA-256 verified
        gates = {
            "perplexity_below_r2000": result.comparison.beats_baseline_ppl,
            "val_loss_below_r2000": result.comparison.beats_baseline_val_loss,
            "math_at_least_r2000": (
                result.comparison.model_math[0] >= result.comparison.baseline_math[0]
            ),
            "logic_at_least_r2000": (
                result.comparison.model_logic[0] >= result.comparison.baseline_logic[0]
            ),
            "knowledge_at_least_r2000": (
                result.comparison.model_knowledge[0] >= result.comparison.baseline_knowledge[0]
            ),
            "coding_at_least_r2000": (
                result.comparison.model_coding[0] >= result.comparison.baseline_coding[0]
            ),
            "weights_sha256_present": bool(result.weights_sha256),
            "used_torch_backend": all(
                s.backend == "torch" for s in result.generation_samples
            ) if result.generation_samples else True,
            "no_echo_substitution": all(
                "sw-echo" not in s.response for s in result.generation_samples
            ),
        }

        all_pass = all(gates.values())

        return {
            "model_id": result.model_id,
            "revision": result.revision,
            "weights_sha256": result.weights_sha256,
            "param_count": result.param_count,
            "evaluated_at": result.timestamp,
            "val_loss": result.perplexity.val_loss,
            "val_perplexity": result.perplexity.val_perplexity,
            "perplexity_skipped": result.perplexity.skipped,
            "benchmarks": {
                name: {"correct": br.correct, "total": br.total, "accuracy": br.accuracy}
                for name, br in result.benchmarks.items()
            },
            "comparison": {
                "beats_r2000_val_loss": result.comparison.beats_baseline_val_loss,
                "beats_r2000_ppl": result.comparison.beats_baseline_ppl,
                "math_accuracy": f"{result.comparison.model_math[0]}/{result.comparison.model_math[1]}",
                "logic_accuracy": f"{result.comparison.model_logic[0]}/{result.comparison.model_logic[1]}",
                "knowledge_accuracy": f"{result.comparison.model_knowledge[0]}/{result.comparison.model_knowledge[1]}",
                "coding_accuracy": f"{result.comparison.model_coding[0]}/{result.comparison.model_coding[1]}",
            },
            "gates": gates,
            "all_gates_passed": all_pass,
            "promotion_status": "clear_for_promotion" if all_pass else "evidence_insufficient",
            "elapsed_seconds": result.total_evaluation_seconds,
        }

    # ------------------------------------------------------------------ #
    # Internal: index management
    # ------------------------------------------------------------------ #
    def _update_index(self, result: EvaluationResult) -> None:
        """Update the index file for this model/revision."""
        idx_path = self._entry_path(
            result.model_id, result.revision, ""
        ).parent / "index.json"
        entries: list[dict[str, Any]] = []
        if idx_path.exists():
            try:
                with open(idx_path, encoding="utf-8") as f:
                    data = json.load(f)
                entries = data.get("evaluations", [])
            except Exception:  # noqa: BLE001
                entries = []
        # Check if this label already exists (overwrite).
        label = result.label
        found = False
        for e in entries:
            if e.get("label") == label and e.get("revision") == result.revision:
                e.update({
                    "timestamp": result.timestamp,
                    "val_loss": result.perplexity.val_loss,
                    "val_perplexity": result.perplexity.val_perplexity,
                    "param_count": result.param_count,
                    "path": str(self._entry_path(
                        result.model_id, result.revision, label
                    )),
                })
                found = True
                break
        if not found:
            entries.append({
                "label": label,
                "revision": result.revision,
                "timestamp": result.timestamp,
                "val_loss": result.perplexity.val_loss,
                "val_perplexity": result.perplexity.val_perplexity,
                "param_count": result.param_count,
                "path": str(self._entry_path(
                    result.model_id, result.revision, label
                )),
            })
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump({"model_id": result.model_id, "evaluations": entries}, f, indent=2)

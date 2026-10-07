"""Tests for the Learning Arena (spec §25-§31).

Covers:
  * TaskArena: create, schedule, start, complete, cancel lifecycle
  * ExperienceArena: capture outcomes, delegate to teacher node recorder
  * FeedbackArena: record signals, normalize metrics, query
  * RewardEngine: compute rewards from feedback/outcome/efficiency/novelty
  * FailureArena: categorize and catalog failures
  * EvaluationArena: submit, mark_complete, mark_error, to_feedback
  * DatasetArena: register, validate, lineage, readiness
  * TrainingRunArena: launch, dispatch, report_metrics, complete, cancel
  * ModelRevisionArena: register, lineage, promote, deprecate, events
"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest

from learning_arena.tasks import (
    ResourceSpec, Task, TaskArena, TaskSpec, TaskStatus,
)
from learning_arena.experiences import ArenaExperience, ExperienceArena
from learning_arena.feedback import (
    Feedback, FeedbackArena, FeedbackQuery, FeedbackSource,
)
from learning_arena.rewards import (
    DEFAULT_WEIGHTS, RewardComponents, RewardEngine,
)
from learning_arena.failures import (
    FailureArena, FailureCategory, FailureRecord,
)
from learning_arena.evaluations import (
    Benchmark, EvalResult, EvalSpec, EvalStatus, EvaluationArena,
)
from learning_arena.datasets import (
    Dataset, DatasetArena, DatasetStatus, DatasetValidation,
)
from learning_arena.training_runs import (
    TrainingConfig, TrainingMetrics, TrainingRun,
    TrainingRunArena, TrainingStatus,
)
from learning_arena.model_revisions import (
    ModelRevision, ModelRevisionArena, RevisionStatus,
)
from learning_arena.lessons import LessonArena


# --------------------------------------------------------------------------- #
# TaskArena
# --------------------------------------------------------------------------- #
class TestTaskArena:
    def test_create_task(self):
        arena = TaskArena()
        task = arena.create(TaskSpec(name="tune-model", category="training"))
        assert task.id is not None
        assert task.name == "tune-model"
        assert task.status == TaskStatus.PENDING
        assert task.category == "training"

    def test_lifecycle(self):
        arena = TaskArena()
        task = arena.create(TaskSpec(name="eval-1", category="evaluation"))
        assert task.status == TaskStatus.PENDING
        arena.schedule(task.id)
        assert task.status == TaskStatus.SCHEDULED
        arena.start(task.id)
        assert task.status == TaskStatus.RUNNING
        arena.complete(task.id)
        assert task.status == TaskStatus.SUCCESS
        assert task.duration is not None

    def test_complete_with_error(self):
        arena = TaskArena()
        task = arena.create(TaskSpec(name="train-1", category="training"))
        arena.schedule(task.id)
        arena.start(task.id)
        arena.complete(task.id, outcome=TaskStatus.FAILED, error="OOM")
        assert task.status == TaskStatus.FAILED
        assert task.error == "OOM"

    def test_cancel_task(self):
        arena = TaskArena()
        task = arena.create(TaskSpec(name="train-1", category="training"))
        arena.schedule(task.id)
        arena.cancel(task.id)
        assert task.status == TaskStatus.CANCELLED

    def test_idempotent_schedule(self):
        arena = TaskArena()
        task = arena.create(TaskSpec(name="t1", category="training"))
        arena.schedule(task.id)
        arena.schedule(task.id)  # should not raise
        assert task.status == TaskStatus.SCHEDULED

    def test_list_filtering(self):
        arena = TaskArena()
        arena.create(TaskSpec(name="t1", category="training"))
        arena.create(TaskSpec(name="t2", category="evaluation"))
        assert len(arena.list()) == 2
        assert len(arena.list(category="training")) == 1
        assert len(arena.list(category="evaluation")) == 1

    def test_terminal_status(self):
        arena = TaskArena()
        task = arena.create(TaskSpec(name="t1", category="training"))
        assert not task.is_terminal()
        arena.complete(task.id)
        assert task.is_terminal()

    def test_resource_spec_defaults(self):
        spec = ResourceSpec()
        assert spec.cpu_cores == 1.0
        assert spec.memory_gb == 1.0
        assert spec.gpu_count == 0
        assert spec.disk_gb == 1.0


# --------------------------------------------------------------------------- #
# FeedbackArena
# --------------------------------------------------------------------------- #
class TestFeedbackArena:
    def test_record_feedback(self):
        arena = FeedbackArena()
        fb = arena.record("task-1", FeedbackSource.HUMAN, 0.8)
        assert fb.score == 0.8
        assert fb.task_id == "task-1"

    def test_score_clamping(self):
        arena = FeedbackArena()
        fb = arena.record("t1", FeedbackSource.AUTOMATED, 5.0)
        assert fb.score == 1.0
        fb2 = arena.record("t2", FeedbackSource.AUTOMATED, -3.0)
        assert fb2.score == -1.0

    def test_normalize_loss(self):
        arena = FeedbackArena()
        assert arena.normalize_metric("loss", 0.5) == 0.5
        assert arena.normalize_metric("loss", 1.5) == -0.5

    def test_normalize_accuracy(self):
        arena = FeedbackArena()
        assert arena.normalize_metric("accuracy", 1.0) == 1.0
        assert arena.normalize_metric("accuracy", 0.0) == -1.0
        assert arena.normalize_metric("accuracy", 0.5) == 0.0

    def test_normalize_latency(self):
        arena = FeedbackArena()
        assert arena.normalize_metric("latency", 0) == 1.0
        assert arena.normalize_metric("latency", 30) == 0.0
        assert arena.normalize_metric("latency", 60) == -1.0

    def test_query_filtering(self):
        arena = FeedbackArena()
        arena.record("t1", FeedbackSource.AUTOMATED, 0.8)
        arena.record("t1", FeedbackSource.HUMAN, -0.3)
        arena.record("t2", FeedbackSource.AUTOMATED, 0.5)
        # Filter by task
        results = arena.query(FeedbackQuery(task_ids=["t1"]))
        assert len(results) == 2
        # Filter by source
        results = arena.query(FeedbackQuery(sources=[FeedbackSource.HUMAN]))
        assert len(results) == 1
        # Filter by score range
        results = arena.query(FeedbackQuery(min_score=0.0))
        assert len(results) == 2
        # Average score for task 1
        assert arena.average_score("t1") == pytest.approx(0.25)

    def test_for_task(self):
        arena = FeedbackArena()
        arena.record("t1", FeedbackSource.AUTOMATED, 0.8)
        arena.record("t1", FeedbackSource.HUMAN, 0.6)
        assert len(arena.for_task("t1")) == 2


# --------------------------------------------------------------------------- #
# RewardEngine
# --------------------------------------------------------------------------- #
class TestRewardEngine:
    def test_compute_basic_success(self):
        fb = FeedbackArena()
        fb.record("t1", FeedbackSource.AUTOMATED, 0.8)
        engine = RewardEngine(fb)
        r = engine.compute("t1", "success")
        assert r.total <= 1.0
        assert r.feedback == 0.8
        assert r.outcome == 1.0  # success

    def test_compute_failure(self):
        fb = FeedbackArena()
        engine = RewardEngine(fb)
        r = engine.compute("t1", "failure")
        assert r.outcome == -0.5
        assert r.total < 0

    def test_compute_with_efficiency(self):
        fb = FeedbackArena()
        engine = RewardEngine(fb)
        r = engine.compute("t1", "success", resource_cost=50.0, expected_cost=100.0)
        assert r.efficiency > 0  # under budget → positive

    def test_compute_over_budget(self):
        fb = FeedbackArena()
        engine = RewardEngine(fb)
        r = engine.compute("t1", "success", resource_cost=200.0, expected_cost=100.0)
        assert r.efficiency < 0  # over budget → negative

    def test_compute_novelty_bonus(self):
        fb = FeedbackArena()
        engine = RewardEngine(fb)
        r = engine.compute("t1", "success", is_novel=True)
        assert r.novelty == 0.5

    def test_compute_trust_weight(self):
        fb = FeedbackArena()
        engine = RewardEngine(fb)
        r = engine.compute("t1", "success", lesson_confidence=0.8)
        assert r.trust == 0.8

    def test_reward_clamped(self):
        fb = FeedbackArena()
        fb.record("t1", FeedbackSource.AUTOMATED, 1.0)
        engine = RewardEngine(fb)
        r = engine.compute("t1", "success", resource_cost=0, expected_cost=1, is_novel=True, lesson_confidence=1.0)
        assert -1.0 <= r.total <= 1.0

    def test_rank_tasks(self):
        fb = FeedbackArena()
        engine = RewardEngine(fb)
        r1 = engine.compute("t1", "success")
        r2 = engine.compute("t2", "failure")
        ranked = engine.rank_tasks([("t1", r1), ("t2", r2)])
        assert ranked[0][0] == "t1"  # success ranks higher
        assert ranked[1][0] == "t2"

    def test_should_prune(self):
        fb = FeedbackArena()
        fb.record("t1", FeedbackSource.AUTOMATED, -1.0)
        engine = RewardEngine(fb)
        bad = engine.compute("t1", "failure")
        assert engine.should_prune(bad)
        good = engine.compute("t1", "success")
        assert not engine.should_prune(good)


# --------------------------------------------------------------------------- #
# FailureArena
# --------------------------------------------------------------------------- #
class TestFailureArena:
    def test_record_and_categorize(self):
        arena = FailureArena()
        rec = arena.record("task-1", "CUDA out of memory")
        assert rec.category == FailureCategory.OUT_OF_MEMORY

    def test_timeout_category(self):
        arena = FailureArena()
        rec = arena.record("task-2", "Request timed out after 300s")
        assert rec.category == FailureCategory.TIMEOUT

    def test_network_category(self):
        arena = FailureArena()
        rec = arena.record("task-3", "Connection refused to api.example.com")
        assert rec.category == FailureCategory.NETWORK_ERROR

    def test_auth_category(self):
        arena = FailureArena()
        rec = arena.record("task-4", "403 Forbidden")
        assert rec.category == FailureCategory.AUTH_ERROR

    def test_rate_limit_category(self):
        arena = FailureArena()
        rec = arena.record("task-5", "429 Too Many Requests")
        assert rec.category == FailureCategory.RATE_LIMIT

    def test_unknown_category(self):
        arena = FailureArena()
        rec = arena.record("task-6", "Something unexpected happened")
        assert rec.category == FailureCategory.UNKNOWN

    def test_error_sanitized(self):
        arena = FailureArena()
        rec = arena.record("task-7", "Failed with key sk-test-12345")
        assert "sk-test-12345" not in rec.error_message

    def test_summary(self):
        arena = FailureArena()
        arena.record("t1", "OOM")
        arena.record("t2", "OOM")
        arena.record("t3", "Timeout")
        summary = arena.summary()
        assert summary["total"] == 3
        assert summary["by_category"]["out_of_memory"] == 2
        assert summary["by_category"]["timeout"] == 1

    def test_top_patterns(self):
        arena = FailureArena()
        arena.record("t1", "OOM")
        arena.record("t2", "OOM")
        arena.record("t3", "OOM")
        arena.record("t4", "Timeout")
        patterns = arena.top_patterns(n=2)
        assert patterns[0]["category"] == "out_of_memory"
        assert patterns[0]["count"] == 3


# --------------------------------------------------------------------------- #
# EvaluationArena
# --------------------------------------------------------------------------- #
class TestEvaluationArena:
    def test_register_and_submit(self):
        arena = EvaluationArena()
        arena.register_benchmark(Benchmark(
            name="mmlu", description="MMLU benchmark", metrics=["accuracy"],
        ))
        bench = arena.get_benchmark("mmlu")
        assert bench is not None
        assert bench.metrics == ["accuracy"]

    def test_submit_eval(self):
        arena = EvaluationArena()
        spec = EvalSpec(
            name="eval-1", model_revision="rev-1",
            benchmark="mmlu", dataset="mmlu:v1",
        )
        result = arena.submit(spec)
        assert result.status == EvalStatus.PENDING
        assert result.spec.benchmark == "mmlu"

    def test_lifecycle(self):
        arena = EvaluationArena()
        spec = EvalSpec(name="e1", model_revision="r1", benchmark="mmlu", dataset="d1")
        result = arena.submit(spec)
        arena.mark_running(result.id)
        assert result.status == EvalStatus.RUNNING
        assert result.started_at is not None
        arena.mark_complete(result.id, metrics={"accuracy": 0.95}, per_task=[{"id": 1, "correct": True}])
        assert result.status == EvalStatus.COMPLETE
        assert result.metrics["accuracy"] == 0.95
        assert len(result.per_task) == 1

    def test_mark_error(self):
        arena = EvaluationArena()
        spec = EvalSpec(name="e1", model_revision="r1", benchmark="mmlu", dataset="d1")
        result = arena.submit(spec)
        arena.mark_error(result.id, "benchmark not found")
        assert result.status == EvalStatus.ERROR
        assert result.error == "benchmark not found"

    def test_to_feedback(self):
        arena = EvaluationArena()
        fb_arena = FeedbackArena()
        spec = EvalSpec(name="e1", model_revision="r1", benchmark="mmlu", dataset="d1")
        result = arena.submit(spec)
        arena.mark_complete(result.id, metrics={"accuracy": 0.90})
        fb = result.to_feedback("task-1", feedback_arena=fb_arena)
        assert fb is not None
        assert fb.source == FeedbackSource.AUTOMATED
        assert fb.raw_score == 0.90
        assert fb.score == pytest.approx(0.8)  # 0.9 * 2 - 1 = 0.8

    def test_results_for_model(self):
        arena = EvaluationArena()
        spec = EvalSpec(name="e1", model_revision="rev-1", benchmark="mmlu", dataset="d1")
        result = arena.submit(spec)
        arena.mark_complete(result.id, metrics={"accuracy": 0.95})
        results = arena.results_for_model("rev-1")
        assert len(results) == 1

    def test_latest_for_benchmark(self):
        arena = EvaluationArena()
        s1 = EvalSpec(name="e1", model_revision="r1", benchmark="mmlu", dataset="d1")
        s2 = EvalSpec(name="e2", model_revision="r2", benchmark="mmlu", dataset="d1")
        r1 = arena.submit(s1)
        r2 = arena.submit(s2)
        arena.mark_complete(r1.id, metrics={"accuracy": 0.85})
        arena.mark_complete(r2.id, metrics={"accuracy": 0.90})
        latest = arena.latest_for_benchmark("mmlu")
        assert latest.id == r2.id


# --------------------------------------------------------------------------- #
# DatasetArena
# --------------------------------------------------------------------------- #
class TestDatasetArena:
    def test_register_dataset(self):
        arena = DatasetArena()
        ds = arena.register("my-data", "s3://bucket/data.jsonl", version="1.0.0")
        assert ds.name == "my-data"
        assert ds.uri == "s3://bucket/data.jsonl"
        assert ds.status == DatasetStatus.REGISTERED

    def test_validate_local_file_exists(self):
        arena = DatasetArena()
        ds = arena.register("test", "/nonexistent/path/data.jsonl")
        val = arena.validate(ds.id)
        assert not val.valid
        assert any("not found" in e for e in val.errors)

    def test_validate_uri(self):
        arena = DatasetArena()
        ds = arena.register("remote", "s3://bucket/data.jsonl")
        val = arena.validate(ds.id)
        assert val.valid  # URI doesn't exist check, so valid

    def test_mark_ready(self):
        arena = DatasetArena()
        ds = arena.register("d1", "s3://bucket/data.jsonl")
        arena.validate(ds.id)
        arena.mark_ready(ds.id)
        assert ds.status == DatasetStatus.READY
        assert ds.is_ready()

    def test_content_hash(self):
        arena = DatasetArena()
        ds1 = arena.register("d1", "s3://bucket/data.jsonl", version="1.0.0")
        ds2 = arena.register("d1", "s3://bucket/data.jsonl", version="1.0.0")
        assert ds1.content_hash == ds2.content_hash

    def test_record_usage(self):
        arena = DatasetArena()
        ds = arena.register("d1", "s3://bucket/data.jsonl")
        arena.record_usage(ds.id, "model-rev-1")
        assert "model-rev-1" in ds.used_by

    def test_lineage_chain(self):
        arena = DatasetArena()
        parent = arena.register("parent", "s3://bucket/parent.jsonl", version="1.0.0")
        child = arena.register("child", "s3://bucket/child.jsonl", version="2.0.0",
                               lineage=[parent.id])
        chain = arena.lineage_chain(child.id)
        assert len(chain) == 2
        assert chain[0].name == "parent"
        assert chain[1].name == "child"

    def test_find_by_name(self):
        arena = DatasetArena()
        arena.register("my-data", "s3://b/d1.jsonl", version="1.0.0")
        arena.register("my-data", "s3://b/d2.jsonl", version="2.0.0")
        results = arena.find_by_name("my-data")
        assert len(results) == 2
        v1 = arena.find_by_name("my-data", version="1.0.0")
        assert len(v1) == 1


# --------------------------------------------------------------------------- #
# TrainingRunArena
# --------------------------------------------------------------------------- #
class _FakeRecorder:
    def __init__(self):
        self.captured = []
    def record(self, **kwargs):
        self.captured.append(kwargs)
        return kwargs
    def clear(self):
        self.captured.clear()


class TestTrainingRunArena:
    def _setup(self):
        from teacher_node.system_knowledge import SystemKnowledge
        from teacher_node.sanitizer import Sanitizer
        from teacher_node.experience_recorder import ExperienceRecorder

        sk = SystemKnowledge(Sanitizer())
        sanitizer = Sanitizer()
        exp = ExperienceRecorder(sk, sanitizer)
        exp_arena = ExperienceArena(exp)
        fb_arena = FeedbackArena()
        fail_arena = FailureArena(sanitizer)
        eval_arena = EvaluationArena()
        reward = RewardEngine(fb_arena)

        # Replace the experience recorder with our fake for predictable behavior
        exp_arena._recorder = _FakeRecorder()

        arena = TrainingRunArena(exp_arena, fb_arena, fail_arena, eval_arena, reward)
        return arena, exp_arena, fb_arena, fail_arena, eval_arena, reward

    def test_launch_and_dispatch(self):
        arena, *_ = self._setup()
        run = arena.launch(
            task_id="t1",
            config=TrainingConfig(
                model_revision="rev-1",
                base_model="base-1",
                dataset_ids=["ds-1"],
                max_steps=100,
            ),
        )
        assert run.status == TrainingStatus.PENDING
        arena.dispatch(run.id)
        assert run.status == TrainingStatus.DISPATCHED
        assert run.dispatched_at is not None

    def test_start_and_report_metrics(self):
        arena, *_ = self._setup()
        run = arena.launch(
            task_id="t1",
            config=TrainingConfig(model_revision="r1", base_model="b1", dataset_ids=["d1"]),
        )
        arena.dispatch(run.id)
        arena.start(run.id)
        assert run.status == TrainingStatus.RUNNING
        arena.report_metrics(run.id, TrainingMetrics(step=10, loss=0.5, elapsed_seconds=30.0))
        assert run.metrics.step == 10
        assert run.metrics.loss == 0.5

    def test_complete_success(self):
        arena, *_ = self._setup()
        run = arena.launch(
            task_id="t1",
            config=TrainingConfig(model_revision="r1", base_model="b1", dataset_ids=["d1"]),
        )
        arena.dispatch(run.id)
        arena.start(run.id)
        arena.complete(run.id, output_revision="new-rev-1")
        assert run.status == TrainingStatus.COMPLETE
        assert run.output_revision == "new-rev-1"

    def test_complete_failure_records_failure(self):
        arena, _, _, fail_arena, *_ = self._setup()
        run = arena.launch(
            task_id="t1",
            config=TrainingConfig(model_revision="r1", base_model="b1", dataset_ids=["d1"]),
        )
        arena.dispatch(run.id)
        arena.start(run.id)
        arena.complete(run.id, error="CUDA out of memory")
        assert run.status == TrainingStatus.FAILED
        failures = fail_arena.by_category(FailureCategory.OUT_OF_MEMORY)
        assert len(failures) == 1

    def test_complete_delegates_to_experience(self):
        arena, exp_arena, *_ = self._setup()
        run = arena.launch(
            task_id="t1",
            config=TrainingConfig(model_revision="r1", base_model="b1", dataset_ids=["d1"]),
        )
        arena.dispatch(run.id)
        arena.start(run.id)
        arena.complete(run.id, output_revision="rev-2")
        # Experience should have been captured
        assert len(exp_arena._recorder.captured) == 1
        assert exp_arena._recorder.captured[0]["outcome"].value == "success"

    def test_cancel(self):
        arena, *_ = self._setup()
        run = arena.launch(
            task_id="t1",
            config=TrainingConfig(model_revision="r1", base_model="b1", dataset_ids=["d1"]),
        )
        arena.dispatch(run.id)
        arena.start(run.id)
        arena.cancel(run.id)
        assert run.status == TrainingStatus.CANCELLED

    def test_pause_and_resume(self):
        arena, *_ = self._setup()
        run = arena.launch(
            task_id="t1",
            config=TrainingConfig(model_revision="r1", base_model="b1", dataset_ids=["d1"]),
        )
        arena.dispatch(run.id)
        arena.start(run.id)
        arena.pause(run.id)
        assert run.status == TrainingStatus.PAUSED
        arena.resume(run.id)
        assert run.status == TrainingStatus.RUNNING


# --------------------------------------------------------------------------- #
# ModelRevisionArena
# --------------------------------------------------------------------------- #
class TestModelRevisionArena:
    def test_register_revision(self):
        arena = ModelRevisionArena()
        rev = arena.register("my-model", "base-llama", version="2.0.0")
        assert rev.name == "my-model"
        assert rev.base_model == "base-llama"
        assert rev.version == "2.0.0"
        assert rev.status == RevisionStatus.DRAFT

    def test_best_revision(self):
        arena = ModelRevisionArena()
        arena.register("model-a", "base", version="1.0.0", tags=["test"])
        rev = arena.find_by_name("model-a")[0]
        arena.record_eval(rev.id, "mmlu", 0.85)
        arena.record_eval(rev.id, "gsm8k", 0.90)
        best = arena.best("model-a", metric="gsm8k")
        assert best is not None
        assert best.eval_scores["gsm8k"] == 0.90

    def test_lineage(self):
        arena = ModelRevisionArena()
        parent = arena.register("child", "parent-base", version="1.0.0")
        child = arena.register("child", "parent-base", version="2.0.0", parent_ids=[parent.id])
        chain = arena.lineage(child.id)
        assert len(chain) == 2
        assert chain[0].id == parent.id
        assert chain[1].id == child.id

    def test_promote_and_deprecate(self):
        arena = ModelRevisionArena()
        rev = arena.register("m", "base", version="1.0.0")
        arena.promote(rev.id)
        assert rev.status == RevisionStatus.READY
        arena.deprecate(rev.id, reason="superseded")
        assert rev.status == RevisionStatus.DEPRECATED

    def test_events(self):
        arena = ModelRevisionArena()
        rev = arena.register("m", "base", version="1.0.0")
        events = arena.events(rev.id)
        assert len(events) == 1
        assert events[0].event_type == "created"

    def test_by_tag(self):
        arena = ModelRevisionArena()
        arena.register("m1", "base", version="1.0.0", tags=["gpu", "prod"])
        arena.register("m2", "base", version="1.0.0", tags=["cpu", "test"])
        gpu_revs = arena.by_tag("gpu")
        assert len(gpu_revs) == 1
        assert gpu_revs[0].name == "m1"

    def test_ready_revisions(self):
        arena = ModelRevisionArena()
        arena.register("m1", "base", version="1.0.0")  # draft
        rev2 = arena.register("m2", "base", version="1.0.0")
        arena.promote(rev2.id)
        ready = arena.ready_revisions()
        assert len(ready) == 1
        assert ready[0].id == rev2.id


# --------------------------------------------------------------------------- #
# LessonArena
# --------------------------------------------------------------------------- #
class TestLessonArena:
    def test_recommend_matches_tags(self):
        from teacher_node.lesson_builder import LessonBuilder
        from teacher_node.system_knowledge import SystemKnowledge
        from teacher_node.sanitizer import Sanitizer

        sk = SystemKnowledge(Sanitizer())
        lb = LessonBuilder(sk, Sanitizer())
        # Create a lesson about OOM
        from teacher_node.experience_recorder import ExperienceRecorder, TaskOutcome
        rec = ExperienceRecorder(sk, Sanitizer())
        for i in range(3):
            rec.record(
                task_id=f"t{i}", category="training",
                outcome=TaskOutcome.FAILURE,
                resource_before={"cpu_percent": 20.0},
                resource_after={"cpu_percent": 95.0},
                error_category="OOM",
                tags=["gpu"],
            )
        lb.build_from_experiences(rec.all(), min_evidence=2)

        lesson_arena = LessonArena(lb, sk)

        # Create a task spec that should match lessons about GPU
        from learning_arena.tasks import TaskSpec
        spec = TaskSpec(name="train-gpu", category="training", tags=["failure", "OOM"])
        recs = lesson_arena.recommend(spec, min_confidence=0.0)
        assert len(recs) >= 1

    def test_apply_and_track(self):
        from teacher_node.lesson_builder import LessonBuilder
        from teacher_node.system_knowledge import SystemKnowledge
        from teacher_node.sanitizer import Sanitizer
        from teacher_node.experience_recorder import ExperienceRecorder, TaskOutcome

        sk = SystemKnowledge(Sanitizer())
        lb = LessonBuilder(sk, Sanitizer())
        rec = ExperienceRecorder(sk, Sanitizer())
        rec.record(task_id="t1", category="training", outcome=TaskOutcome.FAILURE,
                   error_category="OOM")
        rec.record(task_id="t2", category="training", outcome=TaskOutcome.FAILURE,
                   error_category="OOM")
        lessons = lb.build_from_experiences(rec.all(), min_evidence=2)
        assert len(lessons) >= 1

        lesson_arena = LessonArena(lb, sk)
        lesson_id = lessons[0].id
        assert lesson_arena.apply(lesson_id, "task-123")
        summary = lesson_arena.track_effectiveness()
        assert summary["total_applied"] >= 1
        assert lesson_id in summary["per_lesson"]

"""Unit tests for the model lifecycle registry, seeding and training policy."""
import pytest

from model_lifecycle.registry import ModelRegistry
from model_lifecycle.types import (
    LifecycleStage,
    ModelLifecycleType,
    PromotionState,
)
from model_lifecycle.training import (
    RegressionPolicy,
    TrainingLifecycle,
    TrainingPolicyError,
)


@pytest.fixture
def registry(tmp_path):
    return ModelRegistry(store_path=tmp_path / "lifecycle.jsonl")


def test_ensure_identity_immutable(registry):
    base = registry.ensure(
        provider="jarvis", model_id="jarvis-base-v1",
        lifecycle_type=ModelLifecycleType.JARVIS_BASE, actor="test",
    )
    again = registry.ensure(
        provider="jarvis", model_id="jarvis-base-v1",
        lifecycle_type=ModelLifecycleType.JARVIS_CANDIDATE,  # attempted re-type
        actor="test",
    )
    assert again.record_id == base.record_id
    assert again.lifecycle_type is ModelLifecycleType.JARVIS_BASE  # never re-typed


def test_human_gated_promotion_flow(registry):
    cand = registry.ensure(
        provider="jarvis", model_id="cand-x",
        lifecycle_type=ModelLifecycleType.JARVIS_CANDIDATE,
        stage=LifecycleStage.TRAINING, actor="train",
    )
    registry.mark_evaluated(cand.record_id, "eval")
    assert cand.promotion is PromotionState.PROMOTION_REVIEW
    with pytest.raises(ValueError):
        registry.human_approve(cand.record_id, "human")  # not yet requested
    registry.request_human_approval(cand.record_id, "reviewer")
    assert cand.promotion is PromotionState.HUMAN_APPROVAL
    approved = registry.human_approve(cand.record_id, "human")
    assert approved.promotion is PromotionState.APPROVED
    assert approved.lifecycle_stage is LifecycleStage.PROMOTED


def test_human_reject(registry):
    cand = registry.ensure(
        provider="jarvis", model_id="cand-y",
        lifecycle_type=ModelLifecycleType.JARVIS_CANDIDATE, actor="train",
    )
    registry.mark_evaluated(cand.record_id, "eval")
    registry.request_human_approval(cand.record_id, "reviewer")
    rejected = registry.human_reject(cand.record_id, "human", reason="does not regress")
    assert rejected.promotion is PromotionState.REJECTED
    assert rejected.lifecycle_stage is LifecycleStage.REJECTED


def test_lineage_walk(registry):
    base = registry.ensure(
        provider="jarvis", model_id="jarvis-base-v1",
        lifecycle_type=ModelLifecycleType.JARVIS_BASE, actor="test",
    )
    cand = registry.ensure(
        provider="jarvis", model_id="jarvis-cand-v1",
        lifecycle_type=ModelLifecycleType.JARVIS_CANDIDATE,
        parent_model=base.record_id, actor="test",
    )
    chain = registry.lineage(cand.record_id)
    assert [r["model_id"] for r in chain] == [cand.model_id, base.model_id]


def test_evaluation_record_appended(registry):
    cand = registry.ensure(
        provider="jarvis", model_id="cand-z",
        lifecycle_type=ModelLifecycleType.JARVIS_CANDIDATE, actor="train",
    )
    registry.record_evaluation(
        cand.record_id,
        "candidate_vs_baseline",
        {"metric": "pass@1", "value": 0.8, "baseline_value": 0.7},
        actor="eval",
    )
    snap = registry.snapshot()
    evals = cand.evaluation_results
    assert "candidate_vs_baseline" in evals
    assert evals["candidate_vs_baseline"]["value"] == 0.8
    assert snap["by_type"][ModelLifecycleType.JARVIS_CANDIDATE.value] == 1


def test_seed_brain_lineage_idempotent(tmp_path):
    from model_lifecycle.discovery import seed_brain_lineage

    reg = ModelRegistry(store_path=tmp_path / "lifecycle.jsonl")
    seed_brain_lineage(reg)
    n1 = len(reg.all_records())
    seed_brain_lineage(reg)
    assert len(reg.all_records()) == n1  # idempotent
    base = reg.list_by_type(ModelLifecycleType.JARVIS_BASE)[0]
    assert base.family == "jarvis-brain"
    cand = reg.list_by_type(ModelLifecycleType.JARVIS_CANDIDATE)[0]
    assert cand.parent_model == base.record_id


def test_regression_policy_unconfigured_needs_human():
    policy = RegressionPolicy()  # no thresholds -> cannot decide
    verdict = policy.decide({"accuracy": 0.70}, {"accuracy": 0.71})
    assert verdict["decision"] == "needs_human"
    assert "reason" in verdict


def test_regression_policy_configured_decides():
    policy = RegressionPolicy(min_improvement=0.05, max_regression=0.02)
    improved = policy.decide(
        {"accuracy": 0.70, "safety": 0.90}, {"accuracy": 0.77, "safety": 0.95}
    )
    assert improved["decision"] == "approve"
    regressed = policy.decide(
        {"accuracy": 0.70, "safety": 0.90}, {"accuracy": 0.77, "safety": 0.40}
    )
    assert regressed["decision"] == "reject"  # secondary metric regressed


def test_training_launch_requires_remote_and_dataset(registry):
    base = registry.ensure(
        provider="jarvis", model_id="jarvis-base-v1",
        lifecycle_type=ModelLifecycleType.JARVIS_BASE, actor="test",
    )
    lifecycle = TrainingLifecycle(registry)
    with pytest.raises(TrainingPolicyError):
        lifecycle.launch(
            base_record_id=base.record_id, dataset_ids=[], remote_target="",
            actor="test",
        )
    with pytest.raises(TrainingPolicyError):
        lifecycle.launch(
            base_record_id=base.record_id, dataset_ids=[], actor="test",
            remote_target="http://train.example",
        )
    run = lifecycle.launch(
        base_record_id=base.record_id, dataset_ids=["ds-1"],
        remote_target="http://train.example", actor="test",
    )
    assert run.status == "PENDING"
    assert run.candidate_record_id
    cand = registry.require(run.candidate_record_id)
    assert cand.parent_model == base.record_id
    assert "ds-1" in cand.metadata or cand.training_run_id == run.run_id


def test_training_complete_regression_gate(registry):
    base = registry.ensure(
        provider="jarvis", model_id="jarvis-base-v1",
        lifecycle_type=ModelLifecycleType.JARVIS_BASE, actor="test",
    )
    lifecycle = TrainingLifecycle(registry)
    run = lifecycle.launch(
        base_record_id=base.record_id, dataset_ids=["ds-1"],
        remote_target="http://train.example", actor="test",
    )
    result = lifecycle.complete(
        run.run_id, actor="trainer",
        metrics={"pass@1": 0.72},
        baseline_record_id=base.record_id,
        baseline_metrics={"pass@1": 0.70},
    )
    cand = registry.require(result.candidate_record_id)
    assert cand.lifecycle_stage is LifecycleStage.EVALUATION
    assert cand.promotion is PromotionState.PROMOTION_REVIEW
from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic import ValidationError

from jarvis_backend import core
from jarvis_backend.capabilities.bio_learner import BioLearnerCapability
from jarvis_backend.capability import ExecutionContext
from jarvis_backend.research.bio_learner import BioLearner
from jarvis_backend.routers.bio_growth import ReviewBody


@pytest.fixture(autouse=True)
def _isolate_stores():
    core.data.clear()
    yield
    core.data.clear()


def test_study_records_exposure_without_claiming_mastery():
    learner = BioLearner()
    learner.initialize()

    result = asyncio.run(learner.study_concept("mathematics", "arithmetic"))

    assert result["success"] is True
    assert result["assessment_required"] is True
    assert result["mastery_level"] == 0.0
    assert result["mastered_this_session"] is False
    assert learner.get_due_reviews()[0]["item_key"] == "mathematics.arithmetic"


def test_assessed_reviews_schedule_and_change_mastery():
    learner = BioLearner()
    learner.initialize()
    asyncio.run(learner.study_concept("mathematics", "arithmetic"))

    review = asyncio.run(learner.perform_review("mathematics.arithmetic", 5))

    assert review["success"] is True
    assert review["evidence_type"] == "self_assessed_recall"
    assert review["mastery_level"] == pytest.approx(0.2)
    assert review["interval_days"] == 1
    assert learner.get_due_reviews() == []
    assert learner._domains["mathematics"].maturity_score > 0


def test_review_api_contract_rejects_invalid_quality():
    with pytest.raises(ValidationError):
        ReviewBody(item_key="mathematics.arithmetic", quality=6)


def test_unknown_learning_domain_is_reported_without_key_error():
    learner = BioLearner()
    learner.initialize()

    assert learner.get_learning_path("not-a-domain") == {
        "error": "Unknown learning domain: not-a-domain"
    }


def test_capability_persists_and_isolates_user_learning_state():
    user_id = str(uuid.uuid4())
    context = ExecutionContext(
        user_id=user_id,
        session_id="test",
        correlation_id="bio-test",
    )
    capability = BioLearnerCapability()
    studied = asyncio.run(capability.execute({
        "action": "study_concept",
        "domain": "mathematics",
        "concept": "arithmetic",
    }, context))
    reviewed = asyncio.run(capability.execute({
        "action": "perform_review",
        "item_key": "mathematics.arithmetic",
        "quality": 5,
    }, context))

    assert studied.success is True
    assert reviewed.success is True
    assert core.get_store("bio_learning").load()[user_id]["concepts"][
        "mathematics.arithmetic"
    ]["mastery_level"] == pytest.approx(0.2)

    core.data.pop("bio_learning")
    restarted_capability = BioLearnerCapability()
    restored = restarted_capability._get_learner(user_id)
    unrelated = restarted_capability._get_learner("user-two")
    assert restored._concepts["mathematics.arithmetic"].mastery_level == pytest.approx(0.2)
    assert unrelated._concepts["mathematics.arithmetic"].mastery_level == 0.0

"""Unit tests for the curriculum dataset builder (learning_arena.dataset_builder)."""
import pytest

from learning_arena.dataset_builder import CurriculumDatasetBuilder, DatasetQuality
from learning_arena.lesson_gate import LessonGate


def _verified_lessons(n=3):
    gate = LessonGate()
    for i in range(n):
        gate.submit(
            title=f"lesson {i}",
            concept="Programming",
            domain="Programming",
            difficulty=i + 1,
            difficulty_label="basic",
            problem_id=f"p-{i}",
            problem=f"practice problem number {i}",
            expected_format="runnable python",
            verified_solution=f"def solve_{i}():\n    return {i}",
            evidence_ids=[f"ev-{i}"],
        )
        lesson = gate.get(
            [l for l in gate.lessons() if l.problem_id == f"p-{i}"][0].lesson_id
        )
        gate.verify(
            lesson.lesson_id, {"outcome": "VERIFIED", "method": "sandbox"}, actor="test"
        )
    return gate


def test_build_publishes_verified_examples():
    gate = _verified_lessons(3)
    builder = CurriculumDatasetBuilder(gate)
    rev = builder.build(name="programming-verified")
    assert rev.version == 1
    assert rev.example_count == 3
    assert rev.quality_status == DatasetQuality.QUALIFIED
    assert rev.dedup["strategy"] == "content_hash"
    assert rev.dedup["selected"] == 3


def test_immutable_versioning_same_payload():
    gate = _verified_lessons(3)
    builder = CurriculumDatasetBuilder(gate)
    v1 = builder.build(name="programming-verified")
    v2 = builder.build(name="programming-verified")  # identical lessons -> same ds id, v2
    assert v1.dataset_id == v2.dataset_id
    assert v2.version == 2
    first = builder.get(v1.dataset_id, 1)
    second = builder.get(v1.dataset_id, 2)
    assert first.to_dict() == v1.to_dict()  # v1 never mutated
    assert first.content_hash == second.content_hash  # same payload
    assert first.version != second.version  # version is part of identity, not content


def test_changed_lesson_yields_new_dataset_id():
    gate = _verified_lessons(3)
    builder = CurriculumDatasetBuilder(gate)
    before = builder.build(name="programming-verified")
    # Add a fourth, different verified lesson: content changes -> new dataset.
    gate.submit(
        title="extra", concept="Programming", domain="Programming", difficulty=4,
        difficulty_label="advanced", problem_id="p-extra",
        problem="an extra distinct problem", expected_format="python code",
        verified_solution="def extra():\n    return 4", evidence_ids=["ev-extra"],
    )
    new_lesson = gate.lessons()[-1]
    gate.verify(
        new_lesson.lesson_id, {"outcome": "VERIFIED", "method": "sandbox"}, actor="test"
    )
    after = builder.build(name="programming-verified")
    assert after.dataset_id != before.dataset_id
    assert after.example_count == 4


def test_content_hash_is_real_payload_hash():
    gate = _verified_lessons(3)
    builder = CurriculumDatasetBuilder(gate)
    rev = builder.build(name="programming-verified")
    from learning_arena.dataset_builder import compute_content_hash

    assert rev.content_hash == compute_content_hash(rev.examples)


def test_min_quality_filter_drops_weak_lessons():
    gate = LessonGate()
    gate.submit(
        title="weak", concept="Programming", domain="Programming", difficulty=1,
        difficulty_label="basic", problem_id="p-w", problem="",
        verified_solution="", evidence_ids=[],
    )
    builder = CurriculumDatasetBuilder(gate)
    rev = builder.build(name="programming-verified", min_quality_score=0.5)
    assert rev.example_count == 0
    assert "min_quality_score" in rev.filtering_policy


def test_persisted_store_reloads_immutably(tmp_path):
    gate = _verified_lessons(2)
    store = tmp_path / "ds.jsonl"
    builder = CurriculumDatasetBuilder(gate, store_path=store)
    builder.build(name="persisted")
    reloaded = CurriculumDatasetBuilder(LessonGate(), store_path=store)
    revs = reloaded.all_datasets()
    assert len(revs) == 1
    assert revs[0].example_count == 2


def test_dedup_report_counts_duplicates():
    from dataclasses import replace

    from learning_arena.lesson_gate import CurriculumLesson

    gate = _verified_lessons(3)
    # White-box: the gate normally prevents duplicates at submit time, so the
    # builder's content-hash dedup is the second line of defense. Inject a
    # second VERIFIED row carrying the same content hash as an existing lesson.
    original = gate.lessons()[0]
    clone = replace(original, lesson_id="dup-" + original.lesson_id)
    gate._lessons["dup-" + original.lesson_id] = clone  # noqa: SLF001
    builder = CurriculumDatasetBuilder(gate)
    rev = builder.build(name="programming-verified")
    assert rev.dedup["strategy"] == "content_hash"
    assert rev.dedup["duplicates_removed"] == 1
    assert rev.dedup["candidates"] == 4
    assert rev.example_count == 3
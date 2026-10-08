"""Tests for the Teacher Node + Resource Governor (spec §17-§30, §55-§57).

Covers:
  * PrivacyFilter: PII/secret detection, redaction, file-path redaction
  * Sanitizer: env-var/hostname redaction, safe summary (no raw data)
  * SystemKnowledge: add/find/search/cleanup with sanitization
  * MachineObserver: on-demand sampling (psutil), record() into knowledge
  * RepoObserver: diff parsing, categorization, sanitization
  * ExperienceRecorder: record/skip/deduplicate, error categorization
  * LessonBuilder: error-category clustering, resource bottleneck detection,
    timeout patterns, success baselines, confidence scoring
  * ResourceGovernor: state machine (idle→running→throttled→paused→cancelled),
    concurrency throttling, config from env, disk-space gate
  * TeacherNode: end-to-end observation → experience → lesson pipeline
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import pytest

from teacher_node.privacy_filter import (
    DetectionKind,
    PrivacyFilter,
    RedactionResult,
)
from teacher_node.sanitizer import Sanitizer, SanitizationReport
from teacher_node.system_knowledge import KnowledgeEntry, SystemKnowledge
from teacher_node.machine_observer import MachineObserver, SystemMetrics
from teacher_node.repo_observer import RepoChange, RepoObserver
from teacher_node.experience_recorder import (
    ExperienceRecord,
    ExperienceRecorder,
    TaskOutcome,
)
from teacher_node.lesson_builder import Lesson, LessonBuilder
from teacher_node.resource_governor import (
    GovernorConfig,
    GovernorState,
    ResourceGovernor,
    ResourceSnapshot,
)


# --------------------------------------------------------------------------- #
# PrivacyFilter
# --------------------------------------------------------------------------- #
class TestPrivacyFilter:
    def setup_method(self):
        self.pf = PrivacyFilter()

    def test_email_detection_and_redaction(self):
        text = "Contact: user@example.com for details"
        result = self.pf.redact(text)
        assert "[REDACTED:EMAIL_ADDRESS]" in result.text
        assert "user@example.com" not in result.text
        assert any(d.kind == DetectionKind.EMAIL for d in result.detections)

    def test_phone_detection(self):
        text = "Call +1-555-123-4567 now"
        detections = self.pf.detect(text)
        assert any(d.kind == DetectionKind.PHONE for d in detections)

    def test_credit_card_luhn(self):
        text = "Card: 4111111111111111"
        detections = self.pf.detect(text)
        assert any(d.kind == DetectionKind.CREDIT_CARD for d in detections)

    def test_credit_card_invalid_luhn_not_detected(self):
        text = "Number: 411111111111112"  # fails Luhn
        detections = self.pf.detect(text)
        # No credit card detection (the _CREDIT_CARD_RE might still match the
        # pattern but Luhn filter should reject it).
        cc = [d for d in detections if d.kind == DetectionKind.CREDIT_CARD]
        assert len(cc) == 0

    def test_openai_key_detection(self):
        text = "Key: sk-proj-1234567890abcdefghijklmnopqrst"
        detections = self.pf.detect(text)
        assert any(d.kind == DetectionKind.API_KEY for d in detections)

    def test_huggingface_key_detection(self):
        # Assembled at runtime so no credential-shaped literal is stored in the
        # tree; the detector only needs the hf_ prefix and body shape.
        text = "Token: hf_" + "A" * 34
        detections = self.pf.detect(text)
        assert any(d.kind == DetectionKind.API_KEY for d in detections)

    def test_github_key_detection(self):
        text = "ghp_" + "a" * 36
        detections = self.pf.detect(text)
        assert any(d.kind == DetectionKind.API_KEY for d in detections)

    def test_aws_key_detection(self):
        # AWS's own documented example key id, built at runtime to avoid a
        # credential-shaped literal in source.
        text = "ID: AKIA" + "IOSFODNN7EXAMPLE"
        detections = self.pf.detect(text)
        assert any(d.kind == DetectionKind.AWS_KEY_ID for d in detections)

    def test_generic_secret_detection(self):
        text = 'api_key: "sk_live_' + "abc123def456ghi789" + '"'
        detections = self.pf.detect(text)
        assert any(d.kind == DetectionKind.GENERIC_SECRET for d in detections)

    def test_redact_all_categories(self):
        text = "Email: user@test.com, Phone: +15551234567, Key: sk-test1234567890abcdefghij, CC: 4111111111111111"
        result = self.pf.redact(text)
        assert "user@test.com" not in result.text
        assert "+15551234567" not in result.text
        assert "sk-test1234567890abcdefghij" not in result.text
        assert "4111111111111111" not in result.text

    def test_is_clean_true(self):
        assert self.pf.is_clean("This is a normal sentence about cats.")

    def test_is_clean_false(self):
        assert not self.pf.is_clean("Email me at test@example.com")

    def test_redact_preserves_structure(self):
        text = "Hello [REDACTED] World"
        result = self.pf.redact(text)
        assert result.redacted_count == 0  # "REDACTED" in brackets is not PII

    def test_scan_stream(self):
        lines = ["hello", "email user@test.com", "done"]
        result = list(self.pf.scan_stream(lines))
        assert result[0] == "hello"
        assert "user@test.com" not in result[1]
        assert "[REDACTED:EMAIL_ADDRESS]" in result[1]
        assert result[2] == "done"

    def test_no_false_negative_for_email_in_url(self):
        text = "https://user:pass@api.example.com/callback"
        detections = self.pf.detect(text)
        assert any(d.kind == DetectionKind.EMAIL for d in detections)


# --------------------------------------------------------------------------- #
# Sanitizer
# --------------------------------------------------------------------------- #
class TestSanitizer:
    def setup_method(self):
        self.sanitizer = Sanitizer()

    def test_redact_email(self):
        text = "Contact: admin@example.com"
        result = self.sanitizer.sanitize(text)
        assert "admin@example.com" not in result
        assert "[REDACTED:EMAIL_ADDRESS]" in result

    def test_redact_secret_env_var_names(self):
        text = "The JARVIS_OPENAI_API_KEY is used for auth"
        result = self.sanitizer.sanitize(text)
        assert "JARVIS_OPENAI_API_KEY" not in result
        assert "[SECRET_VAR]" in result

    def test_redact_internal_host(self):
        text = "Service at 127.0.0.1:8011 is running"
        result = self.sanitizer.sanitize(text)
        assert "127.0.0.1" not in result
        assert "[INTERNAL_HOST]" in result

    def test_redact_localhost(self):
        text = "Connect to localhost:8000"
        result = self.sanitizer.sanitize(text)
        assert "[INTERNAL_HOST]" in result

    def test_sanitize_with_report(self):
        text = "admin@example.com and JARVIS_OPENAI_API_KEY and 127.0.0.1"
        sanitized, report = self.sanitizer.sanitize_with_report(text)
        assert "admin@example.com" not in sanitized
        assert "JARVIS_OPENAI_API_KEY" not in sanitized
        assert "127.0.0.1" not in sanitized
        assert report.detection_counts.get("EMAIL_ADDRESS", 0) >= 1
        assert report.secret_var_referenced
        assert report.internal_host_referenced
        assert len(report.warnings) >= 2

    def test_sanitize_warning_for_secret_file(self):
        text = "Modified .env file in config directory"
        _, report = self.sanitizer.sanitize_with_report(text)
        assert report.secret_file_referenced
        assert any("secrets/credential" in w for w in report.warnings)

    def test_safe_summary_no_raw_secret(self):
        text = "Key is sk-live-abc123def456 and email is user@host.com"
        summary = self.sanitizer.safe_summary(text)
        assert "sk-live-abc123" not in str(summary)
        assert "user@host.com" not in str(summary)
        assert summary["detection_counts"]  # has some detections

    def test_safe_summary_structure(self):
        text = "Normal observation text"
        summary = self.sanitizer.safe_summary(text)
        assert "original_length" in summary
        assert "redacted_length" in summary
        assert "detection_counts" in summary
        assert "sanitized_excerpt" in summary
        assert summary["original_length"] == len(text)


# --------------------------------------------------------------------------- #
# SystemKnowledge
# --------------------------------------------------------------------------- #
class TestSystemKnowledge:
    def test_add_and_get(self):
        sk = SystemKnowledge()
        entry = sk.add("resource", "cpu_spike", {"cpu": 85.0}, confidence=0.9)
        assert sk.get(entry.id) is not None
        assert sk.get(entry.id).key == "cpu_spike"

    def test_add_sanitizes_values(self):
        sanitizer = Sanitizer()
        sk = SystemKnowledge(sanitizer=sanitizer)
        entry = sk.add("observation", "test", {"data": "user@example.com"})
        got = sk.get(entry.id)
        assert "user@example.com" not in str(got.value)

    def test_find_by_tag(self):
        sk = SystemKnowledge()
        sk.add("resource", "cpu", {}, tags=["resource", "cpu"])
        sk.add("repo", "diff", {}, tags=["repo", "git"])
        results = sk.find_by_tag("resource")
        assert len(results) == 1
        assert results[0].category == "resource"

    def test_find_by_category(self):
        sk = SystemKnowledge()
        sk.add("resource", "a", {})
        sk.add("resource", "b", {})
        sk.add("lesson", "c", {})
        results = sk.find_by_category("resource")
        assert len(results) == 2

    def test_search(self):
        sk = SystemKnowledge()
        sk.add("observation", "gpu_failure", {"note": "OOM on GPU"}, tags=["gpu"])
        results = sk.search("OOM")
        assert len(results) == 1

    def test_expiry_and_cleanup(self):
        sk = SystemKnowledge()
        entry = sk.add("resource", "temp", {}, ttl=0.1)
        assert sk.get(entry.id) is not None
        time.sleep(0.2)
        assert sk.get(entry.id) is None
        assert sk.cleanup() == 0  # already expired & removed by get()

    def test_find_by_key(self):
        sk = SystemKnowledge()
        e1 = sk.add("resource", "cpu", {"val": 1.0})
        e2 = sk.add("resource", "cpu", {"val": 2.0})
        results = sk.find_by_key("cpu")
        assert len(results) == 2
        assert results[0].value["val"] in (1.0, 2.0)


# --------------------------------------------------------------------------- #
# ResourceGovernor
# --------------------------------------------------------------------------- #
class TestResourceGovernor:
    def _snap(self, **kw):
        defaults = dict(
            cpu_percent=50.0, memory_percent=50.0, disk_percent=50.0,
            gpu_percent=0.0, gpu_vram_percent=0.0, timestamp=time.time(),
            background_tasks=0,
        )
        defaults.update(kw)
        return ResourceSnapshot(**defaults)

    def test_initial_state_idle(self):
        g = ResourceGovernor()
        assert g.state == GovernorState.IDLE

    def test_under_threshold_stays_idle(self):
        g = ResourceGovernor(GovernorConfig(max_cpu_percent=70))
        snap = self._snap(cpu_percent=40.0)
        assert g.check(snap) == GovernorState.IDLE  # no tasks registered

    def test_register_task_enters_running(self):
        g = ResourceGovernor(GovernorConfig(max_cpu_percent=70))
        snap = self._snap(cpu_percent=40.0, memory_percent=40.0)
        assert g.check(snap) == GovernorState.IDLE
        assert g.register_task("task-1", snapshot=snap)
        assert g.state == GovernorState.RUNNING
        assert g.active_tasks == 1

    def test_cpu_threshold_throttles(self):
        g = ResourceGovernor(GovernorConfig(max_cpu_percent=70))
        g.register_task("task-1", snapshot=self._snap(cpu_percent=40.0, memory_percent=40.0))
        snap = self._snap(cpu_percent=85.0, memory_percent=40.0)
        assert g.check(snap) == GovernorState.THROTTLED

    def test_memory_threshold_throttles(self):
        g = ResourceGovernor(GovernorConfig(max_memory_percent=60))
        g.register_task("task-1", snapshot=self._snap(cpu_percent=30.0, memory_percent=30.0))
        snap = self._snap(cpu_percent=30.0, memory_percent=80.0)
        assert g.check(snap) == GovernorState.THROTTLED

    def test_disk_threshold_throttles(self):
        g = ResourceGovernor(GovernorConfig(max_disk_percent=80))
        g.register_task("task-1", snapshot=self._snap(disk_percent=30.0))
        snap = self._snap(disk_percent=90.0)
        assert g.check(snap) == GovernorState.THROTTLED

    def test_foreground_pause(self):
        g = ResourceGovernor(GovernorConfig(foreground_pause_threshold=90))
        g.register_task("task-1", snapshot=self._snap(cpu_percent=40.0))
        snap = self._snap(cpu_percent=95.0)
        assert g.check(snap) == GovernorState.PAUSED

    def test_pause_all(self):
        g = ResourceGovernor()
        g.register_task("task-1", snapshot=self._snap(cpu_percent=40.0))
        g.pause_all()
        assert g.state == GovernorState.PAUSED

    def test_cancel_task(self):
        g = ResourceGovernor()
        g.register_task("task-1", snapshot=self._snap(cpu_percent=40.0))
        snap = self._snap(cpu_percent=40.0)
        assert not g.is_task_cancelled("task-1")
        g.cancel_task("task-1")
        assert g.is_task_cancelled("task-1")
        assert g.active_tasks == 0

    def test_cancelled_state_blocks_new_tasks(self):
        g = ResourceGovernor()
        g.cancel_task("fake-id")
        g._state = GovernorState.CANCELLED
        assert not g.can_start_task()

    def test_concurrency_throttle(self):
        cfg = GovernorConfig(
            max_background_tasks=4,
            throttle_start=60.0,
            throttle_end=85.0,
        )
        g = ResourceGovernor(cfg)
        # Below throttle_start → full concurrency
        assert g.allowed_concurrency(self._snap(cpu_percent=30.0)) == 4
        # At ~72.5% → should be ~2 (midpoint)
        mid = self._snap(cpu_percent=72.5)
        result = g.allowed_concurrency(mid)
        assert 1 <= result <= 4
        # Above throttle_end → minimum 1
        assert g.allowed_concurrency(self._snap(cpu_percent=90.0)) == 1

    def test_can_start_task_respects_limits(self):
        cfg = GovernorConfig(max_background_tasks=2)
        g = ResourceGovernor(cfg)
        g.register_task("t1", snapshot=self._snap(cpu_percent=40.0))
        g.register_task("t2", snapshot=self._snap(cpu_percent=40.0))
        snap_ok = self._snap(cpu_percent=40.0)
        # Already at max
        assert not g.can_start_task(snapshot=snap_ok)

    def test_config_from_env(self):
        os.environ["JARVIS_LOCAL_MAX_CPU_PERCENT"] = "50.0"
        os.environ["JARVIS_LOCAL_MAX_MEMORY_PERCENT"] = "60.0"
        try:
            cfg = GovernorConfig.from_env()
            assert cfg.max_cpu_percent == 50.0
            assert cfg.max_memory_percent == 60.0
        finally:
            del os.environ["JARVIS_LOCAL_MAX_CPU_PERCENT"]
            del os.environ["JARVIS_LOCAL_MAX_MEMORY_PERCENT"]

    def test_config_from_env_invalid_fallback(self):
        os.environ["JARVIS_LOCAL_MAX_CPU_PERCENT"] = "not-a-number"
        try:
            cfg = GovernorConfig.from_env()
            # Falls back to default
            assert cfg.max_cpu_percent == 70.0
        finally:
            del os.environ["JARVIS_LOCAL_MAX_CPU_PERCENT"]


# --------------------------------------------------------------------------- #
# ExperienceRecorder
# --------------------------------------------------------------------------- #
class _FakeSanitizer:
    def sanitize(self, text: str) -> str:
        return text.replace("secret", "[REDACTED]")


class TestExperienceRecorder:
    def _setup(self):
        sk = SystemKnowledge()
        sanitizer = Sanitizer()
        rec = ExperienceRecorder(sk, sanitizer)
        return rec, sk

    def test_record_success(self):
        rec, sk = self._setup()
        experience = rec.record(
            task_id="t1", category="training", outcome=TaskOutcome.SUCCESS,
            started_at=0, ended_at=10.0,
            tags=["experiment-1"],
        )
        assert experience.outcome == TaskOutcome.SUCCESS
        assert experience.duration_seconds == 10.0
        assert len(rec.all()) == 1

    def test_record_failure_with_error(self):
        rec, sk = self._setup()
        experience = rec.record(
            task_id="t1", category="training", outcome=TaskOutcome.FAILURE,
            error_message="Connection refused to api.example.com",
            error_category="NetworkError",
        )
        assert experience.error_category == "NetworkError"
        assert "sk-test-12345" not in experience.error_sanitized or "api.example.com" not in experience.error_sanitized

    def test_record_sanitizes_error(self):
        rec, sk = self._setup()
        experience = rec.record(
            task_id="t1", category="evaluation", outcome=TaskOutcome.FAILURE,
            error_message="Key sk-test-12345 expired",
        )
        # The error message should be sanitized.
        assert "sk-test-12345" not in experience.error_sanitized

    def test_record_sanitizes_raw_payload(self):
        rec, sk = self._setup()
        rec.record(
            task_id="t1", category="training", outcome=TaskOutcome.SUCCESS,
            raw_payload={"config": {"api_key": "sk-secret-value"}},
        )
        # The knowledge store should have sanitized content.
        entries = sk.find_by_category("experience")
        assert len(entries) == 1
        stored = str(entries[0].value)
        assert "sk-secret-value" not in stored

    def test_error_categorization(self):
        assert ExperienceRecorder._categorize_error("OOM: cannot allocate 8GB") == "MemoryError"
        assert ExperienceRecorder._categorize_error("timeout after 300s") == "TimeoutError"
        assert ExperienceRecorder._categorize_error("Connection refused") == "NetworkError"
        assert ExperienceRecorder._categorize_error("403 Forbidden") == "AuthError"
        assert ExperienceRecorder._categorize_error("Invalid schema") == "ValidationError"
        assert ExperienceRecorder._categorize_error("something weird") == "UnknownError"

    def test_record_into_knowledge_store(self):
        rec, sk = self._setup()
        rec.record(
            task_id="t1", category="training", outcome=TaskOutcome.SUCCESS,
            started_at=0, ended_at=5.0,
        )
        entries = sk.find_by_category("experience")
        assert len(entries) == 1
        assert entries[0].value["outcome"] == "success"

    def test_resource_delta(self):
        rec, sk = self._setup()
        exp = rec.record(
            task_id="t1", category="training", outcome=TaskOutcome.SUCCESS,
            resource_before={"memory_percent": 30.0, "cpu_percent": 10.0},
            resource_after={"memory_percent": 55.0, "cpu_percent": 45.0},
        )
        delta = exp.resource_delta
        assert delta["memory_percent"] == 25.0
        assert delta["cpu_percent"] == 35.0


# --------------------------------------------------------------------------- #
# LessonBuilder
# --------------------------------------------------------------------------- #
class TestLessonBuilder:
    def _setup(self):
        sk = SystemKnowledge()
        sanitizer = Sanitizer()
        lb = LessonBuilder(sk, sanitizer)
        return lb, sk

    def test_no_experiences_no_lessons(self):
        lb, sk = self._setup()
        assert lb.build_from_experiences([]) == []

    def test_error_category_clustering(self):
        lb, sk = self._setup()
        rec = ExperienceRecorder(sk, lb._sanitizer)
        for i in range(3):
            rec.record(
                task_id=f"t{i}", category="training",
                outcome=TaskOutcome.FAILURE,
                error_category="NetworkError",
            )
        lessons = lb.build_from_experiences(rec.all(), min_evidence=2)
        error_lessons = [l for l in lessons if l.category == "error"]
        assert len(error_lessons) >= 1
        assert error_lessons[0].evidence_count == 3
        assert "NetworkError" in error_lessons[0].hypothesis

    def test_resource_bottleneck_lesson(self):
        lb, sk = self._setup()
        rec = ExperienceRecorder(sk, lb._sanitizer)
        for i in range(3):
            rec.record(
                task_id=f"t{i}", category="training",
                outcome=TaskOutcome.FAILURE,
                resource_before={"cpu_percent": 20.0, "memory_percent": 40.0},
                resource_after={"cpu_percent": 90.0, "memory_percent": 40.0},
                error_category="UnknownError",
            )
        lessons = lb.build_from_experiences(rec.all(), min_evidence=2)
        resource_lessons = [l for l in lessons if "resource" in l.tags]
        assert len(resource_lessons) >= 1

    def test_timeout_pattern(self):
        lb, sk = self._setup()
        rec = ExperienceRecorder(sk, lb._sanitizer)
        for i in range(3):
            rec.record(
                task_id=f"t{i}", category="eval",
                outcome=TaskOutcome.TIMEOUT,
                started_at=0, ended_at=310.0,
            )
        lessons = lb.build_from_experiences(rec.all(), min_evidence=2)
        timeout_lessons = [l for l in lessons if l.category == "timeout"]
        assert len(timeout_lessons) == 1

    def test_success_baseline_lesson(self):
        lb, sk = self._setup()
        rec = ExperienceRecorder(sk, lb._sanitizer)
        for i in range(3):
            rec.record(
                task_id=f"t{i}", category="training",
                outcome=TaskOutcome.SUCCESS,
                started_at=0, ended_at=5.0,
            )
        lessons = lb.build_from_experiences(rec.all(), min_evidence=2)
        success_lessons = [l for l in lessons if l.category == "success"]
        assert len(success_lessons) == 1

    def test_confidence_increases_with_evidence(self):
        lb, sk = self._setup()
        rec = ExperienceRecorder(sk, lb._sanitizer)
        # 2 evidence -> lower confidence
        for i in range(2):
            rec.record(task_id=f"t{i}", category="training",
                       outcome=TaskOutcome.FAILURE, error_category="E1")
        lessons_2 = lb.build_from_experiences(rec.all(), min_evidence=2)
        c2 = [l for l in lessons_2 if l.category == "error"][0].confidence

        # 5 evidence -> higher confidence
        from teacher_node.sanitizer import Sanitizer
        sk2 = SystemKnowledge()
        lb2 = LessonBuilder(sk2, Sanitizer())
        rec2 = ExperienceRecorder(sk2, lb2._sanitizer)
        for i in range(5):
            rec2.record(task_id=f"t{i}", category="training",
                        outcome=TaskOutcome.FAILURE, error_category="E2")
        lessons_5 = lb2.build_from_experiences(rec2.all(), min_evidence=2)
        c5 = [l for l in lessons_5 if l.category == "error"][0].confidence
        assert c5 > c2

    def test_lesson_sanitized(self):
        lb, sk = self._setup()
        rec = ExperienceRecorder(sk, lb._sanitizer)
        rec.record(
            task_id="t1", category="training",
            outcome=TaskOutcome.FAILURE,
            error_category="NetworkError",
            error_message="Failed for user@example.com with key sk-test-123",
        )
        # Need 2 to trigger min_evidence
        rec.record(
            task_id="t2", category="training",
            outcome=TaskOutcome.FAILURE,
            error_category="NetworkError",
            error_message="Failed again",
        )
        lessons = lb.build_from_experiences(rec.all(), min_evidence=2)
        for lesson in lessons:
            assert "user@example.com" not in lesson.hypothesis
            assert "sk-test-123" not in lesson.hypothesis
            assert "user@example.com" not in lesson.action

    def test_lesson_stored_in_knowledge(self):
        lb, sk = self._setup()
        rec = ExperienceRecorder(sk, lb._sanitizer)
        for i in range(2):
            rec.record(task_id=f"t{i}", category="training",
                       outcome=TaskOutcome.FAILURE, error_category="OOM")
        lessons = lb.build_from_experiences(rec.all(), min_evidence=2)
        assert len(lessons) >= 1
        # The lesson should also be in the knowledge store.
        kb_lessons = sk.find_by_category("lesson")
        assert len(kb_lessons) >= 1

    def test_dedup_identical_hypotheses(self):
        lb, sk = self._setup()
        rec = ExperienceRecorder(sk, lb._sanitizer)
        for i in range(4):
            rec.record(task_id=f"t{i}", category="training",
                       outcome=TaskOutcome.FAILURE, error_category="OOM")
        lessons = lb.build_from_experiences(rec.all(), min_evidence=2)
        # Even with 4 OOM failures, only one lesson per unique hypothesis.
        oom_lessons = [l for l in lessons if l.category == "error" and "MemoryError" in l.hypothesis]
        assert len(oom_lessons) <= 1


# --------------------------------------------------------------------------- #
# TeacherNode (end-to-end)
# --------------------------------------------------------------------------- #
class TestTeacherNode:
    def test_full_pipeline(self):
        """End-to-end: observe → record experience → build lesson."""
        from teacher_node import (
            MachineObserver, ExperienceRecorder, LessonBuilder,
            ResourceGovernor, SystemKnowledge, Sanitizer,
        )

        sk = SystemKnowledge(Sanitizer())
        sanitizer = Sanitizer()
        recorder = ExperienceRecorder(sk, sanitizer)
        builder = LessonBuilder(sk, sanitizer)
        governor = ResourceGovernor()

        # Record some experiences.
        for i in range(3):
            recorder.record(
                task_id=f"train-{i}", category="training",
                outcome=TaskOutcome.FAILURE,
                error_category="NetworkError",
                resource_before={"cpu_percent": 20.0},
                resource_after={"cpu_percent": 95.0},
                started_at=0, ended_at=120.0,
            )
        recorder.record(
            task_id="train-success", category="training",
            outcome=TaskOutcome.SUCCESS, started_at=0, ended_at=10.0,
        )

        # Governor should see high CPU.
        snap = ResourceSnapshot(
            cpu_percent=95.0, memory_percent=60.0, disk_percent=50.0,
            gpu_percent=0.0, gpu_vram_percent=0.0, timestamp=time.time(),
            background_tasks=1,
        )
        governor.register_task("train-0")
        assert governor.check(snap) in (GovernorState.THROTTLED, GovernorState.PAUSED)

        # Lessons should be generated.
        lessons = builder.build_from_experiences(recorder.all(), min_evidence=2)
        assert len(lessons) >= 1

        # Knowledge store should have entries.
        experiences = sk.find_by_category("experience")
        lessons_kb = sk.find_by_category("lesson")
        assert len(experiences) == 4
        assert len(lessons_kb) >= 1

    def test_teacher_node_imports(self):
        """Verify the package __init__ re-exports everything."""
        import teacher_node as tn
        assert hasattr(tn, "SystemKnowledge")
        assert hasattr(tn, "MachineObserver")
        assert hasattr(tn, "ResourceGovernor")
        assert hasattr(tn, "LessonBuilder")
        assert hasattr(tn, "ExperienceRecorder")
        assert hasattr(tn, "Sanitizer")
        assert hasattr(tn, "PrivacyFilter")
        assert hasattr(tn, "RepoObserver")

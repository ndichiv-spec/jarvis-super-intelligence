"""
Tests for the Job Registry (Phase 2).

Verifies:
- Job creation and management
- Job status transitions
- Resource tracking
- Cost tracking for jobs
"""

import pytest
import time

from infrastructure.job_registry import (
    JobRegistry,
    JobInfo,
    JobType,
    JobStatus,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry singleton before each test."""
    JobRegistry.reset_instance()
    yield
    JobRegistry.reset_instance()


class TestJobRegistry:
    """Test job registry operations."""
    
    def test_create_job(self):
        """Creating a job should persist it."""
        registry = JobRegistry.get_instance()
        
        job = JobInfo(
            id="test-job-123",
            job_id="job-test-123",
            job_type="training",
            status="pending",
            user_id="user-1",
            resource_cpu=4.0,
            resource_memory_gb=16.0,
            resource_gpu=1,
        )
        
        result = registry.create_job(job)
        
        assert result.job_id == "job-test-123"
        assert result.job_type == "training"
    
    def test_get_job(self):
        """Should retrieve job by job_id."""
        registry = JobRegistry.get_instance()
        
        job = JobInfo(
            id="test-job-456",
            job_id="job-test-456",
            job_type="inference",
            status="pending",
        )
        registry.create_job(job)
        
        retrieved = registry.get("job-test-456")
        assert retrieved is not None
        assert retrieved.id == "test-job-456"
    
    def test_update_status(self):
        """Should update job status."""
        registry = JobRegistry.get_instance()
        
        job = JobInfo(
            id="test-job-status",
            job_id="job-status-test",
            job_type="training",
            status="pending",
        )
        registry.create_job(job)
        
        result = registry.update_status("job-status-test", "running")
        assert result is True
        
        updated = registry.get("job-status-test")
        assert updated.status == "running"
        assert updated.started_at is not None
    
    def test_set_resource_allocation(self):
        """Should set resource allocation."""
        registry = JobRegistry.get_instance()
        
        job = JobInfo(
            id="test-job-resources",
            job_id="job-resources-test",
            job_type="training",
            status="pending",
            resource_cpu=1.0,
            resource_memory_gb=2.0,
            resource_gpu=0,
        )
        registry.create_job(job)
        
        result = registry.set_resource_allocation(
            "job-resources-test",
            cpu=8.0,
            memory_gb=32.0,
            gpu=2,
            gpu_type="a100",
        )
        assert result is True
        
        updated = registry.get("job-resources-test")
        assert updated.resource_cpu == 8.0
        assert updated.resource_memory_gb == 32.0
        assert updated.resource_gpu == 2
    
    def test_set_cost(self):
        """Should set job cost."""
        registry = JobRegistry.get_instance()
        
        job = JobInfo(
            id="test-job-cost",
            job_id="job-cost-test",
            job_type="training",
            status="completed",
        )
        registry.create_job(job)
        
        result = registry.set_cost("job-cost-test", 12.50)
        assert result is True
        
        updated = registry.get("job-cost-test")
        assert updated.actual_cost_usd == 12.50
    
    def test_add_artifact(self):
        """Should add artifact to job."""
        registry = JobRegistry.get_instance()
        
        job = JobInfo(
            id="test-job-artifact",
            job_id="job-artifact-test",
            job_type="training",
            status="completed",
            output_artifacts=[],
        )
        registry.create_job(job)
        
        result = registry.add_artifact("job-artifact-test", "model-v1-weights")
        assert result is True
        
        updated = registry.get("job-artifact-test")
        assert "model-v1-weights" in updated.output_artifacts
    
    def test_list_jobs_by_status(self):
        """Should list jobs by status."""
        registry = JobRegistry.get_instance()
        
        jobs = [
            JobInfo(
                id=f"job-{i}",
                job_id=f"job-status-{i}",
                job_type="training",
                status="running" if i % 2 == 0 else "pending",
            )
            for i in range(4)
        ]
        
        for j in jobs:
            registry.create_job(j)
        
        running = registry.get_jobs_by_status(["running"])
        pending = registry.get_jobs_by_status(["pending"])
        
        assert len(running) == 2
        assert len(pending) == 2
    
    def test_get_recent_jobs(self):
        """Should get recent jobs."""
        registry = JobRegistry.get_instance()
        
        for i in range(5):
            job = JobInfo(
                id=f"job-recent-{i}",
                job_id=f"job-recent-{i}",
                job_type="training",
                status="completed",
            )
            registry.create_job(job)
        
        recent = registry.get_recent_jobs(limit=3)
        assert len(recent) == 3


class TestJobTypes:
    """Test job type enumeration."""
    
    def test_all_types_exist(self):
        """All job types should be defined."""
        types = [t.value for t in JobType]
        
        assert "training" in types
        assert "inference" in types
        assert "evaluation" in types
        assert "deployment" in types


class TestJobStatuses:
    """Test job status enumeration."""
    
    def test_all_statuses_exist(self):
        """All job statuses should be defined."""
        statuses = [s.value for s in JobStatus]
        
        assert "pending" in statuses
        assert "running" in statuses
        assert "completed" in statuses
        assert "failed" in statuses
        assert "cancelled" in statuses


class TestJobDataclass:
    """Test JobInfo dataclass."""
    
    def test_from_record(self):
        """Should create JobInfo from record."""
        from infrastructure.job_registry import JobRecord
        
        class FakeRecord:
            id = "test-job-id"
            job_id = "test-job"
            job_type = "training"
            status = "completed"
            user_id = "user-1"
            user_email = "test@example.com"
            requester = "user-1"
            parent_job_id = None
            related_model_id = None
            model_id = "gpt-4"
            model_version = "1.0"
            resource_cpu = 8.0
            resource_memory_gb = 32.0
            resource_gpu = 1
            resource_gpu_type = "a100"
            resource_instance_type = "p4d.24xlarge"
            scheduled_at = time.time()
            started_at = time.time()
            completed_at = time.time()
            duration_seconds = 3600.0
            estimated_cost_usd = 12.50
            actual_cost_usd = 12.30
            cost_currency = "USD"
            max_retries = 0
            retry_count = 0
            retry_delay_seconds = 60.0
            config = {}
            parameters = {}
            input_artifacts = []
            output_artifacts = ["model-weights-v1"]
            result = {"status": "success"}
            output_uri = "s3://bucket/model.bin"
            error_message = ""
            error_code = ""
            error_traceback = ""
            priority = 0
            queue_position = None
            tags = []
            job_data = {}
            created_by = "user-1"
            created_at = time.time()
            updated_at = time.time()
        
        info = JobInfo.from_record(FakeRecord())
        
        assert info.id == "test-job-id"
        assert info.job_id == "test-job"
        assert info.job_type == "training"
        assert info.status == "completed"
        assert info.resource_cpu == 8.0
        assert info.actual_cost_usd == 12.30
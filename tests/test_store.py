from datetime import datetime, timezone

from ffmpeg_fastapi.jobs.models import Job, JobStatus
from ffmpeg_fastapi.jobs.store import JobStore


def test_marks_interrupted_jobs_as_failed_on_restart(tmp_path):
    db_path = tmp_path / "jobs.db"
    store = JobStore(db_path)
    job = Job(
        id="job0",
        feature_name="sprite",
        status=JobStatus.RUNNING,
        params={},
        created_at=datetime.now(timezone.utc),
    )
    store.create(job)

    # Simulate a restart by re-opening the store against the same db file.
    restarted_store = JobStore(db_path)
    reloaded = restarted_store.get("job0")

    assert reloaded.status == JobStatus.FAILED
    assert "interrupted" in reloaded.error

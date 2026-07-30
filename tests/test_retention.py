from datetime import datetime, timedelta, timezone

from ffmpeg_fastapi.jobs.models import Job, JobStatus
from ffmpeg_fastapi.jobs.retention import enforce_storage_cap
from ffmpeg_fastapi.jobs.store import JobStore


def _make_job(job_id: str, size_bytes: int, completed_at: datetime) -> Job:
    return Job(
        id=job_id,
        feature_name="sprite",
        status=JobStatus.DONE,
        params={},
        output_path=f"/tmp/{job_id}/output.jpg",
        created_at=completed_at,
        completed_at=completed_at,
        size_bytes=size_bytes,
    )


def test_evicts_oldest_jobs_first_when_over_cap(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    uploads_dir = tmp_path / "uploads"
    outputs_dir = tmp_path / "outputs"
    base_time = datetime.now(timezone.utc)

    for i in range(3):
        job = _make_job(f"job{i}", size_bytes=2 * 1024 * 1024, completed_at=base_time + timedelta(minutes=i))
        (outputs_dir / job.id).mkdir(parents=True)
        (uploads_dir / job.id).mkdir(parents=True)
        store.create(job)

    # cap of 3MB with 3 jobs of 2MB each (6MB total) should evict the oldest (job0)
    enforce_storage_cap(store, uploads_dir, outputs_dir, max_storage_mb=3)

    assert store.get("job0") is None
    assert store.get("job1") is not None or store.get("job2") is not None
    assert not (outputs_dir / "job0").exists()


def test_leaves_jobs_alone_when_under_cap(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    uploads_dir = tmp_path / "uploads"
    outputs_dir = tmp_path / "outputs"
    job = _make_job("job0", size_bytes=1024, completed_at=datetime.now(timezone.utc))
    (outputs_dir / job.id).mkdir(parents=True)
    store.create(job)

    enforce_storage_cap(store, uploads_dir, outputs_dir, max_storage_mb=5120)

    assert store.get("job0") is not None

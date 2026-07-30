import shutil
from pathlib import Path

from .store import JobStore


def enforce_storage_cap(store: JobStore, uploads_dir: Path, outputs_dir: Path, max_storage_mb: int) -> None:
    cap_bytes = max_storage_mb * 1024 * 1024
    done_jobs = store.list_done_oldest_first()
    total_bytes = sum(job.size_bytes for job in done_jobs)

    for job in done_jobs:
        if total_bytes <= cap_bytes:
            break
        shutil.rmtree(outputs_dir / job.id, ignore_errors=True)
        shutil.rmtree(uploads_dir / job.id, ignore_errors=True)
        store.delete(job.id)
        total_bytes -= job.size_bytes

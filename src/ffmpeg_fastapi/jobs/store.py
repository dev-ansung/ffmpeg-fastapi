import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Job, JobStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    feature_name TEXT NOT NULL,
    status TEXT NOT NULL,
    params TEXT NOT NULL,
    output_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0
)
"""


class JobStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        self._conn.execute(
            "UPDATE jobs SET status = ?, error = ? WHERE status IN (?, ?)",
            (JobStatus.FAILED, "interrupted by server restart", JobStatus.QUEUED, JobStatus.RUNNING),
        )
        self._conn.commit()

    def create(self, job: Job) -> None:
        self._conn.execute(
            "INSERT INTO jobs (id, feature_name, status, params, output_path, error, created_at, completed_at, size_bytes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job.id,
                job.feature_name,
                job.status,
                json.dumps(job.params),
                job.output_path,
                job.error,
                job.created_at.isoformat(),
                job.completed_at.isoformat() if job.completed_at else None,
                job.size_bytes,
            ),
        )
        self._conn.commit()

    def get(self, job_id: str) -> Job | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        output_path: str | None = None,
        error: str | None = None,
        size_bytes: int | None = None,
    ) -> None:
        completed_at = (
            datetime.now(timezone.utc).isoformat() if status in (JobStatus.DONE, JobStatus.FAILED) else None
        )
        self._conn.execute(
            "UPDATE jobs SET status = ?, output_path = COALESCE(?, output_path),"
            " error = COALESCE(?, error), completed_at = COALESCE(?, completed_at),"
            " size_bytes = COALESCE(?, size_bytes) WHERE id = ?",
            (status, output_path, error, completed_at, size_bytes, job_id),
        )
        self._conn.commit()

    def list_done_oldest_first(self) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status IN (?, ?) ORDER BY completed_at ASC",
            (JobStatus.DONE, JobStatus.FAILED),
        ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def delete(self, job_id: str) -> None:
        self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        self._conn.commit()

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            feature_name=row["feature_name"],
            status=JobStatus(row["status"]),
            params=json.loads(row["params"]),
            output_path=row["output_path"],
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            size_bytes=row["size_bytes"],
        )

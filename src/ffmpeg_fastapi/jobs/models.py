from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(BaseModel):
    id: str
    feature_name: str
    status: JobStatus
    params: dict
    output_path: str | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    size_bytes: int = 0

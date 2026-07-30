import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from ..ffmpeg.registry import get_feature
from ..jobs.models import Job, JobStatus

router = APIRouter(prefix="/api/jobs")


@router.post("/{feature_name}")
async def submit_job(feature_name: str, request: Request):
    feature = get_feature(feature_name)
    if feature is None:
        return JSONResponse({"error": f"unknown feature '{feature_name}'"}, status_code=404)

    form = await request.form()

    try:
        params = feature.parse_params(form)
    except (ValidationError, KeyError, ValueError) as exc:
        return JSONResponse({"error": f"invalid parameters: {exc}"}, status_code=422)

    input_files = feature.input_files(form)
    if not input_files:
        return JSONResponse({"error": "no input file(s) provided"}, status_code=422)

    job_id = uuid.uuid4().hex
    settings = request.app.state.settings
    upload_dir = settings.uploads_dir / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    for index, (filename, content) in enumerate(input_files):
        safe_name = PurePosixPath(filename or "").name or f"input-{index}"
        (upload_dir / f"{index:03d}-{safe_name}").write_bytes(content)

    job = Job(
        id=job_id,
        feature_name=feature_name,
        status=JobStatus.QUEUED,
        params=params.model_dump(),
        created_at=datetime.now(timezone.utc),
    )
    request.app.state.job_store.create(job)
    await request.app.state.job_queue.enqueue(job_id)

    return JSONResponse({"job_id": job_id}, status_code=202)


@router.get("/{job_id}")
async def get_job_status(job_id: str, request: Request):
    job = request.app.state.job_store.get(job_id)
    if job is None:
        return JSONResponse({"error": "job not found"}, status_code=404)
    return {
        "job_id": job.id,
        "feature_name": job.feature_name,
        "status": job.status,
        "error": job.error,
    }


@router.get("/{job_id}/result")
async def get_job_result(job_id: str, request: Request):
    job = request.app.state.job_store.get(job_id)
    if job is None:
        return JSONResponse({"error": "job not found"}, status_code=404)
    if job.status != JobStatus.DONE or not job.output_path:
        return JSONResponse({"error": "job not completed"}, status_code=404)

    filename = f"{job.feature_name}-{job.id}.{job.output_path.rsplit('.', 1)[-1]}"
    return FileResponse(job.output_path, filename=filename)

import asyncio
import shutil
from pathlib import Path

from ..ffmpeg.registry import get_feature
from ..ffmpeg.runner import run_ffmpeg
from .models import JobStatus
from .retention import enforce_storage_cap
from .store import JobStore


class JobQueue:
    def __init__(self, store: JobStore, uploads_dir: Path, outputs_dir: Path, max_storage_mb: int, worker_count: int):
        self._store = store
        self._uploads_dir = uploads_dir
        self._outputs_dir = outputs_dir
        self._max_storage_mb = max_storage_mb
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_count = worker_count
        self._workers: list[asyncio.Task] = []

    def start(self) -> None:
        self._workers = [asyncio.create_task(self._worker_loop()) for _ in range(self._worker_count)]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(job_id)

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._process(job_id)
            finally:
                self._queue.task_done()

    async def _process(self, job_id: str) -> None:
        job = self._store.get(job_id)
        if job is None:
            return

        feature = get_feature(job.feature_name)
        if feature is None:
            self._store.update_status(job_id, JobStatus.FAILED, error=f"unknown feature {job.feature_name}")
            return

        self._store.update_status(job_id, JobStatus.RUNNING)

        upload_dir = self._uploads_dir / job_id
        output_dir = self._outputs_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        inputs = sorted(p for p in upload_dir.iterdir() if p.is_file())
        params_model = feature.params_model.model_validate(job.params)
        output_path = output_dir / f"output.{feature.output_extension(params_model)}"

        try:
            args = await feature.build_command(inputs, params_model, output_path)
            await run_ffmpeg(args)
            size = output_path.stat().st_size
            self._store.update_status(
                job_id, JobStatus.DONE, output_path=str(output_path), size_bytes=size
            )
        except Exception as exc:
            shutil.rmtree(output_dir, ignore_errors=True)
            self._store.update_status(job_id, JobStatus.FAILED, error=str(exc))
        finally:
            shutil.rmtree(upload_dir, ignore_errors=True)
            enforce_storage_cap(self._store, self._uploads_dir, self._outputs_dir, self._max_storage_mb)

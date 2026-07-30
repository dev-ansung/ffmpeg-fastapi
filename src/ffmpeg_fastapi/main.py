from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api.routes_jobs import router as jobs_router
from .config import settings
from .ffmpeg.registry import all_features
from .jobs.queue import JobQueue
from .jobs.store import JobStore

WEB_DIR = Path(__file__).parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    store = JobStore(settings.db_path)
    queue = JobQueue(
        store=store,
        uploads_dir=settings.uploads_dir,
        outputs_dir=settings.outputs_dir,
        max_storage_mb=settings.max_storage_mb,
        worker_count=settings.worker_count,
    )
    queue.start()

    app.state.settings = settings
    app.state.job_store = store
    app.state.job_queue = queue

    yield

    await queue.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="ffmpeg-fastapi", lifespan=lifespan)
    app.include_router(jobs_router)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    @app.get("/")
    async def index(request: Request):
        return templates.TemplateResponse(
            request, "index.html", {"features": all_features()}
        )

    return app


app = create_app()

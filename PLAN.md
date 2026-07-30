# FFmpeg FastAPI - Design Plan

## Context
This is a brand-new project. The goal is a small FastAPI service with a daisyUI web UI for fast ffmpeg-based media transforms that avoid full video decode where possible.

- **Interface**: Web UI (daisyUI v5) + JSON API, both served by FastAPI
- **Jobs**: Async job queue, lightweight/single-process (no Redis/Celery) - in-process asyncio worker pool with a SQLite-backed job table
- **Progress**: Polling (`GET /api/jobs/{id}`), not WebSocket/SSE
- **Storage**: Local filesystem
- **Auth**: None for now
- **Critical constraint: zero-install execution.** Must run as `uvx --from <repo> ffmpeg-fastapi` with no manual setup by the user - just system `ffmpeg`/`ffprobe` as an external dependency. This means: proper installable package (`pyproject.toml` with an entry point), no assumption of a persistent writable project directory, and runtime state defaulting to a temp directory (overridable via env var) since a `uvx`-launched tool has no fixed "install location."
- **Entry point**: bare uvicorn launch (`ffmpeg-fastapi` command starts uvicorn directly), not a custom Typer/argparse CLI layer.
- **Retention**: storage-threshold-based eviction (delete oldest completed jobs' files when total storage exceeds a cap), not time-based.

Environment: ffmpeg 8.1.2 installed locally with videotoolbox (macOS hardware accel), libx264/libx265, libwebp, etc.

Two initial features, designed to avoid full video decode where possible:
1. **Video sprite sheet generation** - input video, rows, cols, output image width -> static image output (jpg)
2. **Images to video conversion** - input images, mirror blur toggle, transition toggle, output width, aspect ratio -> mp4

## Resolved Decisions
1. **Upload size**: no limit for now; disk usage is bounded only by the storage-threshold eviction sweep.
2. **Storage cap**: 5 GB default, configurable via `FFMPEG_FASTAPI_MAX_STORAGE_MB` env var.
3. **Port binding**: auto-pick a free port at startup (no fixed default); the chosen `http://127.0.0.1:<port>` URL is printed to stdout when the server starts, matching the zero-config `uvx` experience.

## Architecture

### Project layout
```
ffmpeg-fastapi/
  pyproject.toml               # uv-managed, defines [project.scripts] entry point
  README.md
  PLAN.md
  src/
    ffmpeg_fastapi/
      __init__.py
      __main__.py               # entry point: launches uvicorn directly (bare, no CLI layer)
      main.py                   # FastAPI app, mounts routers + static UI
      config.py                 # Settings; state dir defaults to
                                 #   tempfile.gettempdir()/ffmpeg-fastapi, overridable via
                                 #   FFMPEG_FASTAPI_STATE_DIR env var
      jobs/
        models.py                # Job, JobStatus (pydantic + SQLite row mapping)
        store.py                 # SQLite-backed job table (create/update/get/list)
        queue.py                 # in-process async worker pool (asyncio.Queue + N workers)
        retention.py             # storage-threshold eviction sweep
      ffmpeg/
        probe.py                 # ffprobe wrapper (duration, dimensions, frame count)
        base.py                   # Feature protocol (parse_params, build_command, output_extension)
        registry.py                # feature_name -> Feature impl lookup
        sprite.py                 # Feature impl: sprite sheet generation
        images_to_video.py        # Feature impl: images -> video
        runner.py                 # shared subprocess execution, error capture
      api/
        routes_jobs.py            # POST /api/jobs/{feature_name}, GET /api/jobs/{id}, GET /api/jobs/{id}/result
      web/
        templates/                 # Jinja2 templates using daisyUI
        static/                     # daisyUI css, minimal JS for polling
```

At runtime (lives under the state dir, no repo checkout needed):
```
$FFMPEG_FASTAPI_STATE_DIR/            # default: <tempdir>/ffmpeg-fastapi
  jobs.db                              # SQLite
  uploads/<job_id>/...
  outputs/<job_id>/...
```

Packaging: `src/` layout, `[project.scripts] ffmpeg-fastapi = "ffmpeg_fastapi.__main__:main"` so `uvx --from <repo-url-or-path> ffmpeg-fastapi` resolves cleanly.

### Extensibility model
The queue/job-store/UI stay feature-agnostic so a third feature is a pure addition.

- **Feature interface**:
  ```python
  class Feature(Protocol):
      name: str
      def parse_params(form: FormData) -> BaseModel
      def build_command(inputs: list[Path], params: BaseModel, output_path: Path) -> list[str]
      def output_extension(params: BaseModel) -> str
  ```
- **Generic job model**: `jobs` table stores `feature_name` + a JSON `params` blob, not feature-specific columns.
- **Generic route**: single `POST /api/jobs/{feature_name}` delegates to the registered feature's `parse_params`/`build_command`.
- **UI**: template block per feature for v1; backend stays generic regardless.

### Job lifecycle
1. Client uploads input file(s) via `multipart/form-data` to `POST /api/jobs/{feature_name}` with feature-specific form params.
2. Endpoint validates inputs, saves uploads to `uploads/<job_id>/`, inserts a `Job` row (`queued`), enqueues it. Returns `{job_id}` (202).
3. An asyncio worker pool pulls jobs off a queue, runs the ffmpeg command via `asyncio.create_subprocess_exec` (never shell=True), updates status `running` -> `done`/`failed`.
4. Client polls `GET /api/jobs/{job_id}`; on `done`, `GET /api/jobs/{job_id}/result` streams the output file with `Content-Disposition: attachment`.
5. UI polls every ~1-2s, shows a daisyUI progress indicator, then a result card with preview + download link.

### Why SQLite instead of pure in-memory
Survives app restarts (a job stuck in `running` is marked `failed: interrupted` on startup) and gives a lightweight audit trail, at zero extra infra cost.

### FFmpeg command design (fast-path, avoid full decode)

**Sprite sheet** (input video, rows, cols, output width):
- `ffprobe` first for duration/dimensions.
- Single-pass: `ffmpeg -i input -vf "select='not(mod(n,FRAME_INTERVAL))',scale=TILE_W:-1,tile=COLSxROWS" -frames:v 1 -vsync vfr out.jpg`, with `FRAME_INTERVAL` computed from total frame count / (rows*cols) so only sampled frames get scaled/tiled.
- Output: static jpg.

**Images to video** (input images, mirror blur toggle, transition toggle, output width, aspect ratio):
- `-f concat` demuxer with a generated list file (handles arbitrary uploaded filenames/order) with per-image `duration` lines.
- **Mirror blur** background: `split` into two branches - one `scale=W:H:force_original_aspect_ratio=increase,crop=W:H,gblur=sigma=20` (blurred fill), one `scale=W:H:force_original_aspect_ratio=decrease` (sharp foreground) - composited via `overlay=(W-w)/2:(H-h)/2`.
- **Transitions**: `xfade` filter chained between consecutive image clips (each turned into a clip via `loop`/`tpad`), fixed default crossfade duration.
- Output width + aspect ratio determine W/H fed into the above filters.
- Encode: `-c:v libx264 -pix_fmt yuv420p -movflags +faststart`.

### API surface
- `POST /api/jobs/{feature_name}` - multipart body is feature-specific:
  - `feature_name=sprite`: `video` file, `rows`, `cols`, `width`
  - `feature_name=images_to_video`: `images[]`, `mirror_blur: bool`, `transition: bool`, `width`, `aspect_ratio` (e.g. "16:9")
  - returns `{job_id}` (202)
- `GET /api/jobs/{job_id}` -> `{status, feature_name, progress?, error?}`
- `GET /api/jobs/{job_id}/result` -> file stream (404 until done)
- `GET /` - daisyUI page with upload forms + job status polling panel

### Web UI flow
Each form submits via `fetch()`, receives `{job_id}`, polls status every ~1-2s. While `queued`/`running`: progress/spinner. On `done`: preview (`<img>` or `<video>`) + a Download link/button pointing at the result endpoint with `download` attribute (server sets `Content-Disposition: attachment`). On `failed`: show the error message.

### Cleanup / limits
- No upload size limit.
- **Retention: storage-threshold-based eviction.** After each job completes, sum `uploads/` + `outputs/` size; if it exceeds `FFMPEG_FASTAPI_MAX_STORAGE_MB` (default 5120), delete oldest-completed jobs' files first (by `completed_at` ascending) until back under the cap. Jobs still `queued`/`running` are never evicted.

## Verification
- `uv run pytest` for unit tests on `Feature` implementations (command construction, given known inputs, without actually invoking ffmpeg) and the retention eviction logic.
- End-to-end smoke test: start the server, POST a small sample video to `/api/jobs/sprite` and a couple sample images to `/api/jobs/images_to_video`, poll to `done`, fetch the result, and assert output file properties via `ffprobe` (dimensions, format).
- Manual browser check of the UI upload/poll/download flow, done once at the end per user's stated preference (build straight through, test only at the end).

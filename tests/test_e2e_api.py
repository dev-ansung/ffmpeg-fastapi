import asyncio

import httpx
import pytest
from asgi_lifespan import LifespanManager

from ffmpeg_fastapi import config
from ffmpeg_fastapi.main import create_app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "state_dir", tmp_path / "state")
    app = create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def _wait_for_done(client: httpx.AsyncClient, job_id: str, timeout: float = 30.0):
    async def poll():
        while True:
            res = await client.get(f"/api/jobs/{job_id}")
            data = res.json()
            if data["status"] in ("done", "failed"):
                return data
            await asyncio.sleep(0.2)

    return await asyncio.wait_for(poll(), timeout=timeout)


async def test_sprite_job_end_to_end(client, sample_video):
    with open(sample_video, "rb") as f:
        res = await client.post(
            "/api/jobs/sprite",
            data={"rows": "2", "cols": "2", "width": "640"},
            files={"video": ("sample.mp4", f, "video/mp4")},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    status = await _wait_for_done(client, job_id)
    assert status["status"] == "done", status

    result = await client.get(f"/api/jobs/{job_id}/result")
    assert result.status_code == 200
    assert result.headers["content-type"] == "image/jpeg"
    assert len(result.content) > 0


async def test_images_to_video_job_end_to_end(client, sample_images):
    files = [("images", (img.name, open(img, "rb"), "image/jpeg")) for img in sample_images]
    try:
        res = await client.post(
            "/api/jobs/images_to_video",
            data={"width": "320", "aspect_ratio": "4:3", "mirror_blur": "true", "transition": "false"},
            files=files,
        )
    finally:
        for _, (_, fh, _) in files:
            fh.close()

    assert res.status_code == 202
    job_id = res.json()["job_id"]

    status = await _wait_for_done(client, job_id)
    assert status["status"] == "done", status

    result = await client.get(f"/api/jobs/{job_id}/result")
    assert result.status_code == 200
    assert result.headers["content-type"] == "video/mp4"


async def test_unknown_feature_returns_404(client):
    res = await client.post("/api/jobs/nonexistent", data={})
    assert res.status_code == 404


async def test_missing_result_returns_404(client):
    res = await client.get("/api/jobs/does-not-exist/result")
    assert res.status_code == 404


async def test_upload_filename_path_traversal_is_contained(client):
    res = await client.post(
        "/api/jobs/sprite",
        data={"rows": "1", "cols": "1", "width": "64"},
        files={"video": ("../../../../etc/passwd", b"not a real video", "video/mp4")},
    )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    upload_dir = config.settings.uploads_dir / job_id
    saved_files = list(upload_dir.iterdir())
    assert len(saved_files) == 1
    assert saved_files[0].parent == upload_dir
    assert saved_files[0].name.endswith("passwd")
    assert ".." not in saved_files[0].name


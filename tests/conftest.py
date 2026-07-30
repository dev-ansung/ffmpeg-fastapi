import asyncio
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("fixtures") / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


@pytest.fixture(scope="session")
def sample_images(tmp_path_factory) -> list[Path]:
    directory = tmp_path_factory.mktemp("images")
    paths = []
    for i, color in enumerate(["red", "green", "blue"]):
        path = directory / f"img{i}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={color}:size=320x240",
                "-frames:v", "1",
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        paths.append(path)
    return paths

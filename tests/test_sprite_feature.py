import subprocess

import pytest

from ffmpeg_fastapi.ffmpeg.runner import run_ffmpeg
from ffmpeg_fastapi.ffmpeg.sprite import SpriteFeature, SpriteParams


def test_params_validation_rejects_out_of_range_rows():
    with pytest.raises(Exception):
        SpriteParams(rows=0, cols=4, width=1280)


async def test_build_command_produces_correct_tile_dimensions(sample_video, tmp_path):
    feature = SpriteFeature()
    params = SpriteParams(rows=2, cols=2, width=800)
    output_path = tmp_path / "sprite.jpg"

    args = await feature.build_command([sample_video], params, output_path)
    await run_ffmpeg(args)

    assert output_path.exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(output_path)],
        check=True, capture_output=True, text=True,
    )
    width, height = (int(v) for v in probe.stdout.strip().split(","))
    assert width == 800
    assert height > 0


def test_output_extension_is_jpg():
    feature = SpriteFeature()
    assert feature.output_extension(SpriteParams(rows=2, cols=2, width=800)) == "jpg"

import subprocess

from ffmpeg_fastapi.ffmpeg.images_to_video import IMAGE_DURATION, ImagesToVideoFeature, ImagesToVideoParams
from ffmpeg_fastapi.ffmpeg.runner import run_ffmpeg


def test_height_derived_from_aspect_ratio():
    params = ImagesToVideoParams(width=1280, aspect_ratio="16:9")
    assert params.height == 720


def test_height_is_always_even():
    params = ImagesToVideoParams(width=1281, aspect_ratio="1:1")
    assert params.height % 2 == 0


async def test_build_command_produces_mp4(sample_images, tmp_path):
    feature = ImagesToVideoFeature()
    params = ImagesToVideoParams(width=320, aspect_ratio="4:3", mirror_blur=False, transition=False)

    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    inputs = []
    for image in sample_images:
        dest = input_dir / image.name
        dest.write_bytes(image.read_bytes())
        inputs.append(dest)

    output_path = tmp_path / "output.mp4"
    args = await feature.build_command(inputs, params, output_path)
    await run_ffmpeg(args)

    assert output_path.exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(output_path)],
        check=True, capture_output=True, text=True,
    )
    width, height = (int(v) for v in probe.stdout.strip().split(","))
    assert width == 320
    assert height == params.height

    duration_probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(output_path)],
        check=True, capture_output=True, text=True,
    )
    duration = float(duration_probe.stdout.strip())
    expected_duration = IMAGE_DURATION * len(sample_images)
    assert abs(duration - expected_duration) < 0.5


async def test_build_command_with_mirror_blur_and_transition(sample_images, tmp_path):
    feature = ImagesToVideoFeature()
    params = ImagesToVideoParams(width=320, aspect_ratio="1:1", mirror_blur=True, transition=True)

    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    inputs = []
    for image in sample_images:
        dest = input_dir / image.name
        dest.write_bytes(image.read_bytes())
        inputs.append(dest)

    output_path = tmp_path / "output.mp4"
    args = await feature.build_command(inputs, params, output_path)
    await run_ffmpeg(args)

    assert output_path.exists()
    assert output_path.stat().st_size > 0

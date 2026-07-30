import subprocess

import pytest

from ffmpeg_fastapi.ffmpeg.images_to_video import (
    IMAGE_DURATION,
    TRANSITION_DURATION,
    ImagesToVideoFeature,
    ImagesToVideoParams,
    TransitionType,
)
from ffmpeg_fastapi.ffmpeg.runner import run_ffmpeg


def _average_brightness_at(video_path, timestamp: float) -> float:
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(timestamp), "-i", str(video_path),
            "-frames:v", "1", "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
            "-f", "null", "-",
        ],
        check=True, capture_output=True, text=True,
    )
    for line in result.stderr.splitlines():
        if "lavfi.signalstats.YAVG" in line:
            return float(line.rsplit("=", 1)[-1])
    raise AssertionError(f"could not read brightness at t={timestamp} from {video_path}")


def _copy_inputs(sample_images, tmp_path):
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    inputs = []
    for image in sample_images:
        dest = input_dir / image.name
        dest.write_bytes(image.read_bytes())
        inputs.append(dest)
    return inputs


def test_height_derived_from_aspect_ratio():
    params = ImagesToVideoParams(width=1280, aspect_ratio="16:9")
    assert params.height == 720


def test_height_is_always_even():
    params = ImagesToVideoParams(width=1281, aspect_ratio="1:1")
    assert params.height % 2 == 0


async def test_build_command_produces_mp4(sample_images, tmp_path):
    feature = ImagesToVideoFeature()
    params = ImagesToVideoParams(width=320, aspect_ratio="4:3", mirror_blur=False, transition=TransitionType.NONE)
    inputs = _copy_inputs(sample_images, tmp_path)

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


@pytest.mark.parametrize("transition", [TransitionType.FADE, TransitionType.DIFFUSE])
async def test_build_command_with_mirror_blur_and_transition(sample_images, tmp_path, transition):
    feature = ImagesToVideoFeature()
    params = ImagesToVideoParams(width=320, aspect_ratio="1:1", mirror_blur=True, transition=transition)
    inputs = _copy_inputs(sample_images, tmp_path)

    output_path = tmp_path / "output.mp4"
    args = await feature.build_command(inputs, params, output_path)
    await run_ffmpeg(args)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


@pytest.mark.parametrize("transition", [TransitionType.FADE, TransitionType.DIFFUSE])
async def test_transition_does_not_darken_later_segments(sample_images, tmp_path, transition):
    # Regression test: an earlier implementation faded each concatenated segment via
    # a single global `fade` filter after the concat demuxer, whose `st=` timestamp
    # only ever landed within the first segment - every later image inherited the
    # fade's terminal (black) value. xfade-based transitions must not reproduce this.
    feature = ImagesToVideoFeature()
    params = ImagesToVideoParams(width=320, aspect_ratio="4:3", mirror_blur=False, transition=transition)
    inputs = _copy_inputs(sample_images, tmp_path)

    output_path = tmp_path / "output.mp4"
    args = await feature.build_command(inputs, params, output_path)
    await run_ffmpeg(args)

    baseline_params = ImagesToVideoParams(width=320, aspect_ratio="4:3", mirror_blur=False, transition=TransitionType.NONE)
    baseline_path = tmp_path / "baseline.mp4"
    baseline_args = await feature.build_command(inputs, baseline_params, baseline_path)
    await run_ffmpeg(baseline_args)

    # Each xfade overlaps TRANSITION_DURATION seconds with the next segment, so the
    # cumulative offset to segment i's own (non-overlapped) midpoint shrinks by one
    # overlap per prior transition.
    step = IMAGE_DURATION - TRANSITION_DURATION
    for segment_index in (1, 2):
        midpoint = segment_index * step + IMAGE_DURATION / 2
        brightness = _average_brightness_at(output_path, midpoint)
        baseline_brightness = _average_brightness_at(baseline_path, IMAGE_DURATION * segment_index + IMAGE_DURATION / 2)
        assert brightness > baseline_brightness * 0.5, (
            f"segment {segment_index} unexpectedly dark at t={midpoint}: "
            f"YAVG={brightness} vs baseline {baseline_brightness}"
        )

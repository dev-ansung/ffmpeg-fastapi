import asyncio
import json
from pathlib import Path


class ProbeError(RuntimeError):
    pass


async def probe_video(path: Path) -> dict:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,nb_frames,r_frame_rate",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise ProbeError(stderr.decode(errors="replace"))

    data = json.loads(stdout)
    stream = data.get("streams", [{}])[0]
    fmt = data.get("format", {})

    duration = float(fmt.get("duration", 0.0) or 0.0)
    width = int(stream.get("width", 0) or 0)
    height = int(stream.get("height", 0) or 0)

    nb_frames_raw = stream.get("nb_frames")
    frame_rate_raw = stream.get("r_frame_rate", "0/1")
    num, _, den = frame_rate_raw.partition("/")
    fps = float(num) / float(den) if den and float(den) != 0 else 0.0

    nb_frames = int(nb_frames_raw) if nb_frames_raw and nb_frames_raw.isdigit() else int(duration * fps)

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "nb_frames": max(nb_frames, 1),
    }

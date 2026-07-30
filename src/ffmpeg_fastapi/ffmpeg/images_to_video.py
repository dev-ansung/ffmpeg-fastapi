from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field
from starlette.datastructures import FormData

IMAGE_DURATION = 2.0
TRANSITION_DURATION = 0.5


class TransitionType(StrEnum):
    NONE = "none"
    FADE = "fade"
    DIFFUSE = "diffuse"


_XFADE_TRANSITION_NAMES = {
    TransitionType.FADE: "fade",
    TransitionType.DIFFUSE: "dissolve",
}


class ImagesToVideoParams(BaseModel):
    mirror_blur: bool = False
    transition: TransitionType = TransitionType.NONE
    width: int = Field(gt=0, le=8192)
    aspect_ratio: str = "16:9"

    @property
    def height(self) -> int:
        num_str, _, den_str = self.aspect_ratio.partition(":")
        num, den = int(num_str), int(den_str)
        height = round(self.width * den / num)
        return height + (height % 2)


class ImagesToVideoFeature:
    name = "images_to_video"
    params_model = ImagesToVideoParams

    def parse_params(self, form: FormData) -> ImagesToVideoParams:
        return ImagesToVideoParams(
            mirror_blur=form.get("mirror_blur") == "true",
            transition=TransitionType(form.get("transition", TransitionType.NONE)),
            width=int(form["width"]),
            aspect_ratio=str(form.get("aspect_ratio", "16:9")),
        )

    def input_files(self, form: FormData) -> list[tuple[str, bytes]]:
        images = form.getlist("images")
        return [(image.filename, image.file.read()) for image in images]

    async def build_command(
        self, inputs: list[Path], params: ImagesToVideoParams, output_path: Path
    ) -> list[str]:
        width, height = params.width, params.height

        if params.mirror_blur:
            frame_filter = (
                f"split=2[bg][fg];"
                f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},gblur=sigma=20[bg2];"
                f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fg2];"
                f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1"
            )
        else:
            frame_filter = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
            )

        input_args = []
        for image in inputs:
            input_args += ["-loop", "1", "-t", str(IMAGE_DURATION), "-i", str(image)]

        filter_parts = []
        for i in range(len(inputs)):
            filter_parts.append(f"[{i}:v]{frame_filter},fps=25[v{i}]")

        use_xfade = params.transition != TransitionType.NONE and len(inputs) > 1
        if use_xfade:
            xfade_name = _XFADE_TRANSITION_NAMES[params.transition]
            current_label = "v0"
            elapsed = IMAGE_DURATION
            last_index = len(inputs) - 1
            for i in range(1, len(inputs)):
                out_label = "outv" if i == last_index else f"x{i}"
                offset = elapsed - TRANSITION_DURATION
                filter_parts.append(
                    f"[{current_label}][v{i}]xfade=transition={xfade_name}:"
                    f"duration={TRANSITION_DURATION}:offset={offset}[{out_label}]"
                )
                current_label = out_label
                elapsed += IMAGE_DURATION - TRANSITION_DURATION
        else:
            labels = "".join(f"[v{i}]" for i in range(len(inputs)))
            filter_parts.append(f"{labels}concat=n={len(inputs)}:v=1:a=0[outv]")

        filter_complex = ";".join(filter_parts)

        return [
            *input_args,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]

    def output_extension(self, params: ImagesToVideoParams) -> str:
        return "mp4"

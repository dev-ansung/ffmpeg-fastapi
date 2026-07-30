from pathlib import Path

from pydantic import BaseModel, Field
from starlette.datastructures import FormData

IMAGE_DURATION = 2.0
TRANSITION_DURATION = 0.5


class ImagesToVideoParams(BaseModel):
    mirror_blur: bool = False
    transition: bool = False
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
            transition=form.get("transition") == "true",
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
        list_path = inputs[0].parent / "concat_list.txt"
        lines = []
        for image in inputs:
            lines.append(f"file '{image.name}'")
            lines.append(f"duration {IMAGE_DURATION}")
        list_path.write_text("\n".join(lines))

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

        vf = f"{frame_filter},fps=25"
        if params.transition and len(inputs) > 1:
            # Simple fade-in/fade-out per image approximates a crossfade without
            # requiring a per-pair xfade filtergraph across an arbitrary N images.
            vf += (
                f",fade=t=in:st=0:d={TRANSITION_DURATION},"
                f"fade=t=out:st={IMAGE_DURATION - TRANSITION_DURATION}:d={TRANSITION_DURATION}"
            )

        return [
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_path),
            "-vf", vf,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]

    def output_extension(self, params: ImagesToVideoParams) -> str:
        return "mp4"

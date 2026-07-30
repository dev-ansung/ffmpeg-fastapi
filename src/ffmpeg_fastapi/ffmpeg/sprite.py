from pathlib import Path

from pydantic import BaseModel, Field
from starlette.datastructures import FormData

from .probe import probe_video


class SpriteParams(BaseModel):
    rows: int = Field(gt=0, le=32)
    cols: int = Field(gt=0, le=32)
    width: int = Field(gt=0, le=8192)


class SpriteFeature:
    name = "sprite"
    params_model = SpriteParams

    def parse_params(self, form: FormData) -> SpriteParams:
        return SpriteParams(
            rows=int(form["rows"]),
            cols=int(form["cols"]),
            width=int(form["width"]),
        )

    def input_files(self, form: FormData) -> list[tuple[str, bytes]]:
        video = form["video"]
        return [(video.filename, video.file.read())]

    async def build_command(self, inputs: list[Path], params: SpriteParams, output_path: Path) -> list[str]:
        info = await probe_video(inputs[0])
        tile_count = params.rows * params.cols
        interval = max(info["nb_frames"] // tile_count, 1)
        tile_width = params.width // params.cols

        vf = (
            f"select='not(mod(n\\,{interval}))',"
            f"scale={tile_width}:-1,"
            f"tile={params.cols}x{params.rows}"
        )
        return [
            "-i", str(inputs[0]),
            "-vf", vf,
            "-frames:v", "1",
            "-vsync", "vfr",
            str(output_path),
        ]

    def output_extension(self, params: SpriteParams) -> str:
        return "jpg"

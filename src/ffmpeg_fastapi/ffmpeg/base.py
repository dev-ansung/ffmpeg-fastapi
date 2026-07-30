from pathlib import Path
from typing import Protocol

from pydantic import BaseModel
from starlette.datastructures import FormData


class Feature(Protocol):
    name: str
    params_model: type[BaseModel]

    def parse_params(self, form: FormData) -> BaseModel:
        """Validate and extract typed parameters from an uploaded form."""

    def input_files(self, form: FormData) -> list[tuple[str, bytes]]:
        """Return (filename, content) pairs for the uploaded input file(s)."""

    async def build_command(self, inputs: list[Path], params: BaseModel, output_path: Path) -> list[str]:
        """Build the ffmpeg argv (no shell) that produces output_path from inputs."""

    def output_extension(self, params: BaseModel) -> str:
        """File extension (without dot) for the produced output."""

import tempfile
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FFMPEG_FASTAPI_")

    state_dir: Path = Path(tempfile.gettempdir()) / "ffmpeg-fastapi"
    max_storage_mb: int = 5120
    worker_count: int = 2
    host: str = "127.0.0.1"
    port: int = 0

    @property
    def db_path(self) -> Path:
        return self.state_dir / "jobs.db"

    @property
    def uploads_dir(self) -> Path:
        return self.state_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.state_dir / "outputs"

    def ensure_dirs(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()

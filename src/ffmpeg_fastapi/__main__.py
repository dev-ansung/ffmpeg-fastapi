import socket

import uvicorn

from .config import settings


def _pick_port(host: str) -> int:
    if settings.port:
        return settings.port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def main() -> None:
    port = _pick_port(settings.host)
    print(f"Serving at http://{settings.host}:{port}", flush=True)
    uvicorn.run("ffmpeg_fastapi.main:app", host=settings.host, port=port, log_level="info")


if __name__ == "__main__":
    main()

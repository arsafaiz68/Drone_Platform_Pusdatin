"""Konfigurasi modul Drone Video Downloader, dibaca dari environment / file backend/.env.

Data (riwayat batch & log) disimpan di ``data/downloader`` pada folder platform,
bersebelahan dengan data Drone Video Trimmer.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv bersifat opsional saat pengujian
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent
# Ikut ADT_DATA_DIR (folder data platform) bila diset, mis. saat pengujian.
DEFAULT_DATA_DIR = (Path(os.environ["ADT_DATA_DIR"]) if os.environ.get("ADT_DATA_DIR")
                    else ROOT_DIR / "data") / "downloader"
_DEFAULT_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:8000", "http://127.0.0.1:8000",
]

if load_dotenv is not None:
    load_dotenv(BACKEND_DIR / ".env")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "ya", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def _list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [v.strip() for v in value.split(",") if v.strip()]


def _path(value: str | None, default: Path) -> Path:
    p = Path(value) if value else default
    if not p.is_absolute():
        p = ROOT_DIR / p
    return p


@dataclass
class Settings:
    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_origins: list[str] = field(default_factory=lambda: list(_DEFAULT_ORIGINS))
    allowed_hosts: list[str] = field(default_factory=lambda: ["127.0.0.1", "localhost"])

    # --- Penyimpanan lokal ---
    data_dir: Path = DEFAULT_DATA_DIR
    log_dir: Path = DEFAULT_DATA_DIR / "logs"
    history_dir: Path = DEFAULT_DATA_DIR / "history"
    default_output_dir: Path = Path.home() / "Videos" / "Batch YouTube Downloader"

    # --- Download ---
    default_quality: int = 1080
    default_parallel: int = 3
    max_parallel: int = 3
    download_retries: int = 3
    ffmpeg_location: str | None = None

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.log_dir, self.history_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    env = os.environ
    data_dir = _path(env.get("DOWNLOADER_DATA_DIR"), DEFAULT_DATA_DIR)
    default_out = env.get("DEFAULT_OUTPUT_DIR")
    max_parallel = max(1, min(_int(env.get("MAX_PARALLEL_DOWNLOADS"), 3), 3))
    return Settings(
        host=env.get("HOST", "127.0.0.1"),
        port=_int(env.get("PORT"), 8000),
        allowed_origins=_list(env.get("ALLOWED_ORIGINS"), list(_DEFAULT_ORIGINS)),
        allowed_hosts=_list(env.get("ALLOWED_HOSTS"), ["127.0.0.1", "localhost"]),
        data_dir=data_dir,
        log_dir=_path(env.get("LOG_DIR"), data_dir / "logs"),
        history_dir=_path(env.get("HISTORY_DIR"), data_dir / "history"),
        default_output_dir=(Path(os.path.expandvars(os.path.expanduser(default_out))) if default_out
                            else Path.home() / "Videos" / "Batch YouTube Downloader"),
        default_quality=_int(env.get("DEFAULT_QUALITY"), 1080),
        default_parallel=max(1, min(_int(env.get("DEFAULT_PARALLEL"), 3), max_parallel)),
        max_parallel=max_parallel,
        download_retries=max(0, _int(env.get("DOWNLOAD_RETRIES"), 3)),
        ffmpeg_location=env.get("FFMPEG_LOCATION") or None,
    )


settings = load_settings()

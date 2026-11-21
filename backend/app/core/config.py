"""Konfigurasi terpusat Drone Video Platform (modul Drone Video Trimmer).

Semua path bersifat lokal. Direktori data dapat dipindahkan melalui variabel
lingkungan ``ADT_DATA_DIR`` (dipakai juga oleh pengujian otomatis).
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Drone Video Platform"
APP_VERSION = "2.0.0"

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


def _data_dir() -> Path:
    env = os.environ.get("ADT_DATA_DIR")
    return Path(env).resolve() if env else (ROOT_DIR / "data")


class Paths:
    """Lokasi direktori data. Dievaluasi ulang lewat ``refresh()`` (untuk tes)."""

    def __init__(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.data = _data_dir()
        self.projects = self.data / "projects"
        self.uploads = self.data / "uploads"
        self.temporary = self.data / "temporary"
        self.exports = self.data / "exports"
        self.models = self.data / "models"
        self.dataset = self.models / "dataset"
        self.database_dir = self.data / "database"
        self.database = self.database_dir / "ai_drone_trimmer.db"
        self.logs = self.data / "logs"

    def ensure(self) -> None:
        for p in (self.projects, self.uploads, self.temporary, self.exports,
                  self.models, self.dataset, self.database_dir, self.logs):
            p.mkdir(parents=True, exist_ok=True)


paths = Paths()

# ----------------------------------------------------------------- batasan
# Maksimal 24 video sumber per batch. Setiap video sumber menghasilkan SATU video
# hasil sendiri (24 video masuk -> 24 video keluar) dengan durasi target di bawah ini.
MAX_BATCH_VIDEOS = 24
DURATION_MIN, DURATION_MAX, DURATION_STEP = 10, 60, 5
FINAL_DURATIONS = tuple(range(DURATION_MIN, DURATION_MAX + 1, DURATION_STEP))  # 10, 15, ..., 60
CONCURRENCY_OPTIONS = (1, 2, 4)
DEFAULT_CONCURRENCY = 2
TRIP_MODES = ("outbound", "round_trip")  # pergi saja / pergi dan kembali
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mts", ".ts", ".lrf"}

TRAFFIC_CONDITIONS = [
    "Lancar",
    "Ramai Lancar",
    "Ramai",
    "Padat",
    "Padat Merayap",
    "Macet",
    "Tidak Teridentifikasi",
]
DEFAULT_TRAFFIC = "Tidak Teridentifikasi"

# Status antrean (kode internal -> label Indonesia)
ITEM_STATUS_LABELS = {
    "waiting": "Menunggu",
    "analyzing": "Sedang dianalisis",
    "analyzed": "Analisis selesai",
    "processing": "Sedang diproses",
    "review": "Menunggu review",
    "done": "Selesai direview",
    "failed": "Gagal",
    "cancelled": "Dibatalkan",
}
BATCH_STATUS_LABELS = {
    "draft": "Draf",
    "queued": "Dalam antrean",
    "running": "Berjalan",
    "paused": "Dijeda",
    "review": "Menunggu review",
    "completed": "Selesai",
    "cancelled": "Dibatalkan",
    "failed": "Gagal",
}

# Pengaturan default (dapat diubah dari halaman Pengaturan, disimpan di SQLite)
DEFAULT_SETTINGS = {
    "default_concurrency": DEFAULT_CONCURRENCY,
    "default_final_duration": 30,
    "default_trip_mode": "round_trip",
    "analysis_sample_fps": 2.0,         # frame per detik yang dianalisis
    "analysis_width": 320,              # lebar frame analisis (px)
    "detector_sample_fps": 1.0,         # frame per detik untuk deteksi objek
    "generate_preview_proxy": True,     # buat proxy H.264 480p untuk preview browser
    "proxy_height": 480,
    "export_mode": "auto",              # auto | reencode | copy
    "export_max_height": 0,             # 0 = pertahankan resolusi asli sumber
    "export_fps": 30,                   # hanya dipakai bila frame rate sumber berbeda-beda
    "export_crf": 16,                   # H.264 CRF 14–18 = kualitas sangat tinggi
    "export_preset": "slow",            # slow / veryslow untuk efisiensi kompresi terbaik
    "export_codec": "h264",             # h264 | hevc
    "export_audio_bitrate": 320,        # kbps AAC
    "use_gpu_encoder": False,           # NVENC lebih cepat tetapi kualitas per bit di bawah x264 slow
    "quality_profile_version": 2,
    "min_segment_seconds": 3.0,
    "max_segment_seconds": 20.0,
    "support_share": 0.2,               # porsi "momen pendukung" dari durasi final
    "metadata_time_is_utc": True,       # creation_time video dianggap UTC
    "local_utc_offset_hours": 7,        # WIB
    "include_home_point": False,        # sertakan footage Home Point di video final
    "output_dir": "",                   # kosong = data/exports
}

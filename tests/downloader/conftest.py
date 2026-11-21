"""Fixture & mock untuk pengujian tanpa internet."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.downloader.ytdlp import (  # noqa: E402
    DownloadCancelledError,
    DownloadFailedError,
    DownloadResult,
    ProgressInfo,
)

BLOCK_TEMPLATE = """*{loc}*
*{day} Apr 2026, {hh}:{mm} {tz}*
Cuaca : Cerah, Tinggi Gelombang : 0.2 - 0.5 m (Selatan)
Lalin : {lalin}
Rekayasa Lalin : -
{url}
"""

SAMPLE_REPORT = """Hari/Tanggal : *Rabu, 1 April 2026*
Jam Laporan : *12:00* - *22:59*

*Pel. Ketapang*
*1 Apr 2026, 14:10 WIB*
Cuaca : Cerah, Tinggi Gelombang : 0.2 - 0.5 m (Selatan)
Lalin : Padat
Rekayasa Lalin : -
https://www.youtube.com/live/tqvej7BovSQ?si=QzF8UrG-LvXbNFCL

*Pel. Gilimanuk*
*1 Apr 2026, 15:20 WITA*
Cuaca : Cerah, Tinggi Gelombang : 0.1 - 0.8 m (Selatan)
Lalin : Ramai Lancar
Rekayasa Lalin : -
https://youtube.com/live/MwXlB-RPNXY?feature=share

*Pel. Merak*
*1 Apr 2026, 16:00 WIB*
Cuaca : Berawan, Tinggi Gelombang : 0.5 - 1.25 m (Barat)
Lalin : Ramai
Rekayasa Lalin : Delaying system
https://www.youtube.com/watch?v=dQw4w9WgXcQ&pp=abc

*Pel. Bakauheni*
*1 Apr 2026, 16:30 WIB*
Cuaca : Hujan Ringan
Lalin : Lancar
Rekayasa Lalin : -
https://youtu.be/9bZkp7q19f0?si=xyz

*Pel. Ketapang*
*1 Apr 2026, 17:10 WIB*
Cuaca : Cerah
Lalin : Padat
Rekayasa Lalin : -
https://www.youtube.com/shorts/aqz-KE-bpKQ

*Pel. Gilimanuk*
*1 Apr 2026, 18:10 WITA*
Cuaca : Cerah
Lalin : Ramai Lancar
Rekayasa Lalin : -
https://m.youtube.com/watch?v=jNQXAC9IVRw&feature=youtu.be
"""


def make_video_id(i: int) -> str:
    base = f"vid{i:08d}"  # 11 karakter
    return base[:11]


def make_report(n: int) -> str:
    header = "Hari/Tanggal : *Rabu, 1 April 2026*\nJam Laporan : *00:00* - *23:59*\n\n"
    blocks = []
    for i in range(n):
        blocks.append(BLOCK_TEMPLATE.format(
            loc=f"Pel. Lokasi {i % 7}",
            day=1,
            hh=f"{(i // 60) % 24:02d}",
            mm=f"{i % 60:02d}",
            tz="WIB",
            lalin="Padat" if i % 2 else "Lancar",
            url=f"https://www.youtube.com/watch?v={make_video_id(i)}&si=track{i}",
        ))
    return header + "\n".join(blocks)


class FakeDownloader:
    """Downloader tiruan. Perilaku ditentukan per ID video melalui `behaviors`.

    - "ok" (default): menulis file 1 KiB dan melaporkan progres nyata.
    - "fail": gagal permanen (mis. video privat).
    - "flaky": gagal retryable sekali, lalu berhasil.
    - "block": menunggu sampai dibatalkan.
    """

    def __init__(self, behaviors: dict[str, str] | None = None, size: int = 1024):
        self.behaviors = behaviors or {}
        self.size = size
        self.calls: list[str] = []
        self._flaky_seen: set[str] = set()
        self.lock = threading.Lock()
        self.started = threading.Event()

    def download(self, url, out_dir: Path, base_name, quality, on_progress, cancel_event):
        vid = url.split("v=")[-1]
        with self.lock:
            self.calls.append(vid)
        behavior = self.behaviors.get(vid, "ok")
        self.started.set()
        if behavior == "fail":
            raise DownloadFailedError("Video bersifat privat dan tidak dapat diakses.", retryable=False)
        if behavior == "flaky" and vid not in self._flaky_seen:
            self._flaky_seen.add(vid)
            raise DownloadFailedError("Koneksi terputus atau jaringan bermasalah.", retryable=True)
        if behavior == "block":
            while not cancel_event.is_set():
                time.sleep(0.01)
            raise DownloadCancelledError("Dibatalkan oleh pengguna")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{base_name}.mp4"
        half = self.size // 2
        on_progress(ProgressInfo("downloading", half, self.size, 50.0, 1000.0, 1))
        on_progress(ProgressInfo("processing"))
        path.write_bytes(b"\0" * self.size)
        return DownloadResult(path=path, size=self.size, ext="mp4", height=quality)


@pytest.fixture
def tmp_dirs(tmp_path):
    out = tmp_path / "Arsip Video"
    h = tmp_path / "history"
    out.mkdir()
    h.mkdir()
    return out, h

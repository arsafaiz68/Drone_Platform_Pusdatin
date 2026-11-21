"""Fixture pengujian AI Drone Trimmer.

Video uji dibuat secara sintetis dengan FFmpeg (tidak perlu rekaman drone asli):
* roundtrip.mp4  : kamera "terbang" menyusuri panorama lalu kembali (putar balik di 20 dtk)
* oneway.mp4     : hanya perjalanan pergi
* short720.mp4   : 12 dtk, 1280x720, 25 fps, ada audio & creation_time
* tiny.mp4       : 3 dtk (durasi pendek)
* long.mp4       : 4 menit pergi-kembali beresolusi kecil (durasi panjang)
* broken.mp4     : file rusak (untuk uji isolasi kegagalan)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

ASSETS = Path(os.environ.get("ADT_TEST_ASSETS", ROOT / "tests" / ".assets"))


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _panorama(path: Path, w=4000, h=480, seed=0):
    import cv2
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.uint8)
    for i in range(0, w, 10):
        hue = int((i / w * 3 * 180) % 180)
        sat = int(150 + 80 * np.sin(i / 170))
        val = int(140 + 70 * np.cos(i / 90))
        img[:, i:i + 10] = (hue, max(0, min(255, sat)), max(0, min(255, val)))
    img = cv2.cvtColor(img, cv2.COLOR_HSV2BGR).astype(int)
    img = np.clip(img + rng.integers(-30, 30, (h, w, 1)), 0, 255).astype(np.uint8)
    # "kendaraan" berupa kotak-kotak kecil agar ada tekstur & tepi
    for _ in range(400):
        x, y = rng.integers(0, w - 30), rng.integers(0, h - 20)
        cv2.rectangle(img, (int(x), int(y)), (int(x) + 24, int(y) + 12), tuple(int(c) for c in rng.integers(0, 255, 3)), -1)
    cv2.imwrite(str(path), img)


@pytest.fixture(scope="session")
def assets() -> dict[str, Path]:
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg tidak tersedia")
    ASSETS.mkdir(parents=True, exist_ok=True)
    pano = ASSETS / "pano.png"
    if not pano.exists():
        _panorama(pano)
    files = {
        "roundtrip": ASSETS / "roundtrip.mp4",
        "oneway": ASSETS / "oneway.mp4",
        "short720": ASSETS / "short720.mp4",
        "tiny": ASSETS / "tiny.mp4",
        "long": ASSETS / "long.mp4",
        "broken": ASSETS / "broken.mp4",
    }
    if not files["roundtrip"].exists():
        _ffmpeg("-loop", "1", "-i", str(pano), "-t", "40", "-r", "30", "-vf",
                "crop=640:480:'if(lt(t,20),t*160,(40-t)*160)':0,format=yuv420p",
                "-c:v", "libx264", "-preset", "ultrafast", "-g", "30", str(files["roundtrip"]))
    if not files["oneway"].exists():
        _ffmpeg("-loop", "1", "-i", str(pano), "-t", "24", "-r", "30", "-vf",
                "crop=640:480:'t*140':0,format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                str(files["oneway"]))
    if not files["short720"].exists():
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25:d=12", "-f", "lavfi", "-i", "sine=f=440:d=12",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
                "-metadata", "creation_time=2026-11-18T00:30:00Z", str(files["short720"]))
    if not files["tiny"].exists():
        _ffmpeg("-f", "lavfi", "-i", "testsrc=s=320x240:r=30:d=3", "-c:v", "libx264", "-preset", "ultrafast",
                str(files["tiny"]))
    if not files["long"].exists():
        _ffmpeg("-loop", "1", "-i", str(pano), "-t", "240", "-r", "24", "-vf",
                "crop=640:480:'if(lt(t,120),t*28,(240-t)*28)':0,scale=320:240,format=yuv420p",
                "-c:v", "libx264", "-preset", "ultrafast", str(files["long"]))
    if not files["broken"].exists():
        files["broken"].write_bytes(os.urandom(40_000))
    return files


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Direktori data & database baru untuk setiap tes."""
    monkeypatch.setenv("ADT_DATA_DIR", str(tmp_path / "data"))
    from app.core.config import paths
    from app.database import db
    paths.refresh()
    db.init_db()
    yield {"data": tmp_path / "data", "paths": paths, "db": db}
    from app.services import export_service
    try:
        export_service.wait_all(120)
    except TimeoutError:
        pass


@pytest.fixture()
def worker(env):
    from app.workers import batch_worker
    batch_worker.start(interval=0.05)
    yield batch_worker
    batch_worker.stop()


def wait_batch(batch_id: int, timeout: float = 120):
    import time
    from app.services import batch_service
    t0 = time.time()
    while time.time() - t0 < timeout:
        b = batch_service.get_batch(batch_id)
        st = b["stats"]
        if st["waiting"] == 0 and st["processing"] == 0 and b["status"] not in ("running", "queued"):
            return b
        if st["waiting"] == 0 and st["processing"] == 0:
            batch_service.refresh_batch_status(batch_id)
        time.sleep(0.1)
    raise TimeoutError(f"Batch {batch_id} belum selesai: {batch_service.get_batch(batch_id)['stats']}")


@pytest.fixture()
def project(env):
    from app.services import batch_service
    return batch_service.create_project("Proyek Uji", "terminal", location_name="Terminal Pulogebang")

"""Manifest informasi video hasil unduhan.

Setiap video yang berhasil diunduh dicatat di file ``_info_video_drone.json`` pada
folder tujuan. Isinya adalah hasil parsing laporan WhatsApp (lokasi, tanggal,
waktu, kondisi lalin, cuaca, dst.) sehingga Drone Video Trimmer dapat membaca
informasi video secara otomatis, juga ketika folder diimpor di kemudian hari.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("app.downloader.manifest")

MANIFEST_NAME = "_info_video_drone.json"
_lock = threading.Lock()

# Nama file standar downloader: DD.MM_HH.MM_Lokasi_Lalin(_NN).ext
_NAME_RE = re.compile(r"^(\d{2})\.(\d{2})_(\d{2})\.(\d{2})_([^_]+)_(.+?)(?:_(\d{2}))?$")


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("videos"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "generator": "Drone Video Downloader", "videos": {}}


def read_manifest(folder: str | Path) -> dict[str, dict]:
    """Kembalikan {nama_file: info} dari manifest di folder (kosong bila tidak ada)."""
    path = Path(folder) / MANIFEST_NAME
    if not path.is_file():
        return {}
    return _read(path)["videos"]


def record_video(output_path: str | Path, metadata: dict[str, Any], *, batch_id: str | None = None,
                 job_id: str | None = None, report_date: str | None = None) -> None:
    """Tambahkan/perbarui satu video di manifest folder tujuannya. Tidak pernah melempar error."""
    try:
        p = Path(output_path)
        manifest = p.parent / MANIFEST_NAME
        info = {k: metadata.get(k) for k in ("location", "date", "time", "timezone", "weather",
                                              "wave_height", "wave_direction", "traffic",
                                              "traffic_engineering", "notes", "url_original", "video_id")}
        info.update({"filename": p.name, "batch_id": batch_id, "job_id": job_id, "report_date": report_date,
                     "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        with _lock:
            data = _read(manifest)
            data["videos"][p.name] = info
            tmp = manifest.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, manifest)
    except Exception as exc:  # noqa: BLE001 - manifest hanya pelengkap
        log.warning("Gagal menulis manifest untuk %s: %s", output_path, exc)


def guess_from_filename(filename: str, year: int | None = None) -> dict[str, Any]:
    """Tebak informasi dari nama file standar downloader (bila manifest tidak tersedia).

    ``27.03_14.00_Pel Merak_Normal Lancar.mp4`` -> lokasi "Pel Merak", tanggal 27/03,
    waktu 14:00, lalin "Normal Lancar". Tahun diambil dari ``year`` atau tahun berjalan.
    """
    stem = Path(filename).stem
    m = _NAME_RE.match(stem)
    if not m:
        return {}
    dd, mo, hh, mi, loc, traffic, _n = m.groups()
    out: dict[str, Any] = {"location": loc.strip() or None, "traffic": traffic.strip() or None}
    try:
        out["date"] = date(year or date.today().year, int(mo), int(dd)).isoformat()
    except ValueError:
        pass
    if int(hh) < 24 and int(mi) < 60:
        out["time"] = f"{int(hh):02d}:{int(mi):02d}"
    out["guessed"] = True
    return out

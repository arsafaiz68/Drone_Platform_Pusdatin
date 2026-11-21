"""Jembatan Drone Video Downloader -> Drone Video Trimmer.

Hasil unduhan beserta informasi parsing laporan (lokasi, tanggal, waktu, kondisi
lalin) dibaca langsung dari riwayat batch downloader atau dari manifest
``_info_video_drone.json`` di folder video, sehingga operator tidak perlu mengisi
informasi video satu per satu di Trimmer.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..core.config import MAX_BATCH_VIDEOS, VIDEO_EXTENSIONS
from ..downloader.manifest import MANIFEST_NAME, guess_from_filename, read_manifest
from . import batch_service
from .timeline_service import NotFound, ValidationError

_OK = {"success", "skipped"}


def _video_entry(path: str | None, info: dict, **extra) -> dict:
    exists = bool(path and os.path.isfile(path))
    return {
        "path": path,
        "filename": Path(path).name if path else None,
        "exists": exists,
        "size_bytes": os.path.getsize(path) if exists else None,
        "info": info,
        "fields": batch_service.info_from_download(info),
        **extra,
    }


def _job_entry(batch: dict, job: dict) -> dict:
    meta = dict(job.get("metadata") or {})
    meta.setdefault("report_date", batch.get("report_date"))
    meta["batch_id"] = batch["id"]
    meta["job_id"] = job["id"]
    return _video_entry(job.get("output_path"), meta, job_id=job["id"], index=job.get("index"),
                        status=job.get("status"))


def list_download_batches(manager) -> list[dict]:
    """Riwayat batch downloader, terbaru dulu, beserta video yang berhasil diunduh."""
    out = []
    for b in manager.list():
        d = b.to_dict()
        videos = [_job_entry(d, j) for j in d.get("jobs") or [] if j.get("status") in _OK and j.get("output_path")]
        out.append({
            "id": d["id"], "created_at": d["created_at"], "report_date": d.get("report_date"),
            "output_dir": d.get("output_dir"), "status": d.get("status"), "summary": d.get("summary"),
            "videos": videos, "available": sum(1 for v in videos if v["exists"]),
        })
    return out


def download_batch_videos(manager, batch_id: str, job_ids: list[str] | None = None) -> list[dict]:
    try:
        b = manager.get(batch_id)
    except Exception as e:  # noqa: BLE001 - BatchError milik modul downloader
        raise NotFound(f"Batch unduhan {batch_id} tidak ditemukan") from e
    d = b.to_dict()
    wanted = set(job_ids or [])
    vids = [_job_entry(d, j) for j in d.get("jobs") or []
            if j.get("status") in _OK and j.get("output_path") and (not wanted or j["id"] in wanted)]
    if not vids:
        raise ValidationError("Batch unduhan ini belum memiliki video yang berhasil diunduh.")
    return vids


def scan_folder(folder: str) -> dict:
    """Daftar video di folder (tidak rekursif) beserta informasinya dari manifest / nama file."""
    p = Path(os.path.expandvars(os.path.expanduser(folder or "")))
    if not p.is_dir():
        raise NotFound("Folder tidak ditemukan.")
    manifest = read_manifest(p)
    videos = []
    for f in sorted(p.iterdir(), key=lambda x: x.name.lower()):
        if not f.is_file() or f.suffix.lower() not in VIDEO_EXTENSIONS or f.name.endswith(".part.mp4"):
            continue
        info = manifest.get(f.name)
        source = "manifest" if info else None
        if not info:
            info = guess_from_filename(f.name)
            source = "filename" if info else None
        videos.append(_video_entry(str(f), info or {}, info_source=source))
    return {"path": str(p), "has_manifest": bool(manifest), "manifest_name": MANIFEST_NAME, "videos": videos}


def import_videos(batch_id: int, items: list[dict[str, Any]]) -> list[dict]:
    """Tambahkan video ke batch sebagai path lokal (tanpa disalin) beserta informasinya."""
    if not items:
        raise ValidationError("Tidak ada video yang dipilih untuk diimpor.")
    if len(items) > MAX_BATCH_VIDEOS:
        raise ValidationError(f"Maksimal {MAX_BATCH_VIDEOS} video per batch ({len(items)} dipilih). "
                              "Pisahkan menjadi beberapa batch.")
    missing = [i["path"] for i in items if not i.get("path") or not os.path.isfile(i["path"])]
    if missing:
        raise ValidationError("File video tidak ditemukan di komputer: " + ", ".join(map(str, missing)))
    existing = {os.path.normcase(os.path.abspath(r["path"]))
                for r in batch_service.list_items(batch_id)}
    fresh = [i for i in items if os.path.normcase(os.path.abspath(i["path"])) not in existing]
    if not fresh:
        raise ValidationError("Semua video yang dipilih sudah ada di batch ini.")
    return batch_service.add_local_paths(batch_id, [i["path"] for i in fresh],
                                         [i.get("info") or None for i in fresh])

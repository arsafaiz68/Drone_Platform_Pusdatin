"""Hapus batch & ekspor hasil ke ZIP.

* ``delete_batch``: menghapus batch beserta video sumber terdaftar, kandidat, video hasil, dan file
  sementara milik aplikasi (salinan unggahan, proxy preview, thumbnail). File video sumber asli
  (path lokal / folder unduhan) TIDAK pernah dihapus. File hasil ekspor dipertahankan kecuali
  diminta (``delete_exports=True``).
* ``build_zip``: mengemas video hasil (mp4 + .json metadata) satu batch atau satu proyek ke ZIP,
  ditambah ``daftar_video_hasil.csv`` berisi ringkasan informasi tiap video.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from ..core.config import paths
from ..core.logging_setup import get_logger
from ..database import db
from .timeline_service import NotFound, ValidationError

log = get_logger("archive")

_BUSY_ITEMS = ("analyzing", "processing", "analyzed")


def _safe_unlink(p: str | Path | None, inside: Path) -> bool:
    """Hapus file hanya bila berada di dalam folder milik aplikasi."""
    if not p:
        return False
    try:
        rp, base = Path(p).resolve(), inside.resolve()
        if rp.is_file() and rp.is_relative_to(base):
            rp.unlink()
            return True
    except OSError:
        pass
    return False


# ====================================================================== hapus batch
def delete_batch(bid: int, delete_exports: bool = False) -> dict:
    b = db.get("batch_jobs", bid)
    if not b:
        raise NotFound("Batch tidak ditemukan")
    if b["status"] in ("running", "queued"):
        raise ValidationError("Batch sedang berjalan. Jeda atau batalkan batch terlebih dahulu sebelum menghapus.")
    if db.scalar(f"SELECT COUNT(*) FROM batch_items WHERE batch_id=? AND status IN {_BUSY_ITEMS}", (bid,)):
        raise ValidationError("Masih ada video yang sedang dianalisis. Tunggu sebentar lalu coba lagi.")
    finals = db.query("SELECT id FROM final_videos WHERE batch_id=? OR source_video_id IN "
                      "(SELECT id FROM source_videos WHERE batch_id=?)", (bid, bid))
    fids = [f["id"] for f in finals]
    if fids:
        ph = ",".join("?" * len(fids))
        if db.scalar(f"SELECT COUNT(*) FROM export_jobs WHERE final_video_id IN ({ph}) "
                     "AND status IN ('queued','running')", fids):
            raise ValidationError("Ekspor batch ini masih berjalan. Tunggu sampai selesai lalu coba lagi.")
    videos = db.query("SELECT id, path, is_uploaded, proxy_path FROM source_videos WHERE batch_id=?", (bid,))

    removed_files = 0
    if delete_exports and fids:
        ph = ",".join("?" * len(fids))
        for e in db.query(f"SELECT output_path, output_files_json FROM export_jobs WHERE final_video_id IN ({ph})", fids):
            for f in {e.get("output_path"), *(e.get("output_files") or [])}:
                if f and os.path.isfile(f):
                    try:
                        os.remove(f)
                        removed_files += 1
                    except OSError:
                        pass
    # file sementara milik aplikasi
    for v in videos:
        if v["is_uploaded"]:
            removed_files += _safe_unlink(v["path"], paths.uploads)
        removed_files += _safe_unlink(v.get("proxy_path"), paths.temporary)
        for t in (paths.temporary / "thumbs").glob(f"v{v['id']}_*.jpg"):
            removed_files += _safe_unlink(t, paths.temporary)
    for fid in fids:
        for t in (paths.temporary / "previews").glob(f"final_{fid}_*.mp4"):
            removed_files += _safe_unlink(t, paths.temporary)
    up = paths.uploads / f"batch_{bid:04d}"
    if up.is_dir():
        shutil.rmtree(up, ignore_errors=True)

    with db.transaction() as conn:
        if fids:
            ph = ",".join("?" * len(fids))
            conn.execute(f"DELETE FROM final_videos WHERE id IN ({ph})", fids)
        conn.execute("DELETE FROM batch_jobs WHERE id=?", (bid,))  # cascade: kelompok, video, item, kandidat
    log.info("Batch %s dihapus (%d video, %d video hasil, %d file)", bid, len(videos), len(fids), removed_files)
    return {"deleted": True, "batch_id": bid, "videos": len(videos), "final_videos": len(fids),
            "files_removed": removed_files, "exports_kept": not delete_exports}


# ====================================================================== ZIP
def _slug(text: str) -> str:
    t = re.sub(r"[^A-Za-z0-9._-]+", "_", text or "").strip("_")
    return t[:60] or "hasil"


def _finals(batch_id: int | None, project_id: int | None) -> list[dict]:
    if batch_id:
        return db.query("SELECT * FROM final_videos WHERE batch_id=? ORDER BY id", (batch_id,))
    return db.query("SELECT * FROM final_videos WHERE project_id=? ORDER BY batch_id, id", (project_id,))


def zip_contents(batch_id: int | None = None, project_id: int | None = None) -> list[dict]:
    """Daftar file hasil ekspor terakhir (berhasil) per video hasil."""
    out = []
    for f in _finals(batch_id, project_id):
        e = db.query_one("SELECT * FROM export_jobs WHERE final_video_id=? AND kind='final' AND status='done' "
                         "ORDER BY id DESC LIMIT 1", (f["id"],))
        if not e or not e.get("output_path") or not os.path.isfile(e["output_path"]):
            continue
        sv = db.get("source_videos", f["source_video_id"]) if f.get("source_video_id") else None
        batch = db.get("batch_jobs", f["batch_id"]) if f.get("batch_id") else None
        files = [p for p in (e.get("output_files") or [e["output_path"]]) if p and os.path.isfile(p)]
        out.append({"final": f, "export": e, "files": files, "source": sv, "batch": batch})
    return out


def build_zip(batch_id: int | None = None, project_id: int | None = None) -> tuple[Path, str]:
    if batch_id:
        owner = db.get("batch_jobs", batch_id)
        if not owner:
            raise NotFound("Batch tidak ditemukan")
        project = db.get("projects", owner["project_id"]) or {}
        label = f"{project.get('name', 'Proyek')}_{owner['name']}"
    else:
        owner = db.get("projects", project_id)
        if not owner:
            raise NotFound("Proyek tidak ditemukan")
        label = owner["name"]
    items = zip_contents(batch_id, project_id)
    if not items:
        raise ValidationError("Belum ada video hasil yang berhasil diekspor. Ekspor video hasil terlebih dahulu.")
    name = f"{_slug(label)}_{datetime.now():%Y%m%d_%H%M%S}.zip"
    dst_dir = paths.temporary / "zips"
    dst_dir.mkdir(parents=True, exist_ok=True)
    for old in dst_dir.glob("*.zip"):  # hanya simpan ZIP terbaru agar tidak memenuhi disk
        try:
            old.unlink()
        except OSError:
            pass
    dst = dst_dir / name
    rows, used = [], set()
    multi_batch = project_id is not None and len({i["final"].get("batch_id") for i in items}) > 1
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
        for it in items:
            f, sv, b = it["final"], it["source"] or {}, it["batch"] or {}
            folder = f"{_slug(b.get('name', 'batch'))}/" if multi_batch else ""
            for p in it["files"]:
                arc = folder + Path(p).name
                k, stem, ext = 1, Path(arc).stem, Path(arc).suffix
                while arc.lower() in used:
                    arc = f"{folder}{stem}_{k:02d}{ext}"
                    k += 1
                used.add(arc.lower())
                # mp4 sudah terkompresi -> disimpan apa adanya (cepat); json/csv dikompresi
                ctype = zipfile.ZIP_STORED if p.lower().endswith(".mp4") else zipfile.ZIP_DEFLATED
                z.write(p, arc, compress_type=ctype)
            rows.append({
                "batch": b.get("name"), "file_hasil": folder + Path(it["export"]["output_path"]).name,
                "video_sumber": sv.get("filename"), "lokasi": f.get("location_name"),
                "jenis_lokasi": f.get("location_type"), "tanggal": f.get("event_date"), "waktu": f.get("event_time"),
                "kondisi_lalin": f.get("traffic_condition"), "target_dtk": f.get("target_duration"),
                "durasi_dtk": round(it["export"].get("duration") or 0, 2),
            })
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(rows)
        z.writestr("daftar_video_hasil.csv", "﻿" + buf.getvalue(), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("info_ekspor.json", json.dumps({
            "dibuat": datetime.now().isoformat(timespec="seconds"), "aplikasi": "Drone Video Platform",
            "batch_id": batch_id, "project_id": project_id, "jumlah_video": len(rows)}, ensure_ascii=False, indent=2),
            compress_type=zipfile.ZIP_DEFLATED)
    log.info("ZIP dibuat: %s (%d video)", dst, len(rows))
    return dst, name


def zip_summary(batch_id: int | None = None, project_id: int | None = None) -> dict:
    items = zip_contents(batch_id, project_id)
    finals = _finals(batch_id, project_id)
    return {"ready": len(items), "total_finals": len(finals),
            "size_bytes": sum(os.path.getsize(p) for i in items for p in i["files"])}


# ====================================================================== hapus proyek
def delete_project(pid: int, delete_exports: bool = False) -> dict:
    """Hapus proyek beserta seluruh batch-nya. File video sumber asli tidak pernah dihapus."""
    p = db.get("projects", pid)
    if not p:
        raise NotFound("Proyek tidak ditemukan")
    running = db.query("SELECT name FROM batch_jobs WHERE project_id=? AND status IN ('running','queued')", (pid,))
    if running:
        raise ValidationError("Batch berikut masih berjalan: " + ", ".join(r["name"] for r in running)
                              + ". Jeda atau batalkan terlebih dahulu.")
    totals = {"batches": 0, "videos": 0, "final_videos": 0, "files_removed": 0}
    for b in db.query("SELECT id FROM batch_jobs WHERE project_id=?", (pid,)):
        r = delete_batch(b["id"], delete_exports)
        totals["batches"] += 1
        for k in ("videos", "final_videos", "files_removed"):
            totals[k] += r[k]
    # sisa: video hasil gabungan lama / video tanpa batch
    for f in db.query("SELECT id FROM final_videos WHERE project_id=?", (pid,)):
        if delete_exports:
            for e in db.query("SELECT output_path, output_files_json FROM export_jobs WHERE final_video_id=?", (f["id"],)):
                for fp in {e.get("output_path"), *(e.get("output_files") or [])}:
                    if fp and os.path.isfile(fp):
                        try:
                            os.remove(fp)
                            totals["files_removed"] += 1
                        except OSError:
                            pass
        totals["final_videos"] += 1
    for v in db.query("SELECT id, path, is_uploaded, proxy_path FROM source_videos WHERE project_id=?", (pid,)):
        if v["is_uploaded"]:
            totals["files_removed"] += _safe_unlink(v["path"], paths.uploads)
        totals["files_removed"] += _safe_unlink(v.get("proxy_path"), paths.temporary)
        totals["videos"] += 1
    with db.transaction() as conn:
        conn.execute("DELETE FROM final_videos WHERE project_id=?", (pid,))
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))  # cascade: video, kelompok tersisa
    pdir = paths.projects / f"project_{pid:03d}"
    if pdir.is_dir():
        shutil.rmtree(pdir, ignore_errors=True)
    log.info("Proyek %s dihapus: %s", pid, totals)
    return {"deleted": True, "project_id": pid, **totals, "exports_kept": not delete_exports}

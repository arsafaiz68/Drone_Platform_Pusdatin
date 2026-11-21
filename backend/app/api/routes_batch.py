"""Endpoint batch, video sumber, kandidat, dan kelompok lokasi."""
from __future__ import annotations

import os

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ..core.config import MAX_BATCH_VIDEOS, paths
from ..database import db
from ..schemas.models import (BatchCreate, BatchUpdate, CandidateCreate, CandidateUpdate, GroupCreate,
                              GroupUpdate, LocalPaths, OrderIds, VideoUpdate, dump)
from ..services import archive_service, batch_service, export_service, timeline_service, video_service
from ..workers import batch_worker
from .media import stream_file

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- batch
@router.post("/batches")
def create_batch(body: BatchCreate):
    return batch_service.create_batch(body.project_id, body.name, body.final_duration, body.trip_mode,
                                      body.concurrency, body.metadata_mode, body.template_code, body.route)


@router.get("/batches")
def list_batches(project_id: int | None = None):
    return batch_service.list_batches(project_id)


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int):
    return batch_service.get_batch(batch_id)


@router.patch("/batches/{batch_id}")
def update_batch(batch_id: int, body: BatchUpdate):
    return batch_service.update_batch(batch_id, dump(body))


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: int, delete_exports: bool = False):
    """Hapus batch. File video sumber asli tidak dihapus; file hasil ekspor dihapus hanya bila diminta."""
    return archive_service.delete_batch(batch_id, delete_exports)


@router.get("/batches/{batch_id}/zip/summary")
def batch_zip_summary(batch_id: int):
    batch_service.get_batch(batch_id)
    return archive_service.zip_summary(batch_id=batch_id)


@router.get("/batches/{batch_id}/zip")
def batch_zip(batch_id: int):
    """Unduh seluruh video hasil batch (mp4 + json) + daftar_video_hasil.csv dalam satu ZIP."""
    path, name = archive_service.build_zip(batch_id=batch_id)
    return FileResponse(str(path), media_type="application/zip", filename=name)


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, delete_exports: bool = False):
    """Hapus proyek + seluruh batch-nya. File video sumber tidak dihapus; hasil ekspor opsional."""
    return archive_service.delete_project(project_id, delete_exports)


@router.get("/projects/{project_id}/zip/summary")
def project_zip_summary(project_id: int):
    return archive_service.zip_summary(project_id=project_id)


@router.get("/projects/{project_id}/zip")
def project_zip(project_id: int):
    """Unduh seluruh video hasil proyek (semua batch) dalam satu ZIP."""
    path, name = archive_service.build_zip(project_id=project_id)
    return FileResponse(str(path), media_type="application/zip", filename=name)


@router.post("/batches/{batch_id}/start")
def start_batch(batch_id: int):
    return batch_service.start_batch(batch_id)


@router.post("/batches/{batch_id}/pause")
def pause_batch(batch_id: int):
    return batch_service.pause_batch(batch_id)


@router.post("/batches/{batch_id}/resume")
def resume_batch(batch_id: int):
    return batch_service.resume_batch(batch_id)


@router.post("/batches/{batch_id}/cancel")
def cancel_batch(batch_id: int):
    return batch_service.cancel_batch(batch_id)


@router.post("/batches/{batch_id}/mark-reviewed")
def mark_reviewed(batch_id: int):
    return batch_service.mark_reviewed(batch_id)


@router.get("/batches/{batch_id}/items")
def batch_items(batch_id: int):
    return batch_service.list_items(batch_id)


@router.get("/batches/{batch_id}/report")
def batch_report(batch_id: int):
    return batch_service.batch_report(batch_id)


@router.post("/batches/{batch_id}/videos")
def upload_videos(batch_id: int, files: list[UploadFile] = File(...)):
    if len(files) > MAX_BATCH_VIDEOS:
        raise HTTPException(400, f"Maksimal {MAX_BATCH_VIDEOS} video per batch ({len(files)} dipilih). "
                                 "Pemrosesan tidak dimulai.")
    return batch_service.add_uploaded_videos(batch_id, [(f.filename, f.file) for f in files])


@router.post("/batches/{batch_id}/videos/paths")
def add_paths(batch_id: int, body: LocalPaths):
    """Path lokal; informasi video dibaca otomatis dari manifest downloader / nama file."""
    return batch_service.add_local_paths(batch_id, body.paths)


@router.delete("/batches/{batch_id}/videos/{video_id}")
def remove_video(batch_id: int, video_id: int):
    batch_service.remove_video(batch_id, video_id)
    return {"deleted": True}


@router.post("/batches/{batch_id}/videos/reorder")
def reorder_videos(batch_id: int, body: OrderIds):
    return batch_service.reorder_videos(batch_id, body.ids)


@router.post("/batches/{batch_id}/final-videos")
def build_finals(batch_id: int):
    """Buat SATU video hasil untuk SETIAP video sumber (24 video masuk -> 24 video hasil).

    Durasi tiap video hasil mengikuti durasi batch (10–60 dtk, kelipatan 5). Video yang sudah memiliki
    video hasil dipilih ulang otomatis. Video rusak (tanpa durasi) dilewati.
    """
    b = batch_service.get_batch(batch_id)
    created = []
    for it in batch_service.list_items(batch_id):
        if not it.get("duration") or it.get("status") == "cancelled":
            continue
        created.append(timeline_service.create_video_output(it["video_id"], b["final_duration"]))
    return created


@router.post("/batches/{batch_id}/export-all")
def export_all(batch_id: int, include_individual: bool = False):
    finals = timeline_service.list_finals(batch_id=batch_id)
    started, errors = [], []
    for f in finals:
        try:
            started.append(export_service.start_export(f["id"], "final"))
            if include_individual:
                started.append(export_service.start_export(f["id"], "individual"))
        except export_service.ExportError as e:
            errors.append({"final_video_id": f["id"], "error": str(e)})
    return {"started": started, "errors": errors}


@router.get("/batches/{batch_id}/final-videos")
def batch_finals(batch_id: int):
    return timeline_service.list_finals(batch_id=batch_id)


# ---------------------------------------------------------------- video
@router.get("/videos/{video_id}")
def get_video(video_id: int):
    return batch_service.get_video(video_id)


@router.patch("/videos/{video_id}")
def update_video(video_id: int, body: VideoUpdate):
    return batch_service.update_video(video_id, dump(body))


@router.post("/videos/{video_id}/reviewed")
def video_reviewed(video_id: int, reviewed: bool = True):
    """Tandai video selesai direview (atau kembalikan ke 'Menunggu review')."""
    batch_service.get_video(video_id)
    timeline_service.set_review_status(video_id, reviewed)
    return batch_service.get_video(video_id)


@router.post("/videos/{video_id}/analyze")
def analyze_video(video_id: int):
    batch_service.get_video(video_id)
    try:
        return batch_worker.analyze_now(video_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/videos/{video_id}/candidates")
def candidates(video_id: int, include_deleted: bool = False):
    batch_service.get_video(video_id)
    return timeline_service.list_candidates(video_id, include_deleted)


@router.post("/videos/{video_id}/candidates")
def add_candidate(video_id: int, body: CandidateCreate):
    return timeline_service.add_candidate(video_id, body.start, body.end, body.point_code, body.direction,
                                          body.traffic)


@router.get("/videos/{video_id}/stream")
def stream_video(video_id: int, request: Request, proxy: bool = True):
    v = db.get("source_videos", video_id)
    if not v:
        raise HTTPException(404, "Video tidak ditemukan")
    path = v["proxy_path"] if proxy and v.get("proxy_path") and os.path.exists(v["proxy_path"]) else v["path"]
    return stream_file(path, request)


@router.get("/videos/{video_id}/thumbnail")
def video_thumbnail(video_id: int, t: float = 0.0):
    v = db.get("source_videos", video_id)
    if not v:
        raise HTTPException(404, "Video tidak ditemukan")
    dst = paths.temporary / "thumbs" / f"v{video_id}_{int(t * 10)}.jpg"
    if not dst.exists():
        try:
            video_service.thumbnail(v["path"], t, str(dst))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"Thumbnail gagal: {e}")
    return FileResponse(str(dst), media_type="image/jpeg")


@router.patch("/candidates/{candidate_id}")
def update_candidate(candidate_id: int, body: CandidateUpdate):
    return timeline_service.update_candidate(candidate_id, dump(body))


@router.post("/candidates/{candidate_id}/reset")
def reset_candidate(candidate_id: int):
    return timeline_service.reset_candidate(candidate_id)


@router.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: int):
    """Hapus (tolak) kandidat; potongan video hasil yang memakainya ikut dihapus (durasi berkurang)."""
    return timeline_service.delete_candidate(candidate_id)


@router.post("/videos/{video_id}/verify-all")
def verify_all_video(video_id: int):
    """Verifikasi Semua: terima seluruh kandidat AI video ini."""
    r = timeline_service.verify_all(video_id)
    return {**r, "video": batch_service.get_video(video_id)}


@router.post("/batches/{batch_id}/verify-all")
def verify_all_batch(batch_id: int):
    """Verifikasi Semua untuk seluruh video batch yang sudah dianalisis."""
    total, videos = 0, 0
    for it in batch_service.list_items(batch_id):
        if it["status"] in ("review", "done"):
            total += timeline_service.verify_all(it["video_id"])["verified"]
            videos += 1
    return {"verified": total, "videos": videos, "batch": batch_service.get_batch(batch_id)}


# ---------------------------------------------------------------- kelompok lokasi
@router.post("/location-groups")
def create_group(body: GroupCreate):
    return batch_service.create_group(body.batch_id, body.name, body.location_name, body.traffic_condition,
                                      body.event_date, body.event_time)


@router.get("/location-groups/{group_id}")
def get_group(group_id: int):
    return batch_service.get_group(group_id)


@router.patch("/location-groups/{group_id}")
def update_group(group_id: int, body: GroupUpdate):
    g = batch_service.update_group(group_id, dump(body))
    b = db.get("batch_jobs", g["batch_id"]) if g.get("batch_id") else None
    # Mode metadata "sama untuk seluruh video": salin ke video hasil kelompok ini. Informasi yang
    # sudah dimiliki video sumber sendiri (mis. dari Drone Video Downloader) tidak ditimpa.
    if b and b["metadata_mode"] == "shared":
        changes = {k: v for k, v in dump(body).items()
                   if k in ("location_name", "traffic_condition", "event_date", "event_time")}
        for f in g["final_videos"]:
            if f.get("cross_location"):
                continue
            full = db.get("final_videos", f["id"])
            own = db.get("source_videos", full["source_video_id"]) if full.get("source_video_id") else None
            upd = {k: v for k, v in changes.items() if not (own and own.get(k))}
            if upd:
                timeline_service.update_final(f["id"], upd)
    return batch_service.get_group(group_id)


@router.delete("/location-groups/{group_id}")
def delete_group(group_id: int):
    batch_service.delete_group(group_id)
    return {"deleted": True}

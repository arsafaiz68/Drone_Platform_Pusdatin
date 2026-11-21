"""Endpoint integrasi: impor hasil Drone Video Downloader ke Drone Video Trimmer."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas.models import BatchFromDownload, ImportRequest
from ..services import batch_service, integration_service
from ..services.timeline_service import ValidationError

router = APIRouter(prefix="/api/integration", tags=["Integrasi"])


def _manager(request: Request):
    return request.app.state.downloader.jobs


@router.get("/downloads")
def downloads(request: Request):
    """Riwayat batch Drone Video Downloader beserta video & informasi hasil parsing."""
    return integration_service.list_download_batches(_manager(request))


@router.get("/downloads/{dl_batch_id}")
def download_batch(dl_batch_id: str, request: Request):
    return integration_service.download_batch_videos(_manager(request), dl_batch_id)


@router.get("/folder")
def folder(path: str):
    """Video di sebuah folder lokal + informasi dari manifest downloader / nama file."""
    return integration_service.scan_folder(path)


def _items(body, request: Request) -> list[dict]:
    if body.items:
        return [i.model_dump() for i in body.items]
    if body.downloader_batch_id:
        vids = integration_service.download_batch_videos(_manager(request), body.downloader_batch_id,
                                                         body.job_ids)
        return [{"path": v["path"], "info": v["info"]} for v in vids if v["exists"]]
    raise ValidationError("Pilih batch unduhan atau daftar video yang akan diimpor.")


@router.post("/batches/{batch_id}/import")
def import_into_batch(batch_id: int, body: ImportRequest, request: Request):
    """Tambahkan video hasil unduhan ke batch Trimmer, informasi video terisi otomatis."""
    added = integration_service.import_videos(batch_id, _items(body, request))
    return {"added": len(added), "videos": added, "batch": batch_service.get_batch(batch_id)}


@router.post("/batch-from-download")
def batch_from_download(body: BatchFromDownload, request: Request):
    """Buat batch Trimmer baru langsung dari hasil unduhan (opsional langsung dimulai)."""
    items = _items(body, request)
    if not items:
        raise ValidationError("Tidak ada video unduhan yang masih tersedia di disk.")
    b = batch_service.create_batch(body.project_id, body.name, body.final_duration, body.trip_mode,
                                   body.concurrency, "per_final")
    try:
        integration_service.import_videos(b["id"], items)
    except Exception:
        batch_service.delete_batch_if_empty(b["id"])
        raise
    if body.start:
        batch_service.start_batch(b["id"])
    return batch_service.get_batch(b["id"])

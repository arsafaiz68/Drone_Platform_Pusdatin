"""Endpoint video final, timeline editing, metadata output, dan ekspor."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..database import db
from ..schemas.models import (Allocations, ExportRequest, FinalCreate, FinalUpdate, OrderIds, SegmentCreate,
                              SegmentReplace, SegmentUpdate, dump)
from ..services import export_service, naming_service, timeline_service
from .media import stream_file

router = APIRouter(prefix="/api")


@router.post("/final-videos")
def create_final(body: FinalCreate):
    return timeline_service.create_final_video(
        body.project_id, body.group_ids, body.target_duration, body.trip_mode, body.batch_id,
        body.cross_location, body.location_name, body.traffic_condition, body.event_date, body.event_time,
        body.auto_select, body.source_video_id)


@router.get("/final-videos")
def list_finals(batch_id: int | None = None, project_id: int | None = None):
    return timeline_service.list_finals(batch_id, project_id)


@router.get("/final-videos/{final_video_id}")
def get_final(final_video_id: int):
    return timeline_service.get_final(final_video_id)


@router.patch("/final-videos/{final_video_id}")
def update_final(final_video_id: int, body: FinalUpdate):
    return timeline_service.update_final(final_video_id, dump(body))


@router.get("/final-videos/{final_video_id}/metadata")
def final_metadata(final_video_id: int):
    f = timeline_service.get_final(final_video_id)
    return {"metadata": f["metadata"], "suggested_filename": f["suggested_filename"],
            "output_filename": f["output_filename"], "time_source": f["time_source_resolved"],
            "filename_valid": naming_service.is_valid_standard(f["output_filename"] or ""),
            "filename_error": f.get("filename_error")}


@router.post("/final-videos/{final_video_id}/select-segments")
def select_segments(final_video_id: int):
    return timeline_service.select_for_final(final_video_id)


@router.post("/final-videos/{final_video_id}/segments")
def add_segment(final_video_id: int, body: SegmentCreate):
    return timeline_service.add_segment(final_video_id, body.candidate_id, body.video_id, body.start, body.end,
                                        body.point_code, body.direction, body.position, body.role)


@router.patch("/final-videos/{final_video_id}/segments/{segment_id}")
def update_segment(final_video_id: int, segment_id: int, body: SegmentUpdate):
    _own(final_video_id, segment_id)
    return timeline_service.update_segment(segment_id, dump(body))


@router.delete("/final-videos/{final_video_id}/segments/{segment_id}")
def delete_segment(final_video_id: int, segment_id: int):
    _own(final_video_id, segment_id)
    return timeline_service.delete_segment(segment_id)


@router.post("/final-videos/{final_video_id}/segments/{segment_id}/reset")
def reset_segment(final_video_id: int, segment_id: int):
    _own(final_video_id, segment_id)
    return timeline_service.reset_segment(segment_id)


@router.post("/final-videos/{final_video_id}/segments/{segment_id}/replace")
def replace_segment(final_video_id: int, segment_id: int, body: SegmentReplace):
    _own(final_video_id, segment_id)
    return timeline_service.replace_segment(segment_id, body.candidate_id, body.keep_duration)


@router.post("/final-videos/{final_video_id}/reorder")
def reorder(final_video_id: int, body: OrderIds):
    return timeline_service.reorder_segments(final_video_id, body.ids)


@router.post("/final-videos/{final_video_id}/allocations")
def allocations(final_video_id: int, body: Allocations):
    return timeline_service.set_allocations(final_video_id, {int(k): v for k, v in body.allocations.items()})


@router.post("/final-videos/{final_video_id}/export")
def export(final_video_id: int, body: ExportRequest | None = None):
    kind = body.kind if body else "final"
    try:
        return export_service.start_export(final_video_id, kind)
    except export_service.ExportError as e:
        raise HTTPException(400, str(e))


@router.get("/final-videos/{final_video_id}/export-info")
def export_info(final_video_id: int):
    try:
        return export_service.export_info(final_video_id)
    except export_service.ExportError as e:
        raise HTTPException(400, str(e))


@router.post("/final-videos/{final_video_id}/preview")
def preview(final_video_id: int):
    try:
        return export_service.start_export(final_video_id, "preview")
    except export_service.ExportError as e:
        raise HTTPException(400, str(e))


def _own(final_id: int, seg_id: int):
    s = db.get("final_video_segments", seg_id)
    if not s or s["final_video_id"] != final_id:
        raise HTTPException(404, "Segmen tidak ditemukan pada video final ini")


# ---------------------------------------------------------------- ekspor
@router.get("/exports")
def list_exports(limit: int = 200):
    return db.query("""SELECT e.*, f.location_name, f.traffic_condition, f.target_duration, f.project_id,
                              p.name AS project_name
                       FROM export_jobs e JOIN final_videos f ON f.id=e.final_video_id
                       LEFT JOIN projects p ON p.id=f.project_id
                       WHERE e.kind <> 'preview' ORDER BY e.id DESC LIMIT ?""", (limit,))


@router.get("/exports/{export_id}")
def get_export(export_id: int):
    e = db.get("export_jobs", export_id)
    if not e:
        raise HTTPException(404, "Ekspor tidak ditemukan")
    e["exists"] = bool(e.get("output_path") and os.path.exists(e["output_path"]))
    return e


@router.get("/exports/{export_id}/download")
def download_export(export_id: int, request: Request, index: int | None = None):
    e = db.get("export_jobs", export_id)
    if not e or e["status"] != "done":
        raise HTTPException(404, "Hasil ekspor belum tersedia")
    path = e["output_path"]
    if index is not None:
        files = [f for f in (e.get("output_files") or []) if f.endswith(".mp4")]
        if index < 0 or index >= len(files):
            raise HTTPException(404, "File tidak ditemukan")
        path = files[index]
    if not path or not os.path.isfile(path):
        raise HTTPException(404, "File hasil ekspor tidak ditemukan di disk")
    return stream_file(path, request, download_name=Path(path).name)


@router.get("/exports/{export_id}/stream")
def stream_export(export_id: int, request: Request):
    e = db.get("export_jobs", export_id)
    if not e or e["status"] != "done":
        raise HTTPException(404, "Hasil belum tersedia")
    return stream_file(e["output_path"], request)

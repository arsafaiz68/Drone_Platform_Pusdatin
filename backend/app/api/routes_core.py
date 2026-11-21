"""Endpoint sistem, template, proyek, pengaturan, model AI."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..core.config import (APP_NAME, APP_VERSION, BATCH_STATUS_LABELS, CONCURRENCY_OPTIONS, DEFAULT_SETTINGS,
                           FINAL_DURATIONS, ITEM_STATUS_LABELS, MAX_BATCH_VIDEOS, TRAFFIC_CONDITIONS, paths)
from ..core.templates_config import all_templates, get_template, route_text
from ..database import db
from ..schemas.models import (ModelConfigCreate, ModelConfigUpdate, ProjectCreate, ProjectUpdate,
                              SettingsUpdate, dump)
from ..services import batch_service, hardware_service
from ..workers import batch_worker

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    hw = hardware_service.detect()
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION, "mode": hw["mode"],
            "ffmpeg": hw["ffmpeg_available"], "ffprobe": hw["ffprobe_available"],
            "active_items": batch_worker.active_items(), "data_dir": str(paths.data)}


@router.get("/meta")
def meta():
    return {"traffic_conditions": TRAFFIC_CONDITIONS, "final_durations": FINAL_DURATIONS,
            "concurrency_options": CONCURRENCY_OPTIONS, "max_batch_videos": MAX_BATCH_VIDEOS,
            "item_status_labels": ITEM_STATUS_LABELS, "batch_status_labels": BATCH_STATUS_LABELS,
            "trip_modes": {"outbound": "Pergi saja", "round_trip": "Pergi dan kembali"}}


# ---------------------------------------------------------------- template
def _tmpl_public(t: dict) -> dict:
    t["route_outbound_text"] = route_text(t["route_outbound"])
    t["route_return_text"] = route_text(t["route_return"])
    return t


@router.get("/templates")
def templates():
    return [_tmpl_public(t) for t in all_templates()]


@router.get("/templates/{code}")
def template(code: str):
    t = get_template(code)
    if not t:
        raise HTTPException(404, "Template tidak ditemukan")
    return _tmpl_public(t)


# ---------------------------------------------------------------- proyek
@router.post("/projects")
def create_project(body: ProjectCreate):
    return batch_service.create_project(body.name, body.template_code, body.description, body.location_name)


@router.get("/projects")
def list_projects():
    return batch_service.list_projects()


@router.get("/projects/{project_id}")
def get_project(project_id: int):
    p = batch_service.get_project(project_id)
    p["batches"] = batch_service.list_batches(project_id)
    return p


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate):
    return batch_service.update_project(project_id, dump(body))


@router.get("/dashboard")
def dashboard():
    hw = hardware_service.detect()
    return {
        "projects": db.scalar("SELECT COUNT(*) FROM projects"),
        "batches": db.scalar("SELECT COUNT(*) FROM batch_jobs"),
        "batches_running": db.scalar("SELECT COUNT(*) FROM batch_jobs WHERE status IN ('running','queued')"),
        "videos": db.scalar("SELECT COUNT(*) FROM source_videos"),
        "videos_review": db.scalar("SELECT COUNT(*) FROM batch_items WHERE status='review'"),
        "videos_failed": db.scalar("SELECT COUNT(*) FROM batch_items WHERE status='failed'"),
        "final_videos": db.scalar("SELECT COUNT(*) FROM final_videos"),
        "exports_done": db.scalar("SELECT COUNT(*) FROM export_jobs WHERE status='done' AND kind='final'"),
        "recent_batches": batch_service.list_batches()[:6],
        "recent_exports": db.query("SELECT e.*, f.location_name FROM export_jobs e JOIN final_videos f "
                                   "ON f.id=e.final_video_id WHERE e.kind<>'preview' ORDER BY e.id DESC LIMIT 6"),
        "hardware": hw,
    }


# ---------------------------------------------------------------- perangkat & pengaturan
@router.get("/hardware")
def hardware(refresh: bool = False):
    info = hardware_service.detect(force=refresh)
    info["usage"] = hardware_service.usage()
    return info


@router.get("/settings")
def get_settings():
    return {"values": db.get_settings(), "defaults": DEFAULT_SETTINGS, "data_dir": str(paths.data),
            "exports_dir": db.get_settings().get("output_dir") or str(paths.exports)}


@router.patch("/settings")
def update_settings(body: SettingsUpdate):
    vals = body.values
    if "default_concurrency" in vals and vals["default_concurrency"] not in CONCURRENCY_OPTIONS:
        raise HTTPException(400, "Concurrency harus 1, 2, atau 4.")
    if "default_final_duration" in vals and vals["default_final_duration"] not in FINAL_DURATIONS:
        raise HTTPException(400, "Durasi tiap video hasil harus kelipatan 5 detik, antara 10 dan 60 detik.")
    if vals.get("output_dir"):
        try:
            Path(vals["output_dir"]).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(400, f"Folder output tidak dapat dibuat: {e}")
    try:
        return {"values": db.set_settings(vals)}
    except KeyError as e:
        raise HTTPException(400, f"Pengaturan tidak dikenal: {e}")


# ---------------------------------------------------------------- model AI
@router.get("/models")
def models():
    cfgs = db.query("SELECT * FROM model_configurations ORDER BY id DESC")
    det = batch_worker._get_detector()
    onnx_files = [{"name": p.name, "path": str(p), "size_mb": round(p.stat().st_size / 2**20, 1)}
                  for p in sorted(paths.models.glob("*.onnx"))]
    return {
        "configurations": cfgs,
        "model_files": onnx_files,
        "models_dir": str(paths.models),
        "active_detector": {"name": det.name, "available": det.available, "validated": det.validated,
                            "device": getattr(det, "device", None)},
        "capabilities": [
            {"name": "Ekstraksi & sampling frame (OpenCV)", "status": "aktif", "requires_model": False},
            {"name": "Kualitas footage (ketajaman, eksposur, kestabilan)", "status": "aktif", "requires_model": False},
            {"name": "Deteksi adegan buram / tidak stabil", "status": "aktif", "requires_model": False},
            {"name": "Estimasi arah gerak kamera (phase correlation)", "status": "aktif", "requires_model": False},
            {"name": "Perubahan visual antarframe & kemiripan adegan", "status": "aktif", "requires_model": False},
            {"name": "Deteksi putar balik (kemiripan cermin + pembalikan gerak)", "status": "aktif",
             "requires_model": False, "note": "Heuristik visual, perlu verifikasi operator"},
            {"name": "Deteksi objek kendaraan/bus/orang", "status": "aktif" if det.available else "perlu model",
             "requires_model": True, "note": "Letakkan model YOLO ONNX di folder models"},
            {"name": "Pengenalan titik pemantauan / landmark", "status": "perlu model & dataset",
             "requires_model": True, "note": "Saat ini titik diestimasi dari urutan temporal template"},
            {"name": "Klasifikasi kondisi lalu lintas",
             "status": "saran belum tervalidasi" if det.available else "perlu model",
             "requires_model": True, "note": "Default 'Tidak Teridentifikasi'; operator menetapkan kondisi akhir"},
        ],
        "dataset": {"feedback_records": db.scalar("SELECT COUNT(*) FROM operator_feedback"),
                    "dataset_dir": str(paths.dataset)},
        "heuristic_mode": not det.available,
    }


@router.post("/models")
def add_model(body: ModelConfigCreate):
    if not os.path.isfile(body.path):
        raise HTTPException(400, "File model tidak ditemukan.")
    if not body.path.lower().endswith(".onnx"):
        raise HTTPException(400, "Saat ini hanya format ONNX yang didukung untuk detektor.")
    if body.enabled:
        db.execute("UPDATE model_configurations SET enabled=0 WHERE kind=?", (body.kind,))
    mid = db.insert("model_configurations", {"kind": body.kind, "name": body.name, "path": body.path,
                                             "enabled": int(body.enabled), "params_json": body.params,
                                             "validated": int(body.validated), "created_at": db.now_iso()})
    return db.get("model_configurations", mid)


@router.patch("/models/{model_id}")
def update_model(model_id: int, body: ModelConfigUpdate):
    m = db.get("model_configurations", model_id)
    if not m:
        raise HTTPException(404, "Model tidak ditemukan")
    upd = dump(body)
    if upd.get("enabled"):
        db.execute("UPDATE model_configurations SET enabled=0 WHERE kind=?", (m["kind"],))
    if "params" in upd:
        upd["params_json"] = upd.pop("params")
    db.update("model_configurations", model_id, upd)
    return db.get("model_configurations", model_id)


@router.post("/dataset/export")
def export_dataset():
    """Ekspor koreksi operator sebagai dataset berlabel (JSONL) untuk pelatihan model."""
    rows = db.query("SELECT * FROM operator_feedback ORDER BY id")
    paths.dataset.mkdir(parents=True, exist_ok=True)
    out = paths.dataset / f"operator_feedback_{db.now_iso().replace(':', '').replace('-', '')}.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            v = db.get("source_videos", r["video_id"]) if r.get("video_id") else None
            r["video_path"] = v["path"] if v else None
            r["video_filename"] = v["filename"] if v else None
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"file": str(out), "records": len(rows)}


@router.post("/open-folder")
def open_folder(body: dict):
    target = body.get("path") or str(paths.exports)
    p = Path(target)
    if p.is_file():
        p = p.parent
    if not p.exists():
        raise HTTPException(404, "Folder tidak ditemukan")
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except Exception as e:  # noqa: BLE001
        return {"opened": False, "path": str(p), "error": str(e)}
    return {"opened": True, "path": str(p)}

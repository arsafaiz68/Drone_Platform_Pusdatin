"""Background worker antrean batch.

* Dispatcher memeriksa batch berstatus ``running`` dan menjalankan video berstatus
  ``waiting`` sesuai concurrency batch (1/2/4) dan batas global perangkat.
* Setiap video dianalisis terpisah; kegagalan satu video tidak menghentikan video lain.
* Jeda: video yang sedang berjalan diselesaikan, video berikutnya tidak dimulai.
* Batal: video yang sedang berjalan dihentikan secara kooperatif.
"""
from __future__ import annotations

import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from ..core.logging_setup import get_logger
from ..core.templates_config import get_template, resolve_route
from ..database import db
from ..services import ai_service, batch_service, hardware_service, video_service

log = get_logger("worker")

_cancel_flags: dict[int, threading.Event] = {}
_active: set[int] = set()
_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_thread: threading.Thread | None = None
_stop = threading.Event()
_detector_cache: dict = {}


def request_cancel(item_id: int) -> None:
    with _lock:
        ev = _cancel_flags.get(item_id)
    if ev:
        ev.set()


def active_items() -> list[int]:
    with _lock:
        return sorted(_active)


def _get_detector() -> ai_service.Detector:
    cfg = db.query_one("SELECT * FROM model_configurations WHERE kind='detector' AND enabled=1 ORDER BY id DESC LIMIT 1")
    hw = hardware_service.detect()
    key = (cfg or {}).get("path"), hw["mode"], tuple(sorted(p.name for p in ai_service.paths.models.glob("*.onnx")))
    with _lock:
        if _detector_cache.get("key") != key:
            _detector_cache["key"] = key
            _detector_cache["det"] = ai_service.load_detector(cfg, hw["mode"] == "cuda")
        return _detector_cache["det"]


def _limit_threads(concurrency: int) -> None:
    try:
        import cv2
        cv2.setNumThreads(max(1, (os.cpu_count() or 2) // max(1, concurrency)))
    except Exception:  # noqa: BLE001
        pass


# ====================================================================== proses satu video
def process_item(item_id: int) -> None:
    cancel = threading.Event()
    with _lock:
        _cancel_flags[item_id] = cancel
        _active.add(item_id)
    item = db.get("batch_items", item_id)
    batch = db.get("batch_jobs", item["batch_id"])
    video = db.get("source_videos", item["video_id"])
    job_id = None
    last_write = [0.0]

    def progress(frac: float, stage: str):
        now = time.time()
        if now - last_write[0] > 0.7 or frac >= 1.0:
            last_write[0] = now
            db.update("batch_items", item_id, {"progress": round(0.9 * frac, 3), "stage": stage})

    try:
        _limit_threads(batch["concurrency"])
        db.update("batch_items", item_id, {"status": "analyzing", "progress": 0.01, "stage": "Membaca metadata",
                                           "started_at": db.now_iso(), "finished_at": None, "error": None})
        if video.get("probe_error") or not video.get("duration"):
            meta = video_service.probe(video["path"])  # melempar error bila file rusak
            db.update("source_videos", video["id"], {
                "duration": meta["duration"], "width": meta["width"], "height": meta["height"], "fps": meta["fps"],
                "codec": meta["codec"], "audio_codec": meta["audio_codec"], "creation_time": meta["creation_time"],
                "metadata_json": meta, "probe_error": None})
            video = db.get("source_videos", video["id"])
        # template per video (jenis lokasi video sendiri), cadangan: template batch
        tcode = video.get("template_code") if get_template(video.get("template_code") or "") else batch["template_code"]
        tmpl = get_template(tcode)
        route = resolve_route(tmpl, batch.get("route") if tcode == batch["template_code"] else None)
        detector = _get_detector()
        hw = hardware_service.detect()
        job_id = db.insert("analysis_jobs", {
            "video_id": video["id"], "batch_item_id": item_id, "status": "running",
            "device": hw["mode"], "detector": detector.name, "is_heuristic": int(not detector.available),
            "started_at": db.now_iso()})
        inp = ai_service.AnalysisInput(
            video_id=video["id"], path=video["path"], duration=float(video["duration"]), template=tmpl,
            route=route, trip_mode=batch["trip_mode"], point_mapping=video.get("point_mapping"),
            direction_override=video.get("direction_override"), settings=db.get_settings())
        result = ai_service.analyze_video(inp, detector, progress, cancel.is_set)
        if cancel.is_set():
            raise InterruptedError("Dibatalkan")
        db.update("batch_items", item_id, {"status": "analyzed", "progress": 0.9, "stage": "Analisis selesai"})

        # ---------- tahap pemrosesan: simpan kandidat + proxy preview
        db.update("batch_items", item_id, {"status": "processing", "stage": "Menyimpan kandidat segmen"})
        cands = result.pop("candidates")
        with db.transaction() as conn:
            conn.execute("DELETE FROM candidate_segments WHERE video_id=? AND origin='ai'", (video["id"],))
            for c in cands:
                import json
                conn.execute(
                    """INSERT INTO candidate_segments(video_id, analysis_job_id, point_code, direction, t_start, t_end,
                         ai_start, ai_end, ai_point_code, ai_direction, quality_score, relevance_score,
                         stability_score, sharpness_score, activity_score, object_density, confidence,
                         recommended_duration, reason, features_json, traffic_suggestion, origin, edited, verified,
                         needs_verification, is_turnaround, deleted, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'ai', 0, 0, ?, ?, 0, ?)""",
                    (video["id"], job_id, c["point_code"], c["direction"], c["start"], c["end"], c["start"], c["end"],
                     c["point_code"], c["direction"], c["quality_score"], c["relevance_score"], c["stability_score"],
                     c["sharpness_score"], c["activity_score"], c["object_density"], c["confidence"],
                     c["recommended_duration"], c["reason"], json.dumps(c["features"]), c["traffic_suggestion"],
                     int(c["needs_verification"]), int(c["is_turnaround"]), db.now_iso()))
        db.update("analysis_jobs", job_id, {"status": "done", "result_json": result, "finished_at": db.now_iso()})
        st = db.get_settings()
        if st.get("generate_preview_proxy", True) and (video.get("codec") != "h264" or (video.get("height") or 0) > 1080):
            db.update("batch_items", item_id, {"stage": "Membuat proxy preview", "progress": 0.95})
            try:
                enc = "h264_nvenc" if hw.get("nvenc_available") else "libx264"
                p = video_service.make_proxy(video["path"], video_service.proxy_path_for(video["id"]),
                                             int(st.get("proxy_height", 480)), enc)
                db.update("source_videos", video["id"], {"proxy_path": p})
            except Exception as e:  # noqa: BLE001 - proxy opsional
                log.warning("Proxy gagal untuk video %s: %s", video["id"], e)
        stage = "Menunggu review operator"
        if result.get("warnings"):
            stage += f" ({len(result['warnings'])} peringatan)"
        db.update("batch_items", item_id, {"status": "review", "progress": 1.0, "stage": stage,
                                           "candidate_count": len(cands), "finished_at": db.now_iso()})
    except InterruptedError:
        db.update("batch_items", item_id, {"status": "cancelled", "stage": "Dibatalkan", "finished_at": db.now_iso()})
        if job_id:
            db.update("analysis_jobs", job_id, {"status": "cancelled", "finished_at": db.now_iso()})
    except Exception as e:  # noqa: BLE001 - isolasi kegagalan per video
        log.error("Video %s gagal: %s", video.get("filename"), e)
        log.debug(traceback.format_exc())
        db.update("batch_items", item_id, {"status": "failed", "error": str(e)[:800], "stage": "Gagal",
                                           "finished_at": db.now_iso()})
        if job_id:
            db.update("analysis_jobs", job_id, {"status": "failed", "error": str(e)[:800], "finished_at": db.now_iso()})
    finally:
        with _lock:
            _cancel_flags.pop(item_id, None)
            _active.discard(item_id)
        try:
            batch_service.refresh_batch_status(item["batch_id"])
        finally:
            db.close_thread_conn()


# ====================================================================== dispatcher
def _dispatch_once() -> int:
    started = 0
    hw = hardware_service.detect()
    global_limit = max(1, int(hw.get("max_concurrency") or 4))
    for b in db.query("SELECT * FROM batch_jobs WHERE status IN ('running','queued') ORDER BY id"):
        with _lock:
            active_total = len(_active)
        running_here = db.scalar("SELECT COUNT(*) FROM batch_items WHERE batch_id=? AND status IN "
                                 "('analyzing','analyzed','processing')", (b["id"],))
        slots = min(b["concurrency"] - running_here, global_limit - active_total)
        if slots <= 0:
            continue
        waiting = db.query("""SELECT i.id FROM batch_items i JOIN source_videos v ON v.id=i.video_id
                              WHERE i.batch_id=? AND i.status='waiting' ORDER BY v.order_index, v.id LIMIT ?""",
                           (b["id"], slots))
        if not waiting:
            batch_service.refresh_batch_status(b["id"])
            continue
        for w in waiting:
            db.update("batch_items", w["id"], {"status": "analyzing", "stage": "Dijadwalkan", "progress": 0.0})
            with _lock:
                _active.add(w["id"])
            _executor.submit(process_item, w["id"])
            started += 1
    return started


def _loop(interval: float) -> None:
    while not _stop.is_set():
        try:
            _dispatch_once()
        except Exception:  # noqa: BLE001
            log.exception("Dispatcher error")
        _stop.wait(interval)
    db.close_thread_conn()


def start(interval: float = 0.5) -> None:
    global _executor, _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="analysis")
    _thread = threading.Thread(target=_loop, args=(interval,), name="batch-dispatcher", daemon=True)
    _thread.start()
    log.info("Batch worker aktif")


def stop(wait: bool = True) -> None:
    global _thread, _executor
    _stop.set()
    if _thread:
        _thread.join(timeout=5)
    _thread = None
    if _executor:
        with _lock:
            for ev in _cancel_flags.values():
                ev.set()
        _executor.shutdown(wait=wait)
        _executor = None


def analyze_now(video_id: int) -> dict:
    """Analisis ulang satu video segera (dipakai endpoint /api/videos/{id}/analyze)."""
    item = db.query_one("SELECT * FROM batch_items WHERE video_id=? ORDER BY id DESC LIMIT 1", (video_id,))
    if not item:
        raise ValueError("Video tidak terdaftar pada batch.")
    if item["status"] in ("analyzing", "processing", "analyzed"):
        raise ValueError("Video sedang dianalisis.")
    db.update("batch_items", item["id"], {"status": "analyzing", "progress": 0, "stage": "Dijadwalkan", "error": None})
    with _lock:
        _active.add(item["id"])
    if _executor is None:
        threading.Thread(target=process_item, args=(item["id"],), daemon=True).start()
    else:
        _executor.submit(process_item, item["id"])
    return db.get("batch_items", item["id"])

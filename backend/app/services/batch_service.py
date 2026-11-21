"""Batch processing: pembuatan batch, video, kelompok lokasi, kontrol antrean, laporan."""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from ..core.config import (BATCH_STATUS_LABELS, CONCURRENCY_OPTIONS, DEFAULT_TRAFFIC, FINAL_DURATIONS,
                           ITEM_STATUS_LABELS, MAX_BATCH_VIDEOS, TRAFFIC_CONDITIONS, TRIP_MODES,
                           VIDEO_EXTENSIONS, paths)
from ..core.logging_setup import get_logger
from ..core.templates_config import detect_template, get_template, point_map, resolve_route
from ..database import db
from . import hardware_service, video_service
from .timeline_service import NotFound, ValidationError

log = get_logger("batch")


# ====================================================================== proyek
def create_project(name: str, template_code: str, description: str | None = None,
                   location_name: str | None = None) -> dict:
    if not name or not name.strip():
        raise ValidationError("Nama proyek wajib diisi.")
    if not get_template(template_code):
        raise ValidationError(f"Template '{template_code}' tidak dikenal.")
    pid = db.insert("projects", {"name": name.strip(), "template_code": template_code,
                                 "description": description, "location_name": location_name,
                                 "created_at": db.now_iso(), "updated_at": db.now_iso()})
    (paths.projects / f"project_{pid:03d}").mkdir(parents=True, exist_ok=True)
    return get_project(pid)


def get_project(pid: int) -> dict:
    p = db.get("projects", pid)
    if not p:
        raise NotFound("Proyek tidak ditemukan")
    p["batch_count"] = db.scalar("SELECT COUNT(*) FROM batch_jobs WHERE project_id=?", (pid,))
    p["video_count"] = db.scalar("SELECT COUNT(*) FROM source_videos WHERE project_id=?", (pid,))
    p["final_count"] = db.scalar("SELECT COUNT(*) FROM final_videos WHERE project_id=?", (pid,))
    p["export_count"] = db.scalar("""SELECT COUNT(*) FROM export_jobs e JOIN final_videos f ON f.id=e.final_video_id
                                     WHERE f.project_id=? AND e.kind='final' AND e.status='done'""", (pid,))
    t = get_template(p["template_code"])
    p["template_name"] = t["name"] if t else p["template_code"]
    return p


def list_projects() -> list[dict]:
    return [get_project(r["id"]) for r in db.query("SELECT id FROM projects ORDER BY id DESC")]


def update_project(pid: int, changes: dict) -> dict:
    get_project(pid)
    upd = {k: changes[k] for k in ("name", "description", "location_name") if k in changes}
    if "template_code" in changes:
        if not get_template(changes["template_code"]):
            raise ValidationError("Template tidak dikenal.")
        upd["template_code"] = changes["template_code"]
    if upd:
        upd["updated_at"] = db.now_iso()
        db.update("projects", pid, upd)
    return get_project(pid)


# ====================================================================== batch
def create_batch(project_id: int, name: str | None, final_duration: int, trip_mode: str,
                 concurrency: int | None = None, metadata_mode: str = "shared",
                 template_code: str | None = None, route: dict | None = None) -> dict:
    project = get_project(project_id)
    if final_duration not in FINAL_DURATIONS:
        raise ValidationError("Durasi tiap video hasil harus kelipatan 5 detik, antara 10 dan 60 detik.")
    if trip_mode not in TRIP_MODES:
        raise ValidationError("Mode perjalanan harus 'outbound' (pergi saja) atau 'round_trip' (pergi dan kembali).")
    if metadata_mode not in ("shared", "per_final"):
        raise ValidationError("Mode metadata harus 'shared' atau 'per_final'.")
    tcode = template_code or project["template_code"]
    tmpl = get_template(tcode)
    if not tmpl:
        raise ValidationError("Template tidak dikenal.")
    if route:
        resolve_route(tmpl, route)  # validasi
    conc = concurrency or db.get_settings().get("default_concurrency", 2)
    if conc not in CONCURRENCY_OPTIONS:
        raise ValidationError("Concurrency harus 1, 2, atau 4.")
    conc, _warn = hardware_service.clamp_concurrency(conc)
    n = db.scalar("SELECT COUNT(*) FROM batch_jobs WHERE project_id=?", (project_id,)) + 1
    bid = db.insert("batch_jobs", {
        "project_id": project_id, "name": (name or f"Batch {n}").strip(), "template_code": tcode,
        "final_duration": final_duration, "trip_mode": trip_mode, "concurrency": conc,
        "metadata_mode": metadata_mode, "route_json": route, "status": "draft",
        "created_at": db.now_iso()})
    create_group(bid, "Lokasi 1", project.get("location_name"))
    return get_batch(bid)


def _batch(bid: int) -> dict:
    b = db.get("batch_jobs", bid)
    if not b:
        raise NotFound("Batch tidak ditemukan")
    return b


def batch_stats(bid: int) -> dict:
    items = db.query("SELECT status, progress, started_at, finished_at FROM batch_items WHERE batch_id=?", (bid,))
    counts = {k: 0 for k in ITEM_STATUS_LABELS}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    total = len(items)
    terminal = {"review", "done", "failed", "cancelled"}
    prog = sum(1.0 if it["status"] in terminal else float(it["progress"] or 0) for it in items)
    durs = []
    for it in items:
        if it["status"] in ("review", "done") and it["started_at"] and it["finished_at"]:
            durs.append((datetime.fromisoformat(it["finished_at"]) - datetime.fromisoformat(it["started_at"])).total_seconds())
    b = db.get("batch_jobs", bid)
    remaining = counts["waiting"] + sum(1 - float(it["progress"] or 0) for it in items
                                        if it["status"] in ("analyzing", "processing", "analyzed"))
    eta = None
    if durs and remaining > 0:
        eta = round(sum(durs) / len(durs) * remaining / max(1, b["concurrency"]))
    return {
        "total": total,
        "completed": counts["review"] + counts["done"],
        "processing": counts["analyzing"] + counts["processing"] + counts["analyzed"],
        "waiting": counts["waiting"],
        "failed": counts["failed"],
        "cancelled": counts["cancelled"],
        "by_status": counts,
        "progress": round(prog / total, 4) if total else 0.0,
        "eta_seconds": eta,
    }


def get_batch(bid: int) -> dict:
    b = _batch(bid)
    p = db.get("projects", b["project_id"])
    t = get_template(b["template_code"])
    b["project_name"] = p["name"] if p else None
    b["template_name"] = t["name"] if t else b["template_code"]
    b["status_label"] = BATCH_STATUS_LABELS.get(b["status"], b["status"])
    b["route_resolved"] = resolve_route(t, b.get("route"))
    b["stats"] = batch_stats(bid)
    b["groups"] = list_groups(bid)
    b["group_count"] = len(b["groups"])
    b["max_videos"] = MAX_BATCH_VIDEOS
    return b


def list_batches(project_id: int | None = None) -> list[dict]:
    sql = "SELECT id FROM batch_jobs" + (" WHERE project_id=?" if project_id else "") + " ORDER BY id DESC"
    return [get_batch(r["id"]) for r in db.query(sql, (project_id,) if project_id else ())]


def update_batch(bid: int, changes: dict) -> dict:
    b = _batch(bid)
    upd = {}
    if "name" in changes and changes["name"]:
        upd["name"] = changes["name"]
    if "final_duration" in changes:
        if int(changes["final_duration"]) not in FINAL_DURATIONS:
            raise ValidationError("Durasi tiap video hasil harus kelipatan 5 detik, antara 10 dan 60 detik.")
        upd["final_duration"] = int(changes["final_duration"])
    if "trip_mode" in changes:
        if changes["trip_mode"] not in TRIP_MODES:
            raise ValidationError("Mode perjalanan tidak valid.")
        if b["status"] in ("running", "queued"):
            raise ValidationError("Mode perjalanan tidak dapat diubah saat batch berjalan.")
        upd["trip_mode"] = changes["trip_mode"]
    if "concurrency" in changes:
        c = int(changes["concurrency"])
        if c not in CONCURRENCY_OPTIONS:
            raise ValidationError("Concurrency harus 1, 2, atau 4.")
        upd["concurrency"], _ = hardware_service.clamp_concurrency(c)
    if "metadata_mode" in changes:
        if changes["metadata_mode"] not in ("shared", "per_final"):
            raise ValidationError("Mode metadata tidak valid.")
        upd["metadata_mode"] = changes["metadata_mode"]
    if "route" in changes:
        if changes["route"]:
            resolve_route(get_template(b["template_code"]), changes["route"])
        upd["route_json"] = changes["route"] or None
    if upd:
        db.update("batch_jobs", bid, upd)
    return get_batch(bid)


# ====================================================================== video
def _video_count(bid: int) -> int:
    return db.scalar("SELECT COUNT(*) FROM source_videos WHERE batch_id=?", (bid,))


def _check_capacity(bid: int, adding: int) -> None:
    b = _batch(bid)
    if b["status"] in ("running", "queued"):
        raise ValidationError("Video tidak dapat ditambahkan saat batch berjalan. Jeda atau tunggu selesai.")
    current = _video_count(bid)
    if current + adding > MAX_BATCH_VIDEOS:
        raise ValidationError(f"Maksimal {MAX_BATCH_VIDEOS} video per batch. Saat ini {current} video, "
                              f"menambah {adding} akan menjadi {current + adding}. Pemrosesan tidak dimulai.")


def _safe_name(name: str) -> str:
    name = os.path.basename(name or "video.mp4")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "video.mp4"
    return name[:150]


# ---------------------------------------------------------------- informasi video
INFO_FIELDS = ("location_name", "traffic_condition", "event_date", "event_time")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$")


def info_from_download(info: dict[str, Any] | None) -> dict[str, Any]:
    """Petakan hasil parsing Drone Video Downloader ke kolom informasi video Trimmer."""
    info = info or {}
    out: dict[str, Any] = {}
    loc = (info.get("location") or "").strip()
    if loc:
        out["location_name"] = loc
    traffic = (info.get("traffic") or "").strip()
    if traffic:
        out["traffic_condition"] = traffic
    d = (info.get("date") or "").strip()
    if _DATE_RE.match(d):
        out["event_date"] = d
    t = _TIME_RE.match((info.get("time") or "").strip())
    if t:
        out["event_time"] = f"{int(t.group(1)):02d}:{t.group(2)}"
    return out


def _auto_info(path: str, filename: str) -> tuple[dict, dict | None, str | None]:
    """Cari informasi video: manifest downloader di folder file, lalu pola nama file standar."""
    from ..downloader.manifest import guess_from_filename, read_manifest
    try:
        man = read_manifest(Path(path).parent)
    except Exception:  # noqa: BLE001
        man = {}
    raw = man.get(Path(path).name) or man.get(filename)
    if raw:
        return info_from_download(raw), raw, "downloader"
    guess = guess_from_filename(filename)
    if guess:
        return info_from_download(guess), guess, "filename"
    return {}, None, None


def _register_video(bid: int, filename: str, path: str, uploaded: bool, info: dict | None = None,
                    origin: str | None = None) -> dict:
    """Daftarkan video. ``info`` = hasil parsing downloader (bila ada); bila kosong dicari otomatis."""
    b = _batch(bid)
    group = db.query_one("SELECT id FROM location_groups WHERE batch_id=? ORDER BY id LIMIT 1", (bid,))
    order = _video_count(bid)
    meta, err = {}, None
    try:
        meta = video_service.probe(path)
    except Exception as e:  # noqa: BLE001 - file rusak tetap didaftarkan, akan gagal saat analisis
        err = str(e)
    if info:
        fields, raw = info_from_download(info), info
        src = "filename" if info.get("guessed") else (origin or "downloader")
    else:
        fields, raw, src = _auto_info(path, filename)
    # jenis lokasi (template) per video ditebak dari nama lokasi; bila tidak dikenali ikut template batch
    fields["template_code"] = detect_template(fields.get("location_name")) or b["template_code"]
    vid = db.insert("source_videos", {
        "project_id": b["project_id"], "batch_id": bid, "location_group_id": group["id"] if group else None,
        "filename": filename, "path": path, "is_uploaded": int(uploaded),
        **fields, "source_meta_json": ({**raw, "_source": src} if raw else None),
        "source_origin": "downloader" if src == "downloader" else ("upload" if uploaded else "path"),
        "size_bytes": meta.get("size_bytes") or (os.path.getsize(path) if os.path.exists(path) else None),
        "duration": meta.get("duration"), "width": meta.get("width"), "height": meta.get("height"),
        "fps": meta.get("fps"), "codec": meta.get("codec"), "audio_codec": meta.get("audio_codec"),
        "creation_time": meta.get("creation_time"), "metadata_json": meta or None, "probe_error": err,
        "order_index": order, "uploaded_at": db.now_iso()})
    db.insert("batch_items", {"batch_id": bid, "video_id": vid, "status": "waiting", "progress": 0})
    return get_video(vid)


def add_uploaded_videos(bid: int, files: list[tuple[str, BinaryIO]]) -> list[dict]:
    if not files:
        raise ValidationError("Tidak ada file yang dipilih.")
    _check_capacity(bid, len(files))
    bad = [f for f, _ in files if Path(f).suffix.lower() not in VIDEO_EXTENSIONS]
    if bad:
        raise ValidationError(f"Format file tidak didukung: {', '.join(bad)}")
    dest_dir = paths.uploads / f"batch_{bid:04d}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for fname, fobj in files:
        safe = _safe_name(fname)
        dst = dest_dir / safe
        i = 1
        while dst.exists():
            dst = dest_dir / f"{Path(safe).stem}_{i:02d}{Path(safe).suffix}"
            i += 1
        with open(dst, "wb") as fh:
            shutil.copyfileobj(fobj, fh, length=8 * 1024 * 1024)
        out.append(_register_video(bid, fname, str(dst), uploaded=True))
    return out


def add_local_paths(bid: int, local_paths: list[str], infos: list[dict | None] | None = None) -> list[dict]:
    """Daftarkan video dari path lokal tanpa menyalin (file sumber hanya dibaca).

    ``infos`` (opsional, sejajar dengan ``local_paths``) berisi hasil parsing downloader
    sehingga lokasi, tanggal, waktu, dan kondisi lalin terisi otomatis.
    """
    if not local_paths:
        raise ValidationError("Daftar path kosong.")
    _check_capacity(bid, len(local_paths))
    missing = [p for p in local_paths if not os.path.isfile(p)]
    if missing:
        raise ValidationError(f"File tidak ditemukan: {', '.join(missing)}")
    bad = [p for p in local_paths if Path(p).suffix.lower() not in VIDEO_EXTENSIONS]
    if bad:
        raise ValidationError(f"Format file tidak didukung: {', '.join(bad)}")
    infos = infos or [None] * len(local_paths)
    return [_register_video(bid, os.path.basename(p), os.path.abspath(p), uploaded=False, info=i)
            for p, i in zip(local_paths, infos)]


def get_video(vid: int) -> dict:
    v = db.get("source_videos", vid)
    if not v:
        raise NotFound("Video tidak ditemukan")
    item = db.query_one("SELECT * FROM batch_items WHERE video_id=? ORDER BY id DESC LIMIT 1", (vid,))
    v["item"] = item
    if item:
        item["status_label"] = ITEM_STATUS_LABELS.get(item["status"], item["status"])
    v["analysis"] = db.query_one("SELECT id, status, device, detector, is_heuristic, result_json, error, "
                                 "started_at, finished_at FROM analysis_jobs WHERE video_id=? ORDER BY id DESC LIMIT 1",
                                 (vid,))
    v["candidate_count"] = db.scalar("SELECT COUNT(*) FROM candidate_segments WHERE video_id=? AND deleted=0", (vid,))
    v["has_proxy"] = bool(v.get("proxy_path") and os.path.exists(v["proxy_path"]))
    return v


def list_items(bid: int) -> list[dict]:
    _batch(bid)
    rows = db.query("""SELECT i.*, v.filename, v.size_bytes, v.duration, v.width, v.height, v.fps, v.codec,
                              v.order_index, v.location_group_id, v.point_mapping_json, v.direction_override,
                              v.probe_error, v.creation_time, v.is_uploaded, v.path,
                              v.location_name, v.traffic_condition, v.event_date, v.event_time,
                              v.source_origin, v.source_meta_json, v.template_code,
                              (SELECT f.id FROM final_videos f WHERE f.source_video_id = v.id
                               ORDER BY f.id DESC LIMIT 1) AS final_video_id
                       FROM batch_items i JOIN source_videos v ON v.id = i.video_id
                       WHERE i.batch_id=? ORDER BY v.order_index, v.id""", (bid,))
    for r in rows:
        r["status_label"] = ITEM_STATUS_LABELS.get(r["status"], r["status"])
    return rows


def remove_video(bid: int, vid: int) -> None:
    b = _batch(bid)
    v = db.get("source_videos", vid)
    if not v or v["batch_id"] != bid:
        raise NotFound("Video tidak ada di batch ini")
    item = db.query_one("SELECT status FROM batch_items WHERE video_id=?", (vid,))
    if item and item["status"] in ("analyzing", "processing"):
        raise ValidationError("Video sedang diproses dan tidak dapat dihapus.")
    if b["status"] in ("running", "queued"):
        raise ValidationError("Jeda batch terlebih dahulu sebelum menghapus video.")
    db.execute("DELETE FROM source_videos WHERE id=?", (vid,))
    # Hanya salinan unggahan milik aplikasi yang dihapus. File sumber asli (path lokal) tidak disentuh.
    if v["is_uploaded"] and str(Path(v["path"]).resolve()).startswith(str(paths.uploads.resolve())):
        try:
            os.remove(v["path"])
        except OSError:
            pass
    rows = db.query("SELECT id FROM source_videos WHERE batch_id=? ORDER BY order_index, id", (bid,))
    for i, r in enumerate(rows):
        db.update("source_videos", r["id"], {"order_index": i})


def update_video(vid: int, changes: dict) -> dict:
    v = db.get("source_videos", vid)
    if not v:
        raise NotFound("Video tidak ditemukan")
    upd = {}
    if "location_group_id" in changes:
        g = db.get("location_groups", changes["location_group_id"])
        if not g or g["batch_id"] != v["batch_id"]:
            raise ValidationError("Kelompok lokasi tidak valid untuk batch ini.")
        upd["location_group_id"] = g["id"]
    if "point_mapping" in changes:
        pm = changes["point_mapping"]
        if pm:
            b = _batch(v["batch_id"])
            valid = point_map(get_template(v.get("template_code") or b["template_code"]))
            bad = [p for p in pm if str(p) not in valid]
            if bad:
                raise ValidationError(f"Titik tidak dikenal: {bad}")
            pm = [str(p) for p in pm]
        upd["point_mapping_json"] = pm or None
    if "direction_override" in changes:
        d = changes["direction_override"]
        if d not in (None, "", "outbound", "return"):
            raise ValidationError("Arah harus outbound/return atau kosong.")
        upd["direction_override"] = d or None
    if "creation_time" in changes:
        upd["creation_time"] = changes["creation_time"] or None
    info = {k: (changes[k] or None) for k in INFO_FIELDS if k in changes}
    if info.get("event_date") and not _DATE_RE.match(info["event_date"]):
        raise ValidationError("Format tanggal harus YYYY-MM-DD.")
    if info.get("event_time"):
        m = _TIME_RE.match(info["event_time"])
        if not m:
            raise ValidationError("Format waktu harus HH:MM (24 jam).")
        info["event_time"] = f"{int(m.group(1)):02d}:{m.group(2)}"
    upd.update(info)
    template_changed = False
    if changes.get("template_code") and changes["template_code"] != v.get("template_code"):
        if not get_template(changes["template_code"]):
            raise ValidationError("Jenis lokasi (template) tidak dikenal.")
        item = db.query_one("SELECT status FROM batch_items WHERE video_id=?", (vid,))
        if item and item["status"] in ("analyzing", "processing", "analyzed"):
            raise ValidationError("Jenis lokasi tidak dapat diubah saat video sedang dianalisis.")
        upd["template_code"] = changes["template_code"]
        upd["point_mapping_json"] = None  # nomor titik berbeda antar template
        template_changed = True
    if upd:
        db.update("source_videos", vid, upd)
    if template_changed:
        # kandidat AI lama memakai titik template lama -> video perlu dianalisis ulang
        db.execute("DELETE FROM candidate_segments WHERE video_id=? AND origin='ai'", (vid,))
        db.execute("DELETE FROM candidate_segments WHERE video_id=? AND origin='operator'", (vid,))
        db.execute("UPDATE batch_items SET status='waiting', progress=0, stage='Jenis lokasi diubah - perlu analisis ulang', "
                   "candidate_count=0, error=NULL WHERE video_id=? AND status NOT IN ('analyzing','processing')", (vid,))
        for f in db.query("SELECT id FROM final_videos WHERE source_video_id=?", (vid,)):
            db.execute("DELETE FROM final_video_segments WHERE final_video_id=?", (f["id"],))
            tm = get_template(upd["template_code"])
            db.update("final_videos", f["id"], {"template_code": upd["template_code"],
                                                "location_type": tm["location_type"], "updated_at": db.now_iso()})
    if info:
        # informasi video ikut memperbarui video hasil (1 video sumber = 1 video hasil)
        from . import timeline_service
        for f in db.query("SELECT id FROM final_videos WHERE source_video_id=?", (vid,)):
            timeline_service.update_final(f["id"], info)
    return get_video(vid)


def reorder_videos(bid: int, ordered_ids: list[int]) -> list[dict]:
    current = sorted(r["id"] for r in db.query("SELECT id FROM source_videos WHERE batch_id=?", (bid,)))
    if current != sorted(ordered_ids):
        raise ValidationError("Urutan harus memuat seluruh video batch tepat satu kali.")
    for i, vid in enumerate(ordered_ids):
        db.update("source_videos", vid, {"order_index": i})
    return list_items(bid)


# ====================================================================== kelompok lokasi
def create_group(bid: int, name: str, location_name: str | None = None, traffic: str | None = None,
                 event_date: str | None = None, event_time: str | None = None) -> dict:
    b = _batch(bid)
    t = get_template(b["template_code"])
    gid = db.insert("location_groups", {
        "batch_id": bid, "project_id": b["project_id"], "name": name or "Lokasi",
        "location_name": location_name, "location_type": t["location_type"],
        "traffic_condition": traffic or DEFAULT_TRAFFIC, "event_date": event_date,
        "event_time": event_time, "created_at": db.now_iso()})
    return get_group(gid)


def get_group(gid: int) -> dict:
    g = db.get("location_groups", gid)
    if not g:
        raise NotFound("Kelompok lokasi tidak ditemukan")
    g["videos"] = db.query("SELECT id, filename, duration, order_index FROM source_videos "
                           "WHERE location_group_id=? ORDER BY order_index, id", (gid,))
    g["video_count"] = len(g["videos"])
    finals = db.query("SELECT id, status, target_duration, group_ids_json, cross_location FROM final_videos "
                      "WHERE project_id=?", (g["project_id"],))
    g["final_videos"] = [f for f in finals if gid in (f.get("group_ids") or [])]
    return g


def list_groups(bid: int) -> list[dict]:
    return [get_group(r["id"]) for r in db.query("SELECT id FROM location_groups WHERE batch_id=? ORDER BY id", (bid,))]


def update_group(gid: int, changes: dict) -> dict:
    get_group(gid)
    upd = {k: changes[k] for k in ("name", "location_name", "traffic_condition", "event_date", "event_time")
           if k in changes}
    if upd.get("traffic_condition") and upd["traffic_condition"] not in TRAFFIC_CONDITIONS:
        raise ValidationError("Kondisi lalu lintas tidak dikenal.")
    if upd:
        db.update("location_groups", gid, upd)
    return get_group(gid)


def delete_group(gid: int) -> None:
    g = get_group(gid)
    others = db.query("SELECT id FROM location_groups WHERE batch_id=? AND id<>? ORDER BY id", (g["batch_id"], gid))
    if not others:
        raise ValidationError("Batch harus memiliki minimal satu kelompok lokasi.")
    db.execute("UPDATE source_videos SET location_group_id=? WHERE location_group_id=?", (others[0]["id"], gid))
    db.execute("DELETE FROM location_groups WHERE id=?", (gid,))


# ====================================================================== kontrol antrean
def start_batch(bid: int) -> dict:
    b = _batch(bid)
    n = _video_count(bid)
    if n == 0:
        raise ValidationError("Batch belum memiliki video.")
    if n > MAX_BATCH_VIDEOS:
        raise ValidationError(f"Batch berisi {n} video; maksimal {MAX_BATCH_VIDEOS}. Pemrosesan tidak dimulai.")
    if b["status"] in ("running", "queued"):
        return get_batch(bid)
    # video yang gagal/dibatalkan diantrekan ulang saat batch dimulai lagi
    db.execute("UPDATE batch_items SET status='waiting', progress=0, error=NULL, stage=NULL "
               "WHERE batch_id=? AND status IN ('failed','cancelled')", (bid,))
    db.update("batch_jobs", bid, {"status": "running", "started_at": b["started_at"] or db.now_iso(),
                                  "finished_at": None, "error": None, "recovered": 0})
    log.info("Batch %s dimulai", bid)
    return get_batch(bid)


def pause_batch(bid: int) -> dict:
    b = _batch(bid)
    if b["status"] not in ("running", "queued"):
        raise ValidationError("Hanya batch yang berjalan yang dapat dijeda.")
    db.update("batch_jobs", bid, {"status": "paused"})
    return get_batch(bid)


def resume_batch(bid: int) -> dict:
    b = _batch(bid)
    if b["status"] != "paused":
        raise ValidationError("Batch tidak sedang dijeda.")
    db.update("batch_jobs", bid, {"status": "running", "recovered": 0})
    return get_batch(bid)


def cancel_batch(bid: int) -> dict:
    from ..workers import batch_worker
    _batch(bid)
    db.update("batch_jobs", bid, {"status": "cancelled", "finished_at": db.now_iso()})
    db.execute("UPDATE batch_items SET status='cancelled', finished_at=? WHERE batch_id=? AND status='waiting'",
               (db.now_iso(), bid))
    for it in db.query("SELECT id FROM batch_items WHERE batch_id=? AND status IN ('analyzing','processing','analyzed')",
                       (bid,)):
        batch_worker.request_cancel(it["id"])
    return get_batch(bid)


def refresh_batch_status(bid: int) -> None:
    b = db.get("batch_jobs", bid)
    if not b or b["status"] in ("paused", "cancelled", "draft"):
        return
    st = batch_stats(bid)
    if st["waiting"] or st["processing"]:
        return
    by = st["by_status"]
    if st["total"] and by["review"] == 0 and by["done"] > 0:
        status = "completed"  # semua video selesai (sisanya gagal/dibatalkan)
    elif by["review"] or by["done"]:
        status = "review"
    elif by["failed"] == st["total"]:
        status = "failed"
    else:
        status = "review"
    if status != b["status"]:
        db.update("batch_jobs", bid, {"status": status, "finished_at": db.now_iso()})


def mark_reviewed(bid: int) -> dict:
    """Tandai seluruh video berstatus 'Menunggu review' sebagai 'Selesai'."""
    db.execute("UPDATE batch_items SET status='done', finished_at=? WHERE batch_id=? AND status='review'",
               (db.now_iso(), bid))
    refresh_batch_status(bid)
    return get_batch(bid)


# ====================================================================== pemulihan
def recover_on_startup() -> dict:
    """Pulihkan status setelah aplikasi ditutup/crash."""
    stuck = db.query("SELECT id, video_id FROM batch_items WHERE status IN ('analyzing','analyzed','processing')")
    for it in stuck:
        # hapus kandidat AI parsial dari analisis yang terputus
        db.execute("""DELETE FROM candidate_segments WHERE video_id=? AND origin='ai' AND analysis_job_id IN
                      (SELECT id FROM analysis_jobs WHERE video_id=? AND status<>'done')""",
                   (it["video_id"], it["video_id"]))
        db.execute("UPDATE analysis_jobs SET status='interrupted', finished_at=? WHERE video_id=? AND status='running'",
                   (db.now_iso(), it["video_id"]))
        db.execute("UPDATE batch_items SET status='waiting', progress=0, stage='Dipulihkan setelah aplikasi dimulai ulang', "
                   "attempts=attempts+1 WHERE id=?", (it["id"],))
    batches = db.query("SELECT id FROM batch_jobs WHERE status IN ('running','queued')")
    for b in batches:
        db.update("batch_jobs", b["id"], {"status": "paused", "recovered": 1})
    exports = db.query("SELECT id, final_video_id FROM export_jobs WHERE status IN ('queued','running')")
    for e in exports:
        db.update("export_jobs", e["id"], {"status": "failed", "error": "Ekspor terputus karena aplikasi ditutup. Ulangi ekspor.",
                                           "finished_at": db.now_iso()})
        db.execute("UPDATE final_videos SET status='draft' WHERE id=? AND status='exporting'", (e["final_video_id"],))
    if stuck or batches or exports:
        log.info("Pemulihan: %d item, %d batch, %d ekspor", len(stuck), len(batches), len(exports))
    return {"items_requeued": len(stuck), "batches_paused": len(batches), "exports_failed": len(exports)}


# ====================================================================== laporan
def batch_report(bid: int) -> dict:
    b = get_batch(bid)
    items = list_items(bid)
    finals = db.query("SELECT * FROM final_videos WHERE batch_id=? ORDER BY id", (bid,))
    exports_ok, exports_failed = [], []
    for f in finals:
        for e in db.query("SELECT * FROM export_jobs WHERE final_video_id=? AND kind IN ('final','individual')", (f["id"],)):
            rec = {"export_id": e["id"], "final_video_id": f["id"], "kind": e["kind"],
                   "file": e["output_path"], "error": e["error"], "duration": e["duration"]}
            (exports_ok if e["status"] == "done" else exports_failed if e["status"] == "failed" else []).append(rec)
    return {
        "batch": {k: b[k] for k in ("id", "name", "project_name", "template_name", "final_duration", "trip_mode",
                                     "concurrency", "status", "status_label", "created_at", "started_at", "finished_at")},
        "stats": b["stats"],
        "groups": [{"id": g["id"], "name": g["name"], "location_name": g["location_name"],
                    "video_count": g["video_count"]} for g in b["groups"]],
        "videos": [{"no": i + 1, "filename": it["filename"], "duration": it["duration"], "status": it["status_label"],
                    "candidates": it["candidate_count"], "error": it["error"] or it["probe_error"]}
                   for i, it in enumerate(items)],
        "final_videos": [{"id": f["id"], "status": f["status"], "location_name": f["location_name"],
                          "traffic_condition": f["traffic_condition"], "target_duration": f["target_duration"]}
                         for f in finals],
        "exports_succeeded": exports_ok,
        "exports_failed": exports_failed,
        "generated_at": db.now_iso(),
    }


def delete_batch_if_empty(bid: int) -> None:
    """Hapus batch draf tanpa video (dipakai bila impor gagal saat membuat batch)."""
    b = db.get("batch_jobs", bid)
    if b and b["status"] == "draft" and not _video_count(bid):
        db.execute("DELETE FROM batch_jobs WHERE id=?", (bid,))

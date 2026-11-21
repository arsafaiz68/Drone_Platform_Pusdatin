"""Video final, timeline editing, koreksi kandidat, dan pencatatan feedback operator."""
from __future__ import annotations

from ..core.config import DEFAULT_TRAFFIC, FINAL_DURATIONS, TRAFFIC_CONDITIONS
from ..core.templates_config import get_template, point_map, resolve_route
from ..database import db
from . import naming_service, selection_service

EPS = 1e-6


class NotFound(Exception):
    pass


class ValidationError(Exception):
    pass


# ====================================================================== util
def _video(video_id: int) -> dict:
    v = db.get("source_videos", video_id)
    if not v:
        raise NotFound(f"Video {video_id} tidak ditemukan")
    return v


def _validate_range(video: dict, start: float, end: float) -> tuple[float, float]:
    dur = float(video.get("duration") or 0)
    if start is None or end is None:
        raise ValidationError("Timestamp awal dan akhir wajib diisi.")
    start, end = float(start), float(end)
    if start < 0 or end <= start:
        raise ValidationError("Timestamp tidak valid: akhir harus lebih besar dari awal dan awal ≥ 0.")
    if dur and end > dur + 0.05:
        raise ValidationError(f"Timestamp akhir melebihi durasi video ({dur:.2f} dtk).")
    if end - start < 0.5:
        raise ValidationError("Durasi segmen minimal 0,5 detik.")
    return round(start, 3), round(min(end, dur) if dur else end, 3)


def _template_for_video(video: dict) -> dict:
    """Template per video (jenis lokasi video itu sendiri), cadangan: template batch/proyek."""
    if video.get("template_code") and get_template(video["template_code"]):
        return get_template(video["template_code"])
    if video.get("batch_id"):
        b = db.get("batch_jobs", video["batch_id"])
        return get_template(b["template_code"])
    p = db.get("projects", video["project_id"])
    return get_template(p["template_code"])


def _check_point(template: dict, code: str | None, direction: str | None):
    if code is not None and code not in point_map(template):
        raise ValidationError(f"Titik '{code}' tidak ada pada template {template['name']}.")
    if direction is not None and direction not in ("outbound", "return"):
        raise ValidationError("Arah perjalanan harus 'outbound' (pergi) atau 'return' (kembali).")


def record_feedback(action: str, candidate: dict | None = None, video: dict | None = None, **extra):
    """Simpan koreksi operator sebagai data pelatihan (dataset berlabel)."""
    c = candidate or {}
    v = video or (db.get("source_videos", c["video_id"]) if c.get("video_id") else {}) or {}
    tmpl = None
    if v:
        tmpl = _template_for_video(v)["code"]
    feats = (c.get("features") or {}).copy()
    feats.pop("hist", None)
    db.insert("operator_feedback", {
        "project_id": v.get("project_id"),
        "video_id": v.get("id"),
        "candidate_id": c.get("id"),
        "template_code": tmpl,
        "point_code": extra.get("point_code", c.get("point_code")),
        "direction": extra.get("direction", c.get("direction")),
        "t_start": extra.get("start", c.get("t_start")),
        "t_end": extra.get("end", c.get("t_end")),
        "is_turnaround": int(bool(extra.get("is_turnaround", c.get("is_turnaround")))),
        "quality_label": extra.get("quality_label"),
        "traffic_label": extra.get("traffic_label", c.get("traffic_suggestion")),
        "visual_features_json": feats,
        "action": action,
        "created_at": db.now_iso(),
    })


def _cand_public(c: dict) -> dict:
    c = dict(c)
    c["start"], c["end"] = c.pop("t_start"), c.pop("t_end")
    c["duration"] = round(c["end"] - c["start"], 3)
    if c.get("features"):
        c["features"] = {k: v for k, v in c["features"].items() if k != "hist"}
    return c


# ====================================================================== kandidat
def list_candidates(video_id: int, include_deleted: bool = False) -> list[dict]:
    rows = db.query("SELECT * FROM candidate_segments WHERE video_id = ? "
                    + ("" if include_deleted else "AND deleted = 0 ")
                    + "ORDER BY direction DESC, t_start", (video_id,))
    return [_cand_public(r) for r in rows]


def get_candidate(cid: int) -> dict:
    c = db.get("candidate_segments", cid)
    if not c:
        raise NotFound(f"Kandidat {cid} tidak ditemukan")
    return c


def add_candidate(video_id: int, start: float, end: float, point_code: str, direction: str,
                  traffic: str | None = None) -> dict:
    v = _video(video_id)
    tmpl = _template_for_video(v)
    _check_point(tmpl, point_code, direction)
    start, end = _validate_range(v, start, end)
    cid = db.insert("candidate_segments", {
        "video_id": video_id, "point_code": point_code, "direction": direction,
        "t_start": start, "t_end": end, "ai_start": None, "ai_end": None,
        "quality_score": None, "relevance_score": 0.6, "confidence": 1.0,
        "recommended_duration": round(end - start, 2), "reason": "Ditambahkan manual oleh operator",
        "origin": "operator", "edited": 1, "verified": 1, "needs_verification": 0,
        "traffic_suggestion": traffic, "created_at": db.now_iso(),
    })
    c = get_candidate(cid)
    record_feedback("add_candidate", c, v)
    _refresh_count(video_id)
    return _cand_public(c)


def update_candidate(cid: int, changes: dict) -> dict:
    c = get_candidate(cid)
    v = _video(c["video_id"])
    tmpl = _template_for_video(v)
    upd = {}
    if "point_code" in changes or "direction" in changes:
        _check_point(tmpl, changes.get("point_code", c["point_code"]), changes.get("direction", c["direction"]))
    if "start" in changes or "end" in changes:
        s, e = _validate_range(v, changes.get("start", c["t_start"]), changes.get("end", c["t_end"]))
        upd["t_start"], upd["t_end"] = s, e
    for k in ("point_code", "direction", "traffic_suggestion", "is_turnaround"):
        if k in changes and changes[k] is not None:
            upd[k] = changes[k]
    if "traffic_suggestion" in upd and upd["traffic_suggestion"] not in TRAFFIC_CONDITIONS:
        raise ValidationError("Kondisi lalu lintas tidak dikenal.")
    if "verified" in changes:
        upd["verified"] = int(bool(changes["verified"]))
        if upd["verified"]:
            upd["needs_verification"] = 0
    if upd:
        upd["edited"] = 1 if any(k in upd for k in ("t_start", "t_end", "point_code", "direction")) else c["edited"]
        upd["updated_at"] = db.now_iso()
        db.update("candidate_segments", cid, upd)
        db.insert("segment_edits", {"candidate_id": cid, "action": "update_candidate",
                                    "old_value_json": {k: c.get(k) for k in upd},
                                    "new_value_json": upd, "created_at": db.now_iso()})
        new = get_candidate(cid)
        record_feedback("verify" if set(upd) <= {"verified", "needs_verification", "updated_at", "edited"}
                        else "correct_candidate", new, v,
                        quality_label=changes.get("quality_label"))
        if "verified" in upd:
            sync_review_status(c["video_id"])
    return _cand_public(get_candidate(cid))


def reset_candidate(cid: int) -> dict:
    c = get_candidate(cid)
    if c["ai_start"] is None:
        raise ValidationError("Kandidat ini ditambahkan operator; tidak ada timestamp AI.")
    db.update("candidate_segments", cid, {
        "t_start": c["ai_start"], "t_end": c["ai_end"],
        "point_code": c["ai_point_code"] or c["point_code"],
        "direction": c["ai_direction"] or c["direction"], "edited": 0, "updated_at": db.now_iso()})
    db.insert("segment_edits", {"candidate_id": cid, "action": "reset_candidate", "created_at": db.now_iso()})
    return _cand_public(get_candidate(cid))


def delete_candidate(cid: int) -> dict:
    """Tolak kandidat. Potongan yang memakai kandidat ini ikut dikeluarkan dari video hasil,
    sehingga durasi video hasil berkurang (tidak diisi ulang otomatis)."""
    c = get_candidate(cid)
    db.update("candidate_segments", cid, {"deleted": 1, "updated_at": db.now_iso()})
    record_feedback("reject_candidate", c, quality_label="ditolak")
    affected = []
    for s in db.query("SELECT * FROM final_video_segments WHERE candidate_id=?", (cid,)):
        db.execute("DELETE FROM final_video_segments WHERE id=?", (s["id"],))
        _renumber(s["final_video_id"])
        _log(s["final_video_id"], None, "delete_segment",
             {"segment_id": s["id"], "start": s["t_start"], "end": s["t_end"], "reason": "kandidat dihapus"}, None, cid)
        affected.append(s["final_video_id"])
    _refresh_count(c["video_id"])
    return {"deleted": True, "removed_from_finals": [
        {"final_video_id": f, "duration": get_final(f)["duration_status"]} for f in dict.fromkeys(affected)]}


def verify_all(video_id: int) -> dict:
    """Terima (verifikasi) semua kandidat video sekaligus -> status "Selesai direview"."""
    _video(video_id)
    rows = db.query("SELECT id FROM candidate_segments WHERE video_id=? AND deleted=0 AND verified=0", (video_id,))
    for r in rows:
        db.update("candidate_segments", r["id"], {"verified": 1, "needs_verification": 0, "updated_at": db.now_iso()})
        record_feedback("verify", get_candidate(r["id"]))
    sync_review_status(video_id)
    if not db.scalar("SELECT COUNT(*) FROM candidate_segments WHERE video_id=? AND deleted=0", (video_id,)):
        set_review_status(video_id, True)  # tanpa kandidat: tetap tandai selesai direview
    return {"verified": len(rows)}


def _refresh_count(video_id: int):
    n = db.scalar("SELECT COUNT(*) FROM candidate_segments WHERE video_id=? AND deleted=0", (video_id,))
    db.execute("UPDATE batch_items SET candidate_count=? WHERE video_id=?", (n, video_id))
    sync_review_status(video_id)


def _has_export(video_id: int) -> bool:
    return bool(db.scalar("""SELECT COUNT(*) FROM export_jobs e JOIN final_videos f ON f.id = e.final_video_id
                             WHERE f.source_video_id=? AND e.kind='final' AND e.status='done'""", (video_id,)))


def set_review_status(video_id: int, reviewed: bool) -> dict | None:
    """Ubah status item video: 'review' (Menunggu review) <-> 'done' (Selesai direview)."""
    item = db.query_one("SELECT * FROM batch_items WHERE video_id=? ORDER BY id DESC LIMIT 1", (video_id,))
    if not item or item["status"] not in ("review", "done"):
        return item
    if reviewed and item["status"] == "review":
        db.update("batch_items", item["id"], {"status": "done", "finished_at": db.now_iso()})
    elif not reviewed and item["status"] == "done" and not _has_export(video_id):
        db.update("batch_items", item["id"], {"status": "review"})
    from . import batch_service
    batch_service.refresh_batch_status(item["batch_id"])
    return db.get("batch_items", item["id"])


def sync_review_status(video_id: int) -> None:
    """Video dianggap selesai direview bila seluruh kandidatnya sudah diverifikasi operator."""
    total = db.scalar("SELECT COUNT(*) FROM candidate_segments WHERE video_id=? AND deleted=0", (video_id,))
    unverified = db.scalar("SELECT COUNT(*) FROM candidate_segments WHERE video_id=? AND deleted=0 AND verified=0",
                           (video_id,))
    if total:
        set_review_status(video_id, unverified == 0)


# ====================================================================== video final
def _group_videos(group_ids: list[int]) -> list[dict]:
    if not group_ids:
        return []
    ph = ",".join("?" for _ in group_ids)
    return db.query(f"SELECT * FROM source_videos WHERE location_group_id IN ({ph}) ORDER BY order_index, id",
                    group_ids)


def final_source_videos(f: dict) -> list[dict]:
    """Video sumber yang boleh dipakai video hasil: satu video (skema per video) atau satu kelompok."""
    if f.get("source_video_id"):
        v = db.get("source_videos", f["source_video_id"])
        return [v] if v else []
    return _group_videos(f.get("group_ids") or [])


def gather_candidates_for_final(f: dict) -> list[dict]:
    return _candidates_of(final_source_videos(f))


def gather_candidates(group_ids: list[int]) -> list[dict]:
    return _candidates_of(_group_videos(group_ids))


def _candidates_of(vids: list[dict]) -> list[dict]:
    if not vids:
        return []
    ph = ",".join("?" for _ in vids)
    rows = db.query(f"SELECT * FROM candidate_segments WHERE deleted=0 AND video_id IN ({ph})",
                    [v["id"] for v in vids])
    out = []
    for r in rows:
        r = dict(r)
        r["start"], r["end"] = r["t_start"], r["t_end"]
        out.append(r)
    return out


def create_video_output(video_id: int, target: int | None = None, auto_select: bool = True) -> dict:
    """Buat (atau pilih ulang) video hasil untuk SATU video sumber.

    Informasi output (lokasi, tanggal, waktu, kondisi lalin) diambil dari informasi video itu
    sendiri (otomatis dari Drone Video Downloader), lalu dari kelompok lokasi sebagai cadangan.
    """
    v = _video(video_id)
    batch = db.get("batch_jobs", v["batch_id"]) if v.get("batch_id") else None
    target = int(target or (batch or {}).get("final_duration") or 30)
    existing = db.query_one("SELECT id FROM final_videos WHERE source_video_id=? ORDER BY id DESC LIMIT 1",
                            (video_id,))
    if existing:
        if (_final(existing["id"]).get("target_duration") != target):
            db.update("final_videos", existing["id"], {"target_duration": target, "updated_at": db.now_iso()})
        return select_for_final(existing["id"]) if auto_select else get_final(existing["id"])
    g = db.get("location_groups", v["location_group_id"]) if v.get("location_group_id") else {}
    g = g or {}
    project = db.get("projects", v["project_id"]) or {}
    tmpl = _template_for_video(v)
    tcode = tmpl["code"] if tmpl else (batch or project).get("template_code")
    fid = db.insert("final_videos", {
        "project_id": v["project_id"], "batch_id": v.get("batch_id"), "source_video_id": video_id,
        "group_ids_json": [g["id"]] if g.get("id") else [], "cross_location": 0,
        "template_code": tcode, "target_duration": target,
        "trip_mode": (batch or {}).get("trip_mode") or "round_trip",
        "location_name": v.get("location_name") or g.get("location_name") or project.get("location_name"),
        "location_type": tmpl["location_type"] if tmpl else None,
        "traffic_condition": v.get("traffic_condition") or g.get("traffic_condition") or DEFAULT_TRAFFIC,
        "event_date": v.get("event_date") or g.get("event_date"),
        "event_time": v.get("event_time") or g.get("event_time"),
        "status": "draft", "created_at": db.now_iso(), "updated_at": db.now_iso(),
    })
    if auto_select:
        select_for_final(fid)
    return get_final(fid)


def create_final_video(project_id: int, group_ids: list[int], target: int, trip_mode: str,
                       batch_id: int | None = None, cross_location: bool = False,
                       location_name: str | None = None, traffic: str | None = None,
                       event_date: str | None = None, event_time: str | None = None,
                       auto_select: bool = True, source_video_id: int | None = None) -> dict:
    if target not in FINAL_DURATIONS:
        raise ValidationError("Durasi tiap video hasil harus kelipatan 5 detik, antara 10 dan 60 detik.")
    if source_video_id:
        f = create_video_output(source_video_id, target, auto_select=False)
        upd = {k: v for k, v in {"location_name": location_name, "traffic_condition": traffic,
                                 "event_date": event_date, "event_time": event_time}.items() if v}
        if upd:
            update_final(f["id"], upd)
        return select_for_final(f["id"]) if auto_select else get_final(f["id"])
    if not group_ids:
        raise ValidationError("Pilih minimal satu kelompok lokasi.")
    groups = [db.get("location_groups", g) for g in group_ids]
    if any(g is None for g in groups):
        raise NotFound("Kelompok lokasi tidak ditemukan.")
    if len(group_ids) > 1 and not cross_location:
        raise ValidationError("Footage dari lokasi berbeda tidak digabung otomatis. "
                              "Aktifkan 'gabungan lintas lokasi' untuk menggabungkan secara manual.")
    project = db.get("projects", project_id)
    if not project:
        raise NotFound("Proyek tidak ditemukan.")
    batch = db.get("batch_jobs", batch_id) if batch_id else None
    tcode = batch["template_code"] if batch else project["template_code"]
    tmpl = get_template(tcode)
    g0 = groups[0]
    if cross_location and not location_name:
        raise ValidationError("Isi nama lokasi/cakupan untuk video gabungan lintas lokasi.")
    fid = db.insert("final_videos", {
        "project_id": project_id, "batch_id": batch_id, "group_ids_json": group_ids,
        "cross_location": int(cross_location), "template_code": tcode, "target_duration": target,
        "trip_mode": trip_mode,
        "location_name": location_name or g0.get("location_name") or project.get("location_name"),
        "location_type": tmpl["location_type"],
        "traffic_condition": traffic or g0.get("traffic_condition") or DEFAULT_TRAFFIC,
        "event_date": event_date or g0.get("event_date"),
        "event_time": event_time or g0.get("event_time"),
        "status": "draft", "created_at": db.now_iso(), "updated_at": db.now_iso(),
    })
    if auto_select:
        select_for_final(fid)
    return get_final(fid)


def select_for_final(final_id: int) -> dict:
    f = _final(final_id)
    tmpl = get_template(f["template_code"])
    batch = db.get("batch_jobs", f["batch_id"]) if f.get("batch_id") else None
    # konfigurasi lintasan batch hanya berlaku untuk video dengan template yang sama dengan batch
    custom = (batch or {}).get("route") if (batch or {}).get("template_code") == f["template_code"] else None
    route = resolve_route(tmpl, custom)
    st = db.get_settings()
    cands = gather_candidates_for_final(f)
    per_video = bool(f.get("source_video_id"))
    res = selection_service.select_segments(cands, tmpl, route, f["trip_mode"], f["target_duration"],
                                            st, available_only=per_video)
    if per_video:
        v = _video(f["source_video_id"])
        rejected = [(r["t_start"], r["t_end"]) for r in db.query(
            "SELECT t_start, t_end FROM candidate_segments WHERE video_id=? AND deleted=1", (v["id"],))]
        segs, extra = selection_service.fill_from_source(res["segments"], v["id"], v.get("duration") or 0,
                                                         f["target_duration"], st, exclude=rejected)
        total = round(sum(s["end"] - s["start"] for s in segs), 3)
        report = res["report"]
        report["warnings"] = [w for w in report["warnings"] if not w.startswith("Footage tidak cukup")] + extra
        report["total"], report["meets_target"] = total, abs(total - f["target_duration"]) < 0.05
        if not report["meets_target"] and total > f["target_duration"]:
            report["warnings"].append(f"Durasi hasil {total:.1f} dtk melebihi target {f['target_duration']} dtk "
                                      "— perlu persetujuan operator sebelum ekspor.")
        res = {"segments": segs, "report": report}
    with db.transaction() as conn:
        conn.execute("DELETE FROM final_video_segments WHERE final_video_id=?", (final_id,))
        for s in res["segments"]:
            conn.execute(
                """INSERT INTO final_video_segments(final_video_id, candidate_id, video_id, order_index,
                   point_code, direction, role, t_start, t_end, ai_start, ai_end, origin, edited, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?, 'ai', 0, ?)""",
                (final_id, s["candidate_id"], s["video_id"], s["order_index"], s["point_code"],
                 s["direction"], s["role"], s["start"], s["end"], s["start"], s["end"], db.now_iso()))
    db.update("final_videos", final_id, {"selection_report_json": res["report"],
                                         "warnings_json": res["report"]["warnings"],
                                         "approved_duration_mismatch": 0, "updated_at": db.now_iso()})
    return get_final(final_id)


def _final(final_id: int) -> dict:
    f = db.get("final_videos", final_id)
    if not f:
        raise NotFound(f"Video final {final_id} tidak ditemukan")
    return f


def segments_of(final_id: int) -> list[dict]:
    rows = db.query("""SELECT s.*, v.filename AS video_filename, v.duration AS video_duration,
                         v.creation_time AS video_creation_time, v.proxy_path AS video_proxy
                       FROM final_video_segments s JOIN source_videos v ON v.id = s.video_id
                       WHERE s.final_video_id=? ORDER BY s.order_index, s.id""", (final_id,))
    out = []
    for r in rows:
        r["start"], r["end"] = r.pop("t_start"), r.pop("t_end")
        r["duration"] = round(r["end"] - r["start"], 3)
        r["has_proxy"] = bool(r.pop("video_proxy"))
        out.append(r)
    return out


def event_datetime(f: dict, segs: list[dict] | None = None):
    st = db.get_settings()
    segs = segs if segs is not None else segments_of(f["id"])
    meta_iso, offset = None, 0.0
    for s in segs:
        if s.get("video_creation_time"):
            meta_iso, offset = s["video_creation_time"], s["start"]
            break
    return naming_service.resolve_event_datetime(
        f.get("event_date"), f.get("event_time"), meta_iso,
        bool(st.get("metadata_time_is_utc", True)), float(st.get("local_utc_offset_hours", 7)), offset)


def duration_status(target: float, total: float) -> dict:
    diff = round(total - target, 2)
    if abs(diff) < 0.05:
        state, msg = "ok", "Durasi sesuai target."
    elif diff > 0:
        state, msg = "over", f"Total durasi melebihi target {diff:.1f} dtk."
    else:
        state, msg = "under", (f"Durasi {total:.1f} dtk, {abs(diff):.1f} dtk lebih pendek dari target "
                               "— tetap dapat diekspor.")
    return {"target": target, "total": round(total, 2), "difference": diff,
            "remaining": round(max(0.0, target - total), 2), "state": state, "message": msg}


def get_final(final_id: int) -> dict:
    f = _final(final_id)
    segs = segments_of(final_id)
    total = sum(s["duration"] for s in segs)
    f["segments"] = segs
    f["duration_status"] = duration_status(f["target_duration"], total)
    dt, src = event_datetime(f, segs)
    f["resolved_event_datetime"] = dt.isoformat() if dt else None
    f["time_source_resolved"] = src
    try:
        f["suggested_filename"] = naming_service.build_filename(dt, f.get("location_name"), f.get("traffic_condition"))
    except ValueError as e:
        f["suggested_filename"] = None
        f["filename_error"] = str(e)
    f["output_filename"] = f.get("custom_filename") or f.get("suggested_filename")
    if f["duration_status"]["state"] == "under":
        cands = gather_candidates_for_final(f)
        recs = selection_service.recommend_additional(cands, segs, f["duration_status"]["remaining"],
                                                      db.get_settings())
        f["recommendations"] = [{"id": c["id"], "video_id": c["video_id"], "point_code": c["point_code"],
                                 "direction": c["direction"], "start": c["start"], "end": c["end"],
                                 "quality_score": c.get("quality_score")} for c in recs]
    else:
        f["recommendations"] = []
    f["metadata"] = {
        "tanggal": dt.strftime("%d.%m.%Y") if dt else None,
        "waktu": dt.strftime("%H:%M") if dt else None,
        "nama_lokasi": f.get("location_name"),
        "jenis_lokasi": f.get("location_type"),
        "kondisi_lalin": f.get("traffic_condition"),
        "template": (get_template(f["template_code"]) or {}).get("name"),
        "durasi_final": round(total, 2),
        "jumlah_video_sumber": len({s["video_id"] for s in segs}),
        "jumlah_segmen": len(segs),
    }
    if f.get("source_video_id"):
        sv = db.get("source_videos", f["source_video_id"]) or {}
        f["source_video"] = {"id": sv.get("id"), "filename": sv.get("filename"), "duration": sv.get("duration"),
                             "source_origin": sv.get("source_origin")}
        f["metadata"]["video_sumber"] = sv.get("filename")
        meta = sv.get("source_meta") or {}
        for k_src, k_dst in (("weather", "cuaca"), ("url_original", "url_youtube"), ("timezone", "zona_waktu")):
            if meta.get(k_src):
                f["metadata"][k_dst] = meta[k_src]
    f["exports"] = db.query("SELECT * FROM export_jobs WHERE final_video_id=? ORDER BY id DESC", (final_id,))
    return f


def update_final(final_id: int, changes: dict) -> dict:
    f = _final(final_id)
    upd = {}
    for k in ("location_name", "traffic_condition", "event_date", "event_time", "trip_mode"):
        if k in changes:
            upd[k] = changes[k] or None
    if "traffic_condition" in upd and upd["traffic_condition"] and upd["traffic_condition"] not in TRAFFIC_CONDITIONS:
        # boleh diisi manual, tetapi tetap dinormalisasi oleh layanan penamaan
        pass
    if "target_duration" in changes:
        if int(changes["target_duration"]) not in FINAL_DURATIONS:
            raise ValidationError("Durasi tiap video hasil harus kelipatan 5 detik, antara 10 dan 60 detik.")
        upd["target_duration"] = int(changes["target_duration"])
    if "event_date" in upd and upd["event_date"]:
        from datetime import date
        try:
            date.fromisoformat(upd["event_date"])
        except ValueError as e:
            raise ValidationError("Format tanggal harus YYYY-MM-DD.") from e
    if "event_time" in upd and upd["event_time"]:
        import re
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", upd["event_time"]):
            raise ValidationError("Format waktu harus HH:MM (24 jam).")
    if "custom_filename" in changes:
        cf = changes["custom_filename"]
        upd["custom_filename"] = naming_service.sanitize_custom(cf) if cf else None
    if "approved_duration_mismatch" in changes:
        upd["approved_duration_mismatch"] = int(bool(changes["approved_duration_mismatch"]))
    if upd:
        upd["updated_at"] = db.now_iso()
        db.update("final_videos", final_id, upd)
        if "traffic_condition" in upd:
            for s in segments_of(final_id):
                if s.get("candidate_id"):
                    c = db.get("candidate_segments", s["candidate_id"])
                    if c:
                        record_feedback("traffic_label", c, traffic_label=upd["traffic_condition"])
    del f
    return get_final(final_id)


# ----------------------------------------------------------------- operasi segmen
def _seg(seg_id: int) -> dict:
    s = db.get("final_video_segments", seg_id)
    if not s:
        raise NotFound(f"Segmen {seg_id} tidak ditemukan")
    return s


def _log(final_id, seg_id, action, old=None, new=None, cand=None):
    db.insert("segment_edits", {"final_video_id": final_id, "final_segment_id": seg_id, "candidate_id": cand,
                                "action": action, "old_value_json": old, "new_value_json": new,
                                "created_at": db.now_iso()})
    db.update("final_videos", final_id, {"approved_duration_mismatch": 0, "updated_at": db.now_iso()})


def _renumber(final_id: int):
    rows = db.query("SELECT id FROM final_video_segments WHERE final_video_id=? ORDER BY order_index, id",
                    (final_id,))
    with db.transaction() as conn:
        for i, r in enumerate(rows):
            conn.execute("UPDATE final_video_segments SET order_index=? WHERE id=?", (i, r["id"]))


def add_segment(final_id: int, candidate_id: int | None = None, video_id: int | None = None,
                start: float | None = None, end: float | None = None, point_code: str | None = None,
                direction: str | None = None, position: int | None = None, role: str = "point") -> dict:
    f = _final(final_id)
    if candidate_id:
        c = get_candidate(candidate_id)
        video_id = c["video_id"]
        start = c["t_start"] if start is None else start
        end = c["t_end"] if end is None else end
        point_code = point_code or c["point_code"]
        direction = direction or c["direction"]
    if not video_id:
        raise ValidationError("Pilih kandidat atau video sumber.")
    v = _video(video_id)
    allowed = {x["id"] for x in final_source_videos(f)}
    if video_id not in allowed:
        raise ValidationError("Potongan harus berasal dari video sumber milik video hasil ini.")
    _check_point(get_template(f["template_code"]), point_code, direction)
    start, end = _validate_range(v, start, end)
    n = db.scalar("SELECT COUNT(*) FROM final_video_segments WHERE final_video_id=?", (final_id,))
    pos = n if position is None else max(0, min(int(position), n))
    db.execute("UPDATE final_video_segments SET order_index = order_index + 1 "
               "WHERE final_video_id=? AND order_index >= ?", (final_id, pos))
    sid = db.insert("final_video_segments", {
        "final_video_id": final_id, "candidate_id": candidate_id, "video_id": video_id,
        "order_index": pos, "point_code": point_code, "direction": direction, "role": role,
        "t_start": start, "t_end": end, "ai_start": start if candidate_id else None,
        "ai_end": end if candidate_id else None, "origin": "operator", "edited": 1,
        "created_at": db.now_iso()})
    _renumber(final_id)
    _log(final_id, sid, "add_segment", None, {"video_id": video_id, "start": start, "end": end}, candidate_id)
    if candidate_id:
        record_feedback("select_candidate", get_candidate(candidate_id))
    return get_final(final_id)


def update_segment(seg_id: int, changes: dict) -> dict:
    s = _seg(seg_id)
    f = _final(s["final_video_id"])
    v = _video(s["video_id"])
    upd = {}
    if "allocated" in changes and changes["allocated"] is not None:
        alloc = float(changes["allocated"])
        start = float(changes.get("start", s["t_start"]))
        end = start + alloc
        if v.get("duration") and end > v["duration"]:
            end = float(v["duration"])
            start = max(0.0, end - alloc)
        changes = {**changes, "start": start, "end": end}
    if "start" in changes or "end" in changes:
        st, en = _validate_range(v, changes.get("start", s["t_start"]), changes.get("end", s["t_end"]))
        upd["t_start"], upd["t_end"] = st, en
    if "point_code" in changes or "direction" in changes:
        _check_point(get_template(f["template_code"]), changes.get("point_code"), changes.get("direction"))
        for k in ("point_code", "direction"):
            if changes.get(k):
                upd[k] = changes[k]
    if changes.get("role") in ("point", "support"):
        upd["role"] = changes["role"]
    if not upd:
        return get_final(f["id"])
    upd["edited"] = 1
    db.update("final_video_segments", seg_id, upd)
    _log(f["id"], seg_id, "update_segment", {k: s.get(k) for k in upd}, upd, s.get("candidate_id"))
    if s.get("candidate_id"):
        c = db.get("candidate_segments", s["candidate_id"])
        if c:
            record_feedback("correct_segment", c, point_code=upd.get("point_code", s["point_code"]),
                            direction=upd.get("direction", s["direction"]),
                            start=upd.get("t_start", s["t_start"]), end=upd.get("t_end", s["t_end"]))
    return get_final(f["id"])


def reset_segment(seg_id: int) -> dict:
    s = _seg(seg_id)
    if s["ai_start"] is None:
        raise ValidationError("Segmen ini ditambahkan operator tanpa timestamp AI.")
    upd = {"t_start": s["ai_start"], "t_end": s["ai_end"], "edited": 0}
    if s.get("candidate_id"):
        c = db.get("candidate_segments", s["candidate_id"])
        if c:
            upd["point_code"] = c.get("ai_point_code") or c["point_code"]
            upd["direction"] = c.get("ai_direction") or c["direction"]
    db.update("final_video_segments", seg_id, upd)
    _log(s["final_video_id"], seg_id, "reset_segment", None, upd)
    return get_final(s["final_video_id"])


def delete_segment(seg_id: int) -> dict:
    s = _seg(seg_id)
    db.execute("DELETE FROM final_video_segments WHERE id=?", (seg_id,))
    _renumber(s["final_video_id"])
    _log(s["final_video_id"], None, "delete_segment", {"segment_id": seg_id, "start": s["t_start"],
                                                       "end": s["t_end"]}, None, s.get("candidate_id"))
    if s.get("candidate_id"):
        c = db.get("candidate_segments", s["candidate_id"])
        if c:
            record_feedback("remove_from_final", c)
    return get_final(s["final_video_id"])


def replace_segment(seg_id: int, candidate_id: int, keep_duration: bool = True) -> dict:
    s = _seg(seg_id)
    f = _final(s["final_video_id"])
    c = get_candidate(candidate_id)
    allowed = {x["id"] for x in final_source_videos(f)}
    if c["video_id"] not in allowed:
        raise ValidationError("Kandidat pengganti bukan dari video sumber milik video hasil ini.")
    length = s["t_end"] - s["t_start"]
    st, en = c["t_start"], c["t_end"]
    if keep_duration and en - st > length:
        mid = (st + en) / 2
        st, en = mid - length / 2, mid + length / 2
    db.update("final_video_segments", seg_id, {
        "candidate_id": candidate_id, "video_id": c["video_id"], "point_code": c["point_code"],
        "direction": c["direction"], "t_start": round(st, 3), "t_end": round(en, 3),
        "ai_start": round(st, 3), "ai_end": round(en, 3), "edited": 1})
    _log(f["id"], seg_id, "replace_segment", {"candidate_id": s.get("candidate_id")}, {"candidate_id": candidate_id},
         candidate_id)
    record_feedback("select_candidate", c)
    return get_final(f["id"])


def reorder_segments(final_id: int, ordered_ids: list[int]) -> dict:
    _final(final_id)
    current = [r["id"] for r in db.query("SELECT id FROM final_video_segments WHERE final_video_id=?", (final_id,))]
    if sorted(current) != sorted(ordered_ids):
        raise ValidationError("Daftar urutan harus memuat seluruh segmen video final tepat satu kali.")
    with db.transaction() as conn:
        for i, sid in enumerate(ordered_ids):
            conn.execute("UPDATE final_video_segments SET order_index=? WHERE id=?", (i, sid))
    _log(final_id, None, "reorder", None, {"order": ordered_ids})
    return get_final(final_id)


def set_allocations(final_id: int, allocations: dict[int, float]) -> dict:
    for sid, sec in allocations.items():
        s = _seg(int(sid))
        if s["final_video_id"] != final_id:
            raise ValidationError(f"Segmen {sid} bukan milik video final ini.")
        update_segment(int(sid), {"allocated": float(sec)})
    return get_final(final_id)


def list_finals(batch_id: int | None = None, project_id: int | None = None) -> list[dict]:
    sql, params = "SELECT * FROM final_videos WHERE 1=1", []
    if batch_id:
        sql += " AND batch_id=?"
        params.append(batch_id)
    if project_id:
        sql += " AND project_id=?"
        params.append(project_id)
    rows = db.query(sql + " ORDER BY id DESC", params)
    for r in rows:
        if r.get("source_video_id"):
            sv = db.get("source_videos", r["source_video_id"]) or {}
            r["source_filename"] = sv.get("filename")
            r["source_order"] = sv.get("order_index")
        total = db.scalar("SELECT COALESCE(SUM(t_end - t_start),0) FROM final_video_segments WHERE final_video_id=?",
                          (r["id"],))
        r["total_duration"] = round(total or 0, 2)
        r["segment_count"] = db.scalar("SELECT COUNT(*) FROM final_video_segments WHERE final_video_id=?", (r["id"],))
    return rows

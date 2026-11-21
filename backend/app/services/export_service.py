"""Ekspor video dengan FFmpeg: video final gabungan, potongan individual, dan preview.

* File sumber tidak pernah diubah (hanya dibaca).
* Stream copy dipakai bila semua segmen kompatibel dan titik potong jatuh pada
  keyframe (mode ``auto``) atau bila dipaksa (``copy``); selain itu re-encode.
* Parameter video disamakan (resolusi, fps, pix_fmt, audio AAC stereo 48 kHz)
  agar penggabungan aman walau sumber berbeda resolusi/frame rate/codec/audio.
* NVENC dipakai bila GPU NVIDIA terdeteksi; gagal -> otomatis libx264 (CPU).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..core.config import paths
from ..core.logging_setup import get_logger
from ..database import db
from . import hardware_service, naming_service, timeline_service
from .video_service import ffmpeg_exe, ffprobe_exe, run_cmd, run_ffmpeg_progress

log = get_logger("export")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="export")
_name_lock = threading.Lock()


class ExportError(Exception):
    pass


# ====================================================================== parameter
def output_dir_for(final: dict) -> Path:
    st = db.get_settings()
    base = Path(st["output_dir"]) if st.get("output_dir") else paths.exports
    project = db.get("projects", final["project_id"]) or {}
    folder = naming_service.to_token(project.get("name"), f"Proyek{final['project_id']}")
    return base / f"{final['project_id']:03d}_{folder}"


def _even(x: int) -> int:
    return max(2, int(x) // 2 * 2)


def target_params(segs: list[dict], settings: dict) -> dict:
    """Parameter output: resolusi & frame rate ASLI sumber dipertahankan.

    * Resolusi = resolusi sumber yang paling banyak dipakai; hanya diperkecil bila pengguna
      menetapkan batas tinggi (``export_max_height`` > 0).
    * Frame rate = frame rate sumber bila seragam (filter fps tidak dipasang sama sekali, sehingga
      timing frame asli utuh); bila sumber berbeda-beda dipakai yang paling banyak.
    """
    vids = {s["video_id"]: db.get("source_videos", s["video_id"]) for s in segs}
    res = Counter((v["width"], v["height"]) for v in vids.values() if v and v.get("width"))
    w, h = res.most_common(1)[0][0] if res else (1920, 1080)
    max_h = int(settings.get("export_max_height") or 0)
    if max_h and h > max_h:
        w, h = w * max_h / h, max_h
    fps_count = Counter(round(v["fps"], 3) for v in vids.values() if v and v.get("fps"))
    uniform_fps = len(fps_count) == 1
    if fps_count:
        fps = fps_count.most_common(1)[0][0]
    else:
        fps = float(settings.get("export_fps", 30))
    return {"width": _even(w), "height": _even(h), "fps": fps, "uniform_fps": uniform_fps}


def choose_encoder(settings: dict) -> str:
    hevc = settings.get("export_codec") == "hevc"
    hw = hardware_service.detect()
    if settings.get("use_gpu_encoder") and hw.get("nvenc_available"):
        return "hevc_nvenc" if hevc else "h264_nvenc"
    if hevc and _has_encoder("libx265"):
        return "libx265"
    return "libx264"


_ENC_CACHE: dict[str, bool] = {}


def _has_encoder(name: str) -> bool:
    if name not in _ENC_CACHE:
        try:
            res = run_cmd([ffmpeg_exe(), "-hide_banner", "-encoders"], timeout=30)
            _ENC_CACHE[name] = f" {name} " in res.stdout
        except Exception:  # noqa: BLE001
            _ENC_CACHE[name] = False
    return _ENC_CACHE[name]


def quality_summary(settings: dict, encoder: str | None = None) -> dict:
    enc = encoder or choose_encoder(settings)
    crf = int(settings.get("export_crf", 16))
    return {"encoder": enc, "codec": "H.265 (HEVC)" if "265" in enc or "hevc" in enc else "H.264 (AVC)",
            "crf": crf + (2 if enc == "libx265" else 0), "preset": settings.get("export_preset", "slow"),
            "audio": f"AAC {int(settings.get('export_audio_bitrate', 320))} kbps 48 kHz stereo",
            "pix_fmt": "yuv420p"}


def _venc_args(encoder: str, settings: dict, preview: bool = False) -> list[str]:
    crf = int(settings.get("export_crf", 16))
    if preview:
        return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"]
    if encoder in ("h264_nvenc", "hevc_nvenc"):
        args = ["-c:v", encoder, "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", str(crf), "-b:v", "0",
                "-spatial-aq", "1", "-temporal-aq", "1", "-bf", "3"]
        return args + (["-profile:v", "high"] if encoder == "h264_nvenc" else ["-tag:v", "hvc1"])
    if encoder == "libx265":
        return ["-c:v", "libx265", "-preset", settings.get("export_preset", "slow"), "-crf", str(crf + 2),
                "-tag:v", "hvc1", "-x265-params", "log-level=error"]
    return ["-c:v", "libx264", "-preset", settings.get("export_preset", "slow"), "-crf", str(crf),
            "-profile:v", "high"]


def _aenc_args(settings: dict, preview: bool = False) -> list[str]:
    br = 128 if preview else int(settings.get("export_audio_bitrate", 320))
    return ["-c:a", "aac", "-b:a", f"{br}k", "-ar", "48000", "-ac", "2"]


def keyframe_aligned(path: str, t: float, tol: float = 0.05) -> bool:
    res = run_cmd([ffprobe_exe(), "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                   "-read_intervals", f"{max(0, t - 1):.3f}%+2", "-show_entries", "frame=pts_time",
                   "-of", "csv=p=0", path], timeout=60)
    if res.returncode != 0:
        return False
    for line in res.stdout.split():
        try:
            if abs(float(line.strip().strip(",")) - t) <= tol:
                return True
        except ValueError:
            continue
    return False


def can_stream_copy(segs: list[dict], settings: dict) -> tuple[bool, str]:
    mode = settings.get("export_mode", "auto")
    if mode == "reencode":
        return False, "re-encode dipaksa oleh pengaturan"
    vids = [db.get("source_videos", s["video_id"]) for s in segs]
    sig = {(v["codec"], v["width"], v["height"], round(v["fps"] or 0, 2), v["audio_codec"]) for v in vids}
    if len(sig) > 1:
        return False, "parameter video sumber berbeda (resolusi/fps/codec/audio)"
    codec = vids[0]["codec"] if vids else None
    if codec not in ("h264", "hevc"):
        return False, f"codec {codec} tidak didukung untuk stream copy"
    max_h = int(settings.get("export_max_height") or 0)
    if max_h and vids and vids[0]["height"] and vids[0]["height"] > max_h and mode != "copy":
        return False, "resolusi sumber melebihi batas ekspor, perlu diskalakan"
    if mode == "copy":
        return True, "stream copy dipaksa oleh pengaturan (titik potong mengikuti keyframe)"
    for s in segs:
        v = db.get("source_videos", s["video_id"])
        if not keyframe_aligned(v["path"], s["start"]):
            return False, "titik potong tidak jatuh pada keyframe; re-encode untuk ketepatan durasi"
    return True, "semua segmen kompatibel dan selaras keyframe"


# ====================================================================== render
def _render_part(src: dict, start: float, end: float, dst: str, params: dict, encoder: str,
                 settings: dict, preview: bool = False, on_progress=None) -> str:
    dur = end - start
    w, h, fps = params["width"], params["height"], params["fps"]
    filters = []
    if (src.get("width"), src.get("height")) != (w, h):
        # skala berkualitas tinggi (lanczos) hanya bila resolusi sumber memang berbeda
        filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                       f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
    filters.append("setsar=1")
    if not params.get("uniform_fps", False) or preview:
        filters.append(f"fps={fps}")
    filters.append("format=yuv420p")
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", src["path"]]
    has_audio = bool(src.get("audio_codec"))
    if not has_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    cmd += ["-t", f"{dur:.3f}", "-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
            "-vf", ",".join(filters), *_venc_args(encoder, settings, preview), "-pix_fmt", "yuv420p",
            *_aenc_args(settings, preview),
            "-video_track_timescale", "90000", "-movflags", "+faststart", "-shortest", dst]
    code, err = run_ffmpeg_progress(cmd, dur, on_progress)
    if code != 0:
        if encoder not in ("libx264",) and not preview:
            log.warning("Encoder %s gagal, fallback ke libx264: %s", encoder, err[-300:])
            return _render_part(src, start, end, dst, params, "libx264", settings, preview, on_progress)
        raise ExportError(f"FFmpeg gagal memotong {src['filename']}: {err.strip()[-400:]}")
    return encoder


def _copy_part(src: dict, start: float, end: float, dst: str) -> None:
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", src["path"],
           "-t", f"{end - start:.3f}", "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
           "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", dst]
    res = run_cmd(cmd)
    if res.returncode != 0:
        raise ExportError(f"Stream copy gagal: {res.stderr.strip()[-300:]}")


def _concat(parts: list[str], dst: str, metadata: dict, copy_mode: bool) -> None:
    lst = Path(dst).with_suffix(".concat.txt")
    lst.write_text("".join(f"file '{Path(p).as_posix()}'\n" for p in parts), encoding="utf-8")
    meta_args = []
    for k, v in metadata.items():
        if v is not None:
            meta_args += ["-metadata", f"{k}={v}"]
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-map", "0:v", "-map", "0:a?", "-c", "copy", *meta_args, "-movflags", "+faststart", dst]
    res = run_cmd(cmd)
    lst.unlink(missing_ok=True)
    if res.returncode != 0:
        raise ExportError(f"Penggabungan gagal: {res.stderr.strip()[-400:]}")


def _progress_cb(eid: int, before: float, total: float, seg_dur: float):
    state = {"last": 0.0}

    def cb(frac: float) -> None:
        p = round(0.95 * (before + frac * seg_dur) / total, 3)
        if p - state["last"] >= 0.01:
            state["last"] = p
            db.update("export_jobs", eid, {"progress": p})
    return cb


def media_duration(path: str) -> float | None:
    res = run_cmd([ffprobe_exe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    try:
        return round(float(res.stdout.strip()), 3)
    except ValueError:
        return None


def _reserved_names() -> set[str]:
    rows = db.query("SELECT output_path FROM export_jobs WHERE output_path IS NOT NULL AND status IN ('queued','running')")
    return {Path(r["output_path"]).name for r in rows}


# ====================================================================== job
def validate_for_export(final: dict, kind: str) -> list[str]:
    errors = []
    if not final["segments"]:
        errors.append("Video final belum memiliki segmen.")
    if kind == "final":
        ds = final["duration_status"]
        # Durasi lebih PENDEK dari target (mis. sebagian video dihapus/ditolak) diizinkan langsung.
        # Hanya durasi yang MELEBIHI target yang perlu persetujuan operator.
        if ds["state"] == "over" and not final.get("approved_duration_mismatch"):
            errors.append(f"{ds['message']} Setujui durasi aktual ({ds['total']:.1f} dtk) atau sesuaikan timeline.")
    if kind in ("final", "individual") and not final.get("output_filename"):
        errors.append(final.get("filename_error") or "Nama file belum dapat dibentuk.")
    return errors


def export_info(final_id: int) -> dict:
    """Informasi sebelum ekspor: sumber, parameter output, mode, dan perkiraan ukuran file."""
    final = timeline_service.get_final(final_id)
    st = db.get_settings()
    segs = final["segments"]
    if not segs:
        return {"sources": [], "segments": 0, "duration": 0, "mode": None}
    vids = {}
    for s in segs:
        v = db.get("source_videos", s["video_id"])
        if v and v["id"] not in vids:
            vids[v["id"]] = v
    params = target_params(segs, st)
    copy_ok, reason = can_stream_copy(segs, st)
    dur = sum(s["end"] - s["start"] for s in segs)
    abr = int(st.get("export_audio_bitrate", 320)) * 1000
    if copy_ok:
        est_bits = sum((vids[s["video_id"]].get("bit_rate") or 0) * (s["end"] - s["start"]) for s in segs)
    else:
        # perkiraan: bitrate sumber sebagai acuan, dibatasi oleh perkiraan bit-per-piksel CRF
        crf = int(st.get("export_crf", 16))
        bpp = 0.11 * (0.86 ** (crf - 16))
        if "265" in choose_encoder(st) or "hevc" in choose_encoder(st):
            bpp *= 0.6
        model = params["width"] * params["height"] * (params["fps"] or 30) * bpp
        src_br = [v.get("bit_rate") for v in vids.values() if v.get("bit_rate")]
        vbr = min(model, max(src_br) * 1.15) if src_br else model
        est_bits = (vbr + abr) * dur
    return {
        "sources": [{"id": v["id"], "filename": v["filename"], "width": v["width"], "height": v["height"],
                     "fps": v["fps"], "duration": v["duration"], "codec": v["codec"],
                     "audio_codec": v.get("audio_codec"), "bit_rate": v.get("bit_rate"),
                     "size_bytes": v.get("size_bytes")} for v in vids.values()],
        "segments": len(segs), "duration": round(dur, 2),
        "output": {"width": params["width"], "height": params["height"], "fps": params["fps"],
                   "keeps_source_resolution": all((v["width"], v["height"]) == (params["width"], params["height"]) for v in vids.values()),
                   "keeps_source_fps": params["uniform_fps"]},
        "mode": "copy" if copy_ok else "reencode", "mode_reason": reason,
        "quality": None if copy_ok else quality_summary(st),
        "estimated_size_bytes": int(est_bits / 8) if est_bits else None,
    }


def start_export(final_id: int, kind: str = "final") -> dict:
    if kind not in ("final", "individual", "preview"):
        raise ExportError("Jenis ekspor tidak dikenal.")
    final = timeline_service.get_final(final_id)
    errs = validate_for_export(final, kind)
    if errs:
        raise ExportError(" ".join(errs))
    eid = db.insert("export_jobs", {"final_video_id": final_id, "kind": kind, "status": "queued",
                                    "progress": 0, "created_at": db.now_iso()})
    if kind == "final":
        db.update("final_videos", final_id, {"status": "exporting", "updated_at": db.now_iso()})
    _executor.submit(_run_job, eid)
    return db.get("export_jobs", eid)


def _run_job(eid: int) -> None:
    job = db.get("export_jobs", eid)
    try:
        db.update("export_jobs", eid, {"status": "running"})
        final = timeline_service.get_final(job["final_video_id"])
        if job["kind"] == "final":
            _export_final(eid, final)
        elif job["kind"] == "individual":
            _export_individual(eid, final)
        else:
            _export_preview(eid, final)
        db.update("export_jobs", eid, {"status": "done", "progress": 1.0, "finished_at": db.now_iso()})
        if job["kind"] == "final":
            db.update("final_videos", job["final_video_id"], {"status": "exported", "updated_at": db.now_iso()})
            _mark_items_done(final)
    except Exception as e:  # noqa: BLE001
        log.exception("Ekspor %s gagal", eid)
        db.update("export_jobs", eid, {"status": "failed", "error": str(e)[:1000], "finished_at": db.now_iso()})
        if job["kind"] == "final":
            db.update("final_videos", job["final_video_id"], {"status": "failed", "updated_at": db.now_iso()})
    finally:
        db.close_thread_conn()


def _mark_items_done(final: dict) -> None:
    vids = {s["video_id"] for s in final["segments"]}
    for vid in vids:
        db.execute("UPDATE batch_items SET status='done', finished_at=? WHERE video_id=? AND status='review'",
                   (db.now_iso(), vid))
    if final.get("batch_id"):
        from . import batch_service
        batch_service.refresh_batch_status(final["batch_id"])


def _metadata(final: dict) -> dict:
    m = final["metadata"]
    return {"title": final.get("output_filename", "").removesuffix(".mp4"),
            "comment": json.dumps(m, ensure_ascii=False),
            "location": m.get("nama_lokasi"), "description": f"{m.get('jenis_lokasi')} - {m.get('kondisi_lalin')}"}


def _export_final(eid: int, final: dict) -> None:
    st = db.get_settings()
    segs = final["segments"]
    out_dir = output_dir_for(final)
    with _name_lock:
        out = naming_service.unique_path(out_dir, final["output_filename"], _reserved_names())
        db.update("export_jobs", eid, {"output_path": str(out)})
    copy_ok, reason = can_stream_copy(segs, st)
    encoder = "copy" if copy_ok else choose_encoder(st)
    params = target_params(segs, st)
    tmp = Path(tempfile.mkdtemp(prefix=f"export_{eid}_", dir=paths.temporary))
    try:
        parts = []
        used_enc = set()
        total = sum(x["end"] - x["start"] for x in segs) or 1.0
        done_before, acc = [], 0.0
        for x in segs:
            done_before.append(acc)
            acc += x["end"] - x["start"]
        for i, s in enumerate(segs):
            src = db.get("source_videos", s["video_id"])
            part = str(tmp / f"part_{i:03d}.mp4")
            if copy_ok:
                _copy_part(src, s["start"], s["end"], part)
            else:
                used_enc.add(_render_part(src, s["start"], s["end"], part, params, encoder, st,
                                          on_progress=_progress_cb(eid, done_before[i], total, s["end"] - s["start"])))
            parts.append(part)
            db.update("export_jobs", eid, {"progress": round(0.95 * (done_before[i] + s["end"] - s["start"]) / total, 3)})
        part_out = str(out) + ".part.mp4"
        _concat(parts, part_out, _metadata(final), copy_ok)
        os.replace(part_out, out)
        dur = media_duration(str(out))
        sidecar = out.with_suffix(".json")
        sidecar.write_text(json.dumps({
            "file": out.name, "metadata": final["metadata"], "export_mode": "stream copy" if copy_ok else "re-encode",
            "mode_reason": reason, "encoder": ",".join(sorted(used_enc)) or encoder, "params": params,
            "segments": [{"order": s["order_index"] + 1, "video": s["video_filename"], "start": s["start"],
                          "end": s["end"], "point": s["point_code"], "direction": s["direction"],
                          "role": s["role"], "edited_by_operator": bool(s["edited"])} for s in segs],
            "duration_target": final["target_duration"], "duration_actual": dur,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        db.update("export_jobs", eid, {"mode": "copy" if copy_ok else "reencode",
                                       "encoder": ",".join(sorted(used_enc)) or encoder,
                                       "duration": dur, "output_files_json": [str(out), str(sidecar)]})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _export_individual(eid: int, final: dict) -> None:
    st = db.get_settings()
    segs = final["segments"]
    base = output_dir_for(final) / (final["output_filename"].removesuffix(".mp4") + "_segmen")
    params = target_params(segs, st)
    encoder = choose_encoder(st)
    files = []
    for i, s in enumerate(segs):
        src = db.get("source_videos", s["video_id"])
        name = naming_service.segment_filename(final["output_filename"], i + 1, s["point_code"] or "X",
                                               s["direction"] or "outbound")
        with _name_lock:
            out = naming_service.unique_path(base, name)
            out.touch()
        part = str(out) + ".part.mp4"
        _render_part(src, s["start"], s["end"], part, params, encoder, st,
                     on_progress=_progress_cb(eid, i, len(segs), 1.0))
        os.replace(part, out)
        files.append(str(out))
        db.update("export_jobs", eid, {"progress": round((i + 1) / len(segs), 3), "output_files_json": files})
    (base / "segmen.json").write_text(json.dumps({
        "final_video": final["output_filename"], "metadata": final["metadata"],
        "segments": [{"file": Path(f).name, "video": s["video_filename"], "start": s["start"], "end": s["end"],
                      "point": s["point_code"], "direction": s["direction"]} for f, s in zip(files, segs)],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    db.update("export_jobs", eid, {"output_path": str(base), "mode": "reencode", "encoder": encoder})


def _export_preview(eid: int, final: dict) -> None:
    st = db.get_settings()
    segs = final["segments"]
    out = paths.temporary / "previews" / f"final_{final['id']}_{eid}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    params = target_params(segs, st)
    scale = 480 / params["height"] if params["height"] > 480 else 1
    params = {"width": _even(params["width"] * scale), "height": _even(params["height"] * scale),
              "fps": min(params["fps"], 30), "uniform_fps": False}
    tmp = Path(tempfile.mkdtemp(prefix=f"preview_{eid}_", dir=paths.temporary))
    try:
        parts = []
        enc = choose_encoder(st)
        for i, s in enumerate(segs):
            src = db.get("source_videos", s["video_id"])
            part = str(tmp / f"p_{i:03d}.mp4")
            _render_part(src, s["start"], s["end"], part, params, enc, st, preview=True)
            parts.append(part)
            db.update("export_jobs", eid, {"progress": round(0.9 * (i + 1) / len(segs), 3)})
        _concat(parts, str(out), {"title": "Preview"}, False)
        db.update("export_jobs", eid, {"output_path": str(out), "duration": media_duration(str(out)),
                                       "mode": "preview", "encoder": enc})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def wait_all(timeout: float = 600) -> None:
    """Untuk pengujian: tunggu antrean ekspor kosong."""
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        n = db.scalar("SELECT COUNT(*) FROM export_jobs WHERE status IN ('queued','running')")
        if not n:
            return
        time.sleep(0.2)
    raise TimeoutError("Ekspor belum selesai")

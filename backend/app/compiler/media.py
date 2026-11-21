"""Impor media Video Compiler: probe (ffprobe), thumbnail, waveform, dan proxy preview."""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..core.logging_setup import get_logger
from ..services.video_service import ffmpeg_exe, ffprobe_exe, run_cmd
from . import store
from .store import CompilerError

log = get_logger("compiler.media")
_bg = ThreadPoolExecutor(max_workers=2, thread_name_prefix="compiler-media")

# Container/codec yang dapat diputar langsung oleh browser (Chrome/Edge) untuk preview.
_WEB_VIDEO_EXT = {".mp4", ".m4v", ".mov", ".webm"}
_WEB_VIDEO_CODEC = {"h264", "vp8", "vp9", "av1"}
_WEB_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac"}


def _rate(r: str | None) -> float | None:
    try:
        a, b = (r or "0/0").split("/")
        return round(float(a) / float(b), 3) if float(b) else None
    except ValueError:
        return None


def probe_any(path: str) -> dict:
    res = run_cmd([ffprobe_exe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                  timeout=60)
    if res.returncode != 0:
        raise CompilerError(f"File tidak dapat dibaca: {res.stderr.strip()[:200]}")
    data = json.loads(res.stdout or "{}")
    st = data.get("streams", [])
    fmt = data.get("format", {})
    v = next((s for s in st if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in st if s.get("codec_type") == "audio"), None)
    try:
        dur = float(fmt.get("duration") or (v or a or {}).get("duration") or 0)
    except ValueError:
        dur = 0.0
    w, h = (v or {}).get("width"), (v or {}).get("height")
    rot = None
    for sd in (v or {}).get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = sd["rotation"]
    if rot in (90, -90, 270, -270) and w and h:
        w, h = h, w
    return {"duration": round(dur, 3) if dur > 0 else None, "width": w, "height": h,
            "fps": _rate((v or {}).get("avg_frame_rate")) or _rate((v or {}).get("r_frame_rate")),
            "vcodec": (v or {}).get("codec_name"), "acodec": (a or {}).get("codec_name"),
            "has_video": v is not None, "has_audio": a is not None,
            "bit_rate": int(fmt["bit_rate"]) if fmt.get("bit_rate") else None}


def register_file(path: str, display_name: str | None = None, uploaded: bool = False) -> dict:
    p = Path(path)
    if not p.is_file():
        raise CompilerError(f"File tidak ditemukan: {path}")
    kind = store.kind_of(display_name or p.name)
    if kind == "svg":
        raise CompilerError("SVG perlu diimpor lewat tombol Import / drag & drop (otomatis dikonversi ke PNG).")
    if not kind:
        raise CompilerError(f"Tipe file tidak didukung: {p.suffix or p.name}")
    # file yang sama (path asli) tidak didaftarkan dua kali
    if not uploaded:
        rp = str(p.resolve())
        for m in store.all_media().values():
            if m.get("path") == rp and Path(rp).stat().st_size == m.get("size"):
                return m
    info = probe_any(str(p))
    if kind == "video" and not info["has_video"]:
        kind = "audio" if info["has_audio"] else None
    if kind == "audio" and not info["has_audio"]:
        raise CompilerError("File audio tidak memiliki stream suara.")
    if kind == "image" and not info["width"]:
        raise CompilerError("Gambar tidak dapat dibaca.")
    if not kind:
        raise CompilerError("File tidak memiliki stream video maupun audio.")
    if kind in ("video", "audio") and not info["duration"]:
        raise CompilerError("Durasi media tidak dapat dibaca.")
    m = {"id": store.new_id("m"), "name": display_name or p.name, "path": str(p.resolve()), "kind": kind,
         "ext": Path(display_name or p.name).suffix.lower(), "size": p.stat().st_size, "uploaded": uploaded,
         "imported_at": store.now_iso(), **info,
         "has_audio": bool(info["has_audio"]) and kind in ("video", "audio"),
         "thumb": None, "wave": None, "proxy": "none", "proxy_path": None}
    if kind == "image":
        m["duration"] = None
        m["has_audio"] = False
    m["proxy"] = "pending" if needs_proxy(m) else "none"
    store.put_media(m)
    _bg.submit(_post_process, m["id"])
    return m


def needs_proxy(m: dict) -> bool:
    if m["kind"] == "video":
        return m["ext"] not in _WEB_VIDEO_EXT or (m.get("vcodec") or "") not in _WEB_VIDEO_CODEC
    if m["kind"] == "audio":
        return m["ext"] not in _WEB_AUDIO_EXT
    return False


def _post_process(mid: str) -> None:
    m = store.all_media().get(mid)
    if not m:
        return
    d = store.dirs()
    try:
        if m["kind"] in ("video", "image"):
            dst = d["thumbs"] / f"{mid}.jpg"
            t = 0 if m["kind"] == "image" else min(1.0, (m.get("duration") or 0) / 3)
            cmd = [ffmpeg_exe(), "-y", "-v", "error"]
            if m["kind"] == "video":
                cmd += ["-ss", f"{t:.2f}"]
            cmd += ["-i", m["path"], "-frames:v", "1", "-vf", "scale=320:-2:flags=bicubic", "-q:v", "4", str(dst)]
            if run_cmd(cmd, timeout=120).returncode == 0:
                store.update_media(mid, thumb=str(dst))
        if m.get("has_audio"):
            dst = d["thumbs"] / f"{mid}_wave.png"
            cmd = [ffmpeg_exe(), "-y", "-v", "error", "-i", m["path"], "-filter_complex",
                   "aformat=channel_layouts=mono,showwavespic=s=1600x120:colors=white", "-frames:v", "1", str(dst)]
            if run_cmd(cmd, timeout=600).returncode == 0:
                store.update_media(mid, wave=str(dst))
        if m.get("proxy") == "pending":
            _make_proxy(m)
    except Exception as e:  # noqa: BLE001
        log.warning("Pasca-proses media %s gagal: %s", mid, e)


def _make_proxy(m: dict) -> None:
    d = store.dirs()
    if m["kind"] == "video":
        dst = d["proxies"] / f"{m['id']}.mp4"
        cmd = [ffmpeg_exe(), "-y", "-v", "error", "-i", m["path"], "-map", "0:v:0", "-map", "0:a:0?",
               "-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
               "-g", "15", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
               str(dst) + ".part.mp4"]
    else:
        dst = d["proxies"] / f"{m['id']}.m4a"
        cmd = [ffmpeg_exe(), "-y", "-v", "error", "-i", m["path"], "-vn", "-c:a", "aac", "-b:a", "192k",
               str(dst) + ".part.m4a"]
    res = run_cmd(cmd)
    part = Path(cmd[-1])
    if res.returncode == 0 and part.is_file():
        os.replace(part, dst)
        store.update_media(m["id"], proxy="ready", proxy_path=str(dst))
    else:
        part.unlink(missing_ok=True)
        store.update_media(m["id"], proxy="failed")
        log.warning("Proxy %s gagal: %s", m["name"], res.stderr[-300:])


_SAFE = re.compile(r"[^A-Za-z0-9._ ()\-\[\]]+")


def upload_target(filename: str) -> Path:
    name = _SAFE.sub("_", Path(filename).name).strip() or "media"
    d = store.dirs()["media"] / store.new_id("u")
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def register_paths(items: list[str]) -> dict:
    """Daftarkan file/folder dari komputer pengguna TANPA menyalin (dibaca langsung dari lokasi asli)."""
    added, errors = [], []
    for raw in items:
        raw = (raw or "").strip().strip('"')
        if not raw:
            continue
        p = Path(raw).expanduser()
        files = sorted(x for x in p.iterdir() if x.is_file()) if p.is_dir() else [p]
        for f in files:
            if p.is_dir() and store.kind_of(f.name) in (None, "svg"):
                continue
            try:
                added.append(register_file(str(f)))
            except CompilerError as e:
                errors.append({"path": str(f), "error": str(e)})
    return {"added": added, "errors": errors}


def public(m: dict) -> dict:
    """Info media untuk frontend (path asli tetap dikirim agar pengguna tahu sumbernya)."""
    out = {k: v for k, v in m.items() if k not in ("proxy_path",)}
    out["thumb"] = bool(m.get("thumb"))
    out["wave"] = bool(m.get("wave"))
    return out

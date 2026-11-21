"""Operasi video: probe metadata (ffprobe), sampling frame (OpenCV), proxy preview."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

from ..core.config import paths
from ..core.logging_setup import get_logger

log = get_logger("video")

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("FFmpeg tidak ditemukan di PATH.")
    return exe


def ffprobe_exe() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("FFprobe tidak ditemukan di PATH.")
    return exe


def run_cmd(cmd: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          creationflags=_NO_WINDOW, encoding="utf-8", errors="replace")


def _parse_rate(rate: str | None) -> float | None:
    if not rate or rate in ("0/0", "0"):
        return None
    try:
        if "/" in rate:
            a, b = rate.split("/")
            return float(a) / float(b) if float(b) else None
        return float(rate)
    except ValueError:
        return None


def parse_creation_time(raw: str | None) -> datetime | None:
    """Kembalikan datetime aware (UTC) jika metadata waktu dapat dipercaya."""
    if not raw:
        return None
    s = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.strptime(raw.strip()[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if dt.year < 2005 or dt > now + timedelta(days=1):
        return None  # nilai default kamera / tidak valid
    return dt


def probe(path: str | Path) -> dict:
    """Baca metadata video. Melempar RuntimeError jika file tidak valid."""
    path = str(path)
    if not os.path.isfile(path):
        raise RuntimeError(f"File tidak ditemukan: {path}")
    res = run_cmd([ffprobe_exe(), "-v", "error", "-print_format", "json", "-show_format",
                   "-show_streams", path], timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe gagal: {res.stderr.strip()[:300]}")
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v is None:
        raise RuntimeError("Tidak ada stream video di dalam file.")
    fmt = data.get("format", {})
    duration = None
    for cand in (fmt.get("duration"), v.get("duration")):
        try:
            duration = float(cand)
            break
        except (TypeError, ValueError):
            continue
    if not duration or duration <= 0:
        raise RuntimeError("Durasi video tidak dapat dibaca.")
    tags = {**(fmt.get("tags") or {}), **(v.get("tags") or {})}
    raw_ct = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate")
    ct = parse_creation_time(raw_ct)
    width, height = v.get("width"), v.get("height")
    rotation = None
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = sd["rotation"]
    if rotation in (90, -90, 270, -270) and width and height:
        width, height = height, width
    return {
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "fps": round(_parse_rate(v.get("avg_frame_rate")) or _parse_rate(v.get("r_frame_rate")) or 0, 3) or None,
        "codec": v.get("codec_name"),
        "pix_fmt": v.get("pix_fmt"),
        "audio_codec": a.get("codec_name") if a else None,
        "audio_sample_rate": int(a["sample_rate"]) if a and a.get("sample_rate") else None,
        "bit_rate": int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
        "size_bytes": int(fmt["size"]) if fmt.get("size") else os.path.getsize(path),
        "creation_time": ct.isoformat() if ct else None,
        "creation_time_raw": raw_ct,
        "format_name": fmt.get("format_name"),
        "rotation": rotation,
    }


def make_proxy(src: str, dst: str, height: int = 480, encoder: str = "libx264") -> str:
    """Buat proxy H.264 ringan agar preview dapat diputar browser (mis. sumber H.265)."""
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    tmp = dst + ".part.mp4"
    venc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28"]
    if encoder == "h264_nvenc":
        venc = ["-c:v", "h264_nvenc", "-preset", "p2", "-cq", "30"]
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-i", src, "-vf", f"scale=-2:{height}",
           *venc, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
           tmp]
    res = run_cmd(cmd)
    if res.returncode != 0 and encoder != "libx264":
        return make_proxy(src, dst, height, "libx264")
    if res.returncode != 0:
        raise RuntimeError(f"Gagal membuat proxy: {res.stderr.strip()[:300]}")
    os.replace(tmp, dst)
    return dst


def iter_frames(path: str, sample_fps: float, width: int,
                should_stop: Callable[[], bool] | None = None,
                ) -> Iterator[tuple[float, np.ndarray]]:
    """Ambil frame (waktu, BGR kecil) dengan OpenCV; fallback ke pipe FFmpeg."""
    import cv2

    cap = None
    try:
        params = []
        if hasattr(cv2, "CAP_PROP_HW_ACCELERATION"):
            params = [cv2.CAP_PROP_HW_ACCELERATION, getattr(cv2, "VIDEO_ACCELERATION_ANY", 1)]
        cap = cv2.VideoCapture(path, cv2.CAP_ANY, params) if params else cv2.VideoCapture(path)
    except Exception:  # noqa: BLE001
        cap = cv2.VideoCapture(path)
    if cap is not None and cap.isOpened():
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if fps <= 0 or fps > 240:
            fps = 30.0
        step = max(1, int(round(fps / sample_fps)))
        idx = 0
        got_any = False
        while True:
            if should_stop and should_stop():
                break
            if idx % step == 0:
                ok, frame = cap.read()
                if not ok:
                    break
                got_any = True
                h, w = frame.shape[:2]
                small = cv2.resize(frame, (width, max(2, int(h * width / w))),
                                   interpolation=cv2.INTER_AREA)
                yield idx / fps, small
            else:
                if not cap.grab():
                    break
            idx += 1
        cap.release()
        if got_any:
            return
    # Fallback FFmpeg pipe
    log.info("OpenCV tidak dapat membaca %s, memakai pipe FFmpeg", path)
    meta = probe(path)
    w = width
    h = int(round((meta["height"] or 9) * width / (meta["width"] or 16) / 2) * 2)
    cmd = [ffmpeg_exe(), "-v", "error", "-i", path, "-vf", f"fps={sample_fps},scale={w}:{h}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=_NO_WINDOW)
    frame_bytes = w * h * 3
    i = 0
    try:
        while True:
            if should_stop and should_stop():
                break
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield i / sample_fps, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            i += 1
    finally:
        proc.kill()


def thumbnail(path: str, t: float, dst: str, width: int = 320) -> str:
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    res = run_cmd([ffmpeg_exe(), "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", path,
                   "-frames:v", "1", "-vf", f"scale={width}:-2", dst], timeout=60)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[:200])
    return dst


def proxy_path_for(video_id: int) -> str:
    return str(paths.temporary / "proxies" / f"video_{video_id}.mp4")


def run_ffmpeg_progress(cmd: list[str], duration: float, on_progress: Callable[[float], None] | None = None,
                        should_cancel: Callable[[], bool] | None = None,
                        on_proc: Callable[[subprocess.Popen], None] | None = None) -> tuple[int, str]:
    """Jalankan FFmpeg sambil membaca ``-progress`` agar persentase dapat dilaporkan.

    ``cmd`` dimulai dengan path ffmpeg; argumen progres disisipkan otomatis.
    Mengembalikan (returncode, stderr-ringkas). Bila ``should_cancel`` bernilai True proses dihentikan
    dan returncode -999 dikembalikan.
    """
    import threading
    full = [cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]]
    proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
    if on_proc:
        on_proc(proc)
    err_tail: list[str] = []

    def _drain():
        for line in proc.stderr:
            err_tail.append(line)
            if len(err_tail) > 60:
                del err_tail[:20]
    th = threading.Thread(target=_drain, daemon=True)
    th.start()
    cancelled = False
    for line in proc.stdout:
        if should_cancel and should_cancel():
            cancelled = True
            proc.kill()
            break
        key, _, val = line.strip().partition("=")
        if key in ("out_time_us", "out_time_ms") and on_progress and duration > 0:
            try:
                sec = int(val) / 1_000_000
            except ValueError:
                continue
            on_progress(max(0.0, min(1.0, sec / duration)))
    proc.wait()
    th.join(timeout=2)
    if cancelled:
        return -999, "dibatalkan"
    return proc.returncode, "".join(err_tail)[-800:]

"""Render komposisi timeline Video Compiler menjadi satu video final dengan FFmpeg native.

Model komposisi (sama persis dengan preview di browser):
* Kanvas W×H dengan warna latar; durasi = panjang timeline.
* Track visual ditumpuk dari bawah ke atas mengikuti urutan track (V1 paling bawah secara default).
  Di dalam satu track, klip yang mulai belakangan berada di atas (dipakai untuk crossfade).
* Klip visual: sumber di-"contain" ke kanvas, dikalikan ``scale``, titik tengahnya di (x·W, y·H),
  opacity, serta fade in/out alpha (fade dari/ke lapisan di bawahnya — di V1 berarti dari/ke hitam).
* Teks: gambar PNG transparan seukuran kanvas yang dirender browser (font & gaya identik dengan preview).
* Audio: setiap klip memiliki volume × volume track, amplop fade in/out dengan volume awal/akhir,
  lalu ditempatkan (adelay) dan dicampur tanpa normalisasi agar level tetap seperti yang diatur.
"""
from __future__ import annotations

import base64
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from ..core.logging_setup import get_logger
from ..services import hardware_service
from ..services.video_service import ffmpeg_exe, run_cmd, run_ffmpeg_progress
from . import media as media_mod
from . import store
from .store import CompilerError

log = get_logger("compiler.render")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="compiler-render")
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:3": 4 / 3}
RESOLUTIONS = {"1080": 1080, "1440": 1440, "2160": 2160}
FPS_OPTIONS = (24, 25, 30, 50, 60)
QUALITY = {  # (preset, CRF H.264, CRF H.265)
    "high": ("slow", 18, 22),
    "very_high": ("slow", 16, 20),
    "max": ("veryslow", 14, 18),
}
AUDIO_BITRATE = "320k"


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def _reference_media(p: dict) -> dict | None:
    lib = store.all_media()
    v1 = sorted((c for c in p["clips"] if c["track"] == "V1" and c.get("media_id")), key=lambda c: c["start"])
    for c in v1 + [c for c in p["clips"] if c.get("media_id")]:
        m = lib.get(c["media_id"])
        if m and m["kind"] in ("video", "image") and m.get("width"):
            return m
    return None


def canvas(p: dict, export: dict | None = None) -> dict:
    """Ukuran kanvas & fps output dari pengaturan proyek + ekspor."""
    export = {**p.get("export", {}), **(export or {})}
    ref = _reference_media(p)
    aspect = p["settings"].get("aspect", "16:9")
    res = str(export.get("resolution", "1080"))
    if aspect == "original":
        rw, rh = (ref["width"], ref["height"]) if ref else (1920, 1080)
        ratio = rw / rh
    else:
        ratio = ASPECTS.get(aspect, 16 / 9)
        rw = rh = None
    if res == "source":
        if aspect == "original" and ref:
            w, h = rw, rh
        else:
            short = min(ref["width"], ref["height"]) if ref else 1080
            w, h = (short * ratio, short) if ratio >= 1 else (short, short / ratio)
    else:
        short = RESOLUTIONS.get(res, 1080)
        w, h = (short * ratio, short) if ratio >= 1 else (short, short / ratio)
    fps_opt = export.get("fps", "source")
    if fps_opt in ("source", None, ""):
        fps = (ref or {}).get("fps") if ref and ref["kind"] == "video" else None
        fps = fps or float(p["settings"].get("fps") or 30)
        fps = min(fps, 60.0)
    else:
        fps = float(fps_opt)
    return {"width": _even(w), "height": _even(h), "fps": round(fps, 3), "aspect": aspect}


def _fit(mw: int, mh: int, cw: int, ch: int, scale: float) -> tuple[int, int]:
    r = min(cw / mw, ch / mh) * max(0.01, scale)
    return _even(mw * r), _even(mh * r)


def _ffnum(x: float) -> str:
    return f"{x:.4f}".rstrip("0").rstrip(".") if x % 1 else str(int(x))


def _vol_expr(base: float, dur: float, fi: float, fo: float, vs: float, ve: float) -> str:
    """Amplop volume per frame audio (t relatif terhadap awal klip)."""
    parts = "1"
    if fo > 0:
        fo = min(fo, dur)
        parts = f"if(gt(t,{dur - fo:.4f}),{ve:.4f}+(1-{ve:.4f})*max(0,{dur:.4f}-t)/{fo:.4f},{parts})"
    if fi > 0:
        fi = min(fi, dur)
        parts = f"if(lt(t,{fi:.4f}),{vs:.4f}+(1-{vs:.4f})*t/{fi:.4f},{parts})"
    return f"{base:.4f}*({parts})"


def build(p: dict, export: dict, text_images: dict[str, str], workdir: Path) -> dict:
    """Susun argumen FFmpeg (input + filter_complex script). Mengembalikan dict cmd/duration/info."""
    cv = canvas(p, export)
    W, H, fps = cv["width"], cv["height"], cv["fps"]
    D = store.project_duration(p)
    if D <= 0:
        raise CompilerError("Timeline masih kosong — tambahkan minimal satu klip.")
    lib = store.all_media()
    tracks = {t["id"]: t for t in p["tracks"]}
    inputs: list[list[str]] = []
    graph: list[str] = []
    audio_labels: list[str] = []
    bg = (p["settings"].get("background") or "#000000").lstrip("#")
    graph.append(f"color=c=0x{bg}:s={W}x{H}:r={_ffnum(fps)}:d={D:.4f},format=yuv420p,setsar=1[base]")
    cur = "base"
    n_vis = 0

    # ------------------------------------------------------------------ visual (bawah -> atas)
    visual_tracks = [t for t in p["tracks"] if t["kind"] in ("video", "image", "text")]
    for t in reversed(visual_tracks):
        if t.get("hidden"):
            continue
        clips = sorted((c for c in p["clips"] if c["track"] == t["id"]), key=lambda c: c["start"])
        for c in clips:
            start, dur = float(c["start"]), float(c["duration"])
            if start >= D:
                continue
            dur = min(dur, D - start)
            idx = len(inputs)
            if t["kind"] == "text":
                data = text_images.get(c["id"])
                if not data:
                    continue
                png = workdir / f"text_{c['id']}.png"
                png.write_bytes(base64.b64decode(data.split(",", 1)[-1]))
                inputs.append(["-loop", "1", "-framerate", _ffnum(fps), "-t", f"{dur:.4f}", "-i", str(png)])
                sw, sh, ox, oy = W, H, 0, 0
            else:
                m = lib.get(c.get("media_id") or "")
                if not m:
                    raise CompilerError(f"Media untuk klip di {t['id']} tidak ada di pustaka.")
                if not Path(m["path"]).is_file():
                    raise CompilerError(f"File sumber tidak ditemukan: {m['path']}")
                if m["kind"] == "image":
                    inputs.append(["-loop", "1", "-framerate", _ffnum(fps), "-t", f"{dur:.4f}", "-i", m["path"]])
                else:
                    inputs.append(["-ss", f"{float(c.get('in', 0)):.4f}", "-t", f"{dur:.4f}", "-i", m["path"]])
                sw, sh = _fit(m["width"] or W, m["height"] or H, W, H, float(c.get("scale", 1.0)))
                ox = round(float(c.get("x", 0.5)) * W - sw / 2)
                oy = round(float(c.get("y", 0.5)) * H - sh / 2)
            chain = [f"[{idx}:v:0]setpts=PTS-STARTPTS", f"fps={_ffnum(fps)}"]
            if t["kind"] != "text":
                chain.append(f"scale={sw}:{sh}:flags=lanczos")
            chain += ["setsar=1", "format=yuva420p"]
            op = float(c.get("opacity", 1.0))
            if op < 0.999:
                chain.append(f"colorchannelmixer=aa={max(0.0, op):.4f}")
            fin = float(c.get("video_fade_in", 0) or 0)
            if c.get("transition") == "crossfade":
                fin = max(fin, float(c.get("transition_duration", 1.0) or 0))
            fout = float(c.get("video_fade_out", 0) or 0)
            if fin > 0:
                chain.append(f"fade=t=in:st=0:d={min(fin, dur):.4f}:alpha=1")
            if fout > 0:
                fo = min(fout, dur)
                chain.append(f"fade=t=out:st={dur - fo:.4f}:d={fo:.4f}:alpha=1")
            chain.append(f"setpts=PTS+{start:.4f}/TB")
            lbl = f"v{n_vis}"
            graph.append(",".join(chain) + f"[{lbl}]")
            out = f"o{n_vis}"
            graph.append(f"[{cur}][{lbl}]overlay=x={ox}:y={oy}:eof_action=pass:format=auto:"
                         f"enable='between(t,{start:.4f},{start + dur:.4f})'[{out}]")
            cur = out
            n_vis += 1
            # audio milik klip video di track video
            if t["kind"] == "video" and m.get("has_audio") and not t.get("muted"):
                lab = _audio_chain(graph, idx, c, t, dur, start)
                if lab:
                    audio_labels.append(lab)

    # ------------------------------------------------------------------ audio track
    for t in p["tracks"]:
        if t["kind"] != "audio" or t.get("muted"):
            continue
        for c in sorted((c for c in p["clips"] if c["track"] == t["id"]), key=lambda c: c["start"]):
            start, dur = float(c["start"]), float(c["duration"])
            if start >= D:
                continue
            dur = min(dur, D - start)
            m = lib.get(c.get("media_id") or "")
            if not m or not m.get("has_audio"):
                continue
            if not Path(m["path"]).is_file():
                raise CompilerError(f"File sumber tidak ditemukan: {m['path']}")
            idx = len(inputs)
            inputs.append(["-ss", f"{float(c.get('in', 0)):.4f}", "-t", f"{dur:.4f}", "-i", m["path"]])
            lab = _audio_chain(graph, idx, c, t, dur, start)
            if lab:
                audio_labels.append(lab)

    graph.append(f"[{cur}]format=yuv420p[vout]")
    graph.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{D:.4f}[asil]")
    mix_in = "".join(f"[{a}]" for a in audio_labels) + "[asil]"
    graph.append(f"{mix_in}amix=inputs={len(audio_labels) + 1}:normalize=0:dropout_transition=0:duration=longest,"
                 f"atrim=0:{D:.4f},alimiter=limit=0.98:level=0:attack=5:release=50[aout]")

    script = workdir / "graph.txt"
    script.write_text(";\n".join(graph), encoding="utf-8")
    codec = export.get("codec", "h264")
    quality = export.get("quality", "very_high")
    preset, crf264, crf265 = QUALITY.get(quality, QUALITY["very_high"])
    if codec == "hevc" and _has_encoder("libx265"):
        venc = ["-c:v", "libx265", "-preset", preset if preset != "veryslow" else "slower", "-crf", str(crf265),
                "-tag:v", "hvc1", "-x265-params", "log-level=error"]
        codec_label, crf = "H.265 (HEVC)", crf265
    else:
        venc = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf264), "-profile:v", "high"]
        codec_label, crf = "H.264 (AVC)", crf264
        codec = "h264"
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-hide_banner"]
    for a in inputs:
        cmd += a
    cmd += [*_graph_args(script), "-map", "[vout]", "-map", "[aout]",
            *venc, "-pix_fmt", "yuv420p", "-r", _ffnum(fps), "-fps_mode", "cfr",
            "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000", "-ac", "2",
            "-t", f"{D:.4f}", "-movflags", "+faststart"]
    return {"cmd": cmd, "duration": D, "width": W, "height": H, "fps": fps, "codec": codec,
            "codec_label": codec_label, "crf": crf, "preset": venc[3], "inputs": len(inputs),
            "layers": n_vis, "audio_clips": len(audio_labels)}


def _audio_chain(graph: list[str], idx: int, c: dict, t: dict, dur: float, start: float) -> str | None:
    vol = float(c.get("volume", 1.0)) * float(t.get("volume", 1.0))
    if vol <= 0:
        return None
    fi, fo = float(c.get("fade_in", 0) or 0), float(c.get("fade_out", 0) or 0)
    vs, ve = float(c.get("vol_start", 0) or 0), float(c.get("vol_end", 0) or 0)
    expr = _vol_expr(vol, dur, fi, fo, vs, ve)
    ms = int(round(start * 1000))
    lbl = f"au{idx}"
    graph.append(f"[{idx}:a:0]asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                 f"atrim=0:{dur:.4f},volume='{expr}':eval=frame,adelay={ms}|{ms}[{lbl}]")
    return lbl


def _ffmpeg_major() -> int:
    if "major" not in _VER:
        try:
            out = run_cmd([ffmpeg_exe(), "-hide_banner", "-version"], timeout=30).stdout
            m = re.search(r"ffmpeg version \D*(\d+)", out)
            _VER["major"] = int(m.group(1)) if m else 0   # build git/nightly tanpa nomor versi -> 0
        except Exception:  # noqa: BLE001
            _VER["major"] = 0
    return _VER["major"]


def _graph_args(script: Path) -> list[str]:
    """Filter graph untuk FFmpeg lintas versi.

    * ``-filter_complex_script`` dihapus di FFmpeg 8, diganti ``-/filter_complex <file>`` (FFmpeg ≥ 7).
    * Graph kecil dikirim langsung (inline) — berlaku di semua versi; graph besar memakai file agar tidak
      melewati batas panjang baris perintah Windows (~32 rb karakter).
    """
    graph = script.read_text(encoding="utf-8").replace("\n", "")
    if len(graph) < 12000:
        return ["-filter_complex", graph]
    major = _ffmpeg_major()
    if major >= 7 or major == 0:
        return ["-/filter_complex", str(script)]
    return ["-filter_complex_script", str(script)]


_VER: dict[str, int] = {}
_ENC: dict[str, bool] = {}


def _has_encoder(name: str) -> bool:
    if name not in _ENC:
        try:
            _ENC[name] = f" {name} " in run_cmd([ffmpeg_exe(), "-hide_banner", "-encoders"], timeout=30).stdout
        except Exception:  # noqa: BLE001
            _ENC[name] = False
    return _ENC[name]


# ====================================================================== perkiraan & sistem
def estimate(p: dict, export: dict) -> dict:
    cv = canvas(p, export)
    D = store.project_duration(p)
    preset, crf264, crf265 = QUALITY.get(export.get("quality", "very_high"), QUALITY["very_high"])
    crf = crf265 if export.get("codec") == "hevc" else crf264
    bpp = 0.10 * (0.86 ** (crf - 16)) * (0.6 if export.get("codec") == "hevc" else 1.0)
    vbr = cv["width"] * cv["height"] * cv["fps"] * bpp
    size = (vbr + 320_000) * D / 8
    return {**cv, "duration": round(D, 3), "estimated_size_bytes": int(size),
            "encoder": "libx265" if export.get("codec") == "hevc" else "libx264", "preset": preset, "crf": crf,
            "warnings": system_warnings(cv["width"], cv["height"], D)}


def system_info() -> dict:
    hw = hardware_service.detect()
    return {"cpu_cores": hw.get("cpu_cores"), "ram_total_gb": hw.get("ram_total_gb"),
            "ram_available_gb": hw.get("ram_available_gb"), "ffmpeg": hw.get("ffmpeg_available"),
            "hevc": _has_encoder("libx265") if hw.get("ffmpeg_available") else False}


def system_warnings(w: int, h: int, dur: float) -> list[str]:
    hw = hardware_service.detect()
    warn = []
    cores = hw.get("cpu_cores") or 0
    ram = hw.get("ram_total_gb") or 0
    pixels = w * h
    if not hw.get("ffmpeg_available"):
        warn.append("FFmpeg tidak ditemukan — render tidak dapat dijalankan.")
    if pixels >= 3840 * 2160 * 0.9:
        if ram and ram < 8:
            warn.append(f"Render 4K membutuhkan RAM ≥ 8 GB (terdeteksi {ram} GB). Pilih 1080p/1440p bila render gagal.")
        if cores and cores < 4:
            warn.append(f"CPU {cores} core: render 4K kualitas maksimum akan sangat lama.")
    elif pixels >= 2560 * 1440 * 0.9 and ram and ram < 6:
        warn.append(f"RAM {ram} GB terbatas untuk 1440p; tutup aplikasi lain selama render.")
    if cores and cores <= 2 and dur > 120:
        warn.append("Prosesor 2 core: render video panjang dengan preset lambat dapat memakan waktu lama.")
    return warn


# ====================================================================== job
def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def start_render(pid: str, export: dict | None, text_images: dict[str, str] | None) -> dict:
    p = store.get_project(pid)
    export = {**p["export"], **(export or {})}
    with _jobs_lock:
        if any(j["status"] in ("queued", "running") and j["project_id"] == pid for j in _jobs.values()):
            raise CompilerError("Proyek ini sedang dirender. Tunggu atau batalkan render sebelumnya.")
    d = store.dirs()
    jid = store.new_id("r")
    work = d["temp"] / jid
    work.mkdir(parents=True, exist_ok=True)
    plan = build(p, export, text_images or {}, work)
    safe = media_mod._SAFE.sub("_", p["name"]).strip().replace(" ", "_") or "Video"
    fname = (export.get("filename") or f"{safe}_{datetime.now():%Y%m%d_%H%M%S}").removesuffix(".mp4") + ".mp4"
    fname = media_mod._SAFE.sub("_", fname)
    out = d["renders"] / fname
    i = 1
    while out.exists():
        out = d["renders"] / f"{Path(fname).stem}_{i:02d}.mp4"
        i += 1
    job = {"id": jid, "project_id": pid, "project_name": p["name"], "status": "queued", "progress": 0.0,
           "eta_seconds": None, "elapsed_seconds": 0, "message": "Menunggu antrean render…",
           "output_path": str(out), "filename": out.name, "created_at": store.now_iso(), "error": None,
           "settings": {"width": plan["width"], "height": plan["height"], "fps": plan["fps"],
                        "codec": plan["codec_label"], "crf": plan["crf"], "preset": plan["preset"],
                        "quality": export.get("quality"), "duration": round(plan["duration"], 3)},
           "result": None, "_cancel": False, "_work": str(work), "_plan": plan}
    with _jobs_lock:
        _jobs[jid] = job
    _executor.submit(_run, jid)
    return _public(job)


def _run(jid: str) -> None:
    job = _jobs[jid]
    plan = job["_plan"]
    out = Path(job["output_path"])
    part = out.with_name(out.stem + ".rendering.mp4")
    if job["_cancel"]:
        job.update(status="cancelled", message="Render dibatalkan.")
        return
    t0 = time.time()
    job.update(status="running", message="Merender komposisi timeline…")

    def on_progress(frac: float) -> None:
        el = time.time() - t0
        job["progress"] = round(frac, 4)
        job["elapsed_seconds"] = round(el, 1)
        job["eta_seconds"] = round(el * (1 - frac) / frac, 0) if frac > 0.01 else None

    try:
        code, err = run_ffmpeg_progress(plan["cmd"] + [str(part)], plan["duration"], on_progress,
                                        should_cancel=lambda: job["_cancel"])
        if code == -999 or job["_cancel"]:
            part.unlink(missing_ok=True)
            job.update(status="cancelled", message="Render dibatalkan.", eta_seconds=None)
            return
        if code != 0:
            part.unlink(missing_ok=True)
            raise CompilerError(f"FFmpeg gagal: {err.strip()[-600:]}")
        part.replace(out)
        info = media_mod.probe_any(str(out))
        job.update(status="done", progress=1.0, eta_seconds=0, elapsed_seconds=round(time.time() - t0, 1),
                   message="Render selesai.",
                   result={"width": info["width"], "height": info["height"], "fps": info["fps"],
                           "duration": info["duration"], "size_bytes": out.stat().st_size,
                           "vcodec": info["vcodec"], "acodec": info["acodec"], "format": "MP4"})
    except Exception as e:  # noqa: BLE001
        log.exception("Render %s gagal", jid)
        job.update(status="failed", error=str(e)[:1200], message="Render gagal.", eta_seconds=None)
    finally:
        shutil.rmtree(job["_work"], ignore_errors=True)


def get_job(jid: str) -> dict:
    j = _jobs.get(jid)
    if not j:
        raise store.NotFoundError("Render tidak ditemukan.")
    return _public(j)


def list_jobs(pid: str | None = None) -> list[dict]:
    js = [_public(j) for j in _jobs.values() if pid is None or j["project_id"] == pid]
    return sorted(js, key=lambda j: j["created_at"], reverse=True)


def cancel(jid: str) -> dict:
    j = _jobs.get(jid)
    if not j:
        raise store.NotFoundError("Render tidak ditemukan.")
    if j["status"] in ("queued", "running"):
        j["_cancel"] = True
        j["message"] = "Membatalkan…"
    return _public(j)


def output_file(jid: str) -> str:
    j = _jobs.get(jid)
    if not j or j["status"] != "done" or not Path(j["output_path"]).is_file():
        raise store.NotFoundError("File hasil render belum tersedia.")
    return j["output_path"]


def wait(jid: str, timeout: float = 600) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _jobs[jid]["status"] not in ("queued", "running"):
            return _public(_jobs[jid])
        time.sleep(0.2)
    raise TimeoutError("Render belum selesai")



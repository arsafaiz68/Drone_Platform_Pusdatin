"""Penyimpanan lokal Video Compiler: pustaka media & proyek (file JSON di folder data)."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from ..core.config import paths

_lock = threading.RLock()

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mts", ".m2ts", ".ts", ".wmv", ".flv", ".3gp", ".mpg", ".mpeg"}
AUDIO_EXT = {".mp3", ".wav", ".aac", ".m4a", ".ogg", ".oga", ".opus", ".flac", ".wma", ".aiff", ".aif", ".mka"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
SVG_EXT = {".svg"}


class CompilerError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna (HTTP 400)."""


class NotFoundError(CompilerError):
    pass


def root() -> Path:
    return paths.data / "compiler"


def dirs() -> dict[str, Path]:
    r = root()
    d = {"root": r, "media": r / "media", "thumbs": r / "thumbs", "proxies": r / "proxies",
         "projects": r / "projects", "temp": r / "temp", "renders": paths.exports / "compiler"}
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    return d


def kind_of(name: str) -> str | None:
    ext = Path(name).suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    if ext in SVG_EXT:
        return "svg"
    return None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ====================================================================== media library
def _media_index() -> Path:
    return dirs()["root"] / "media_index.json"


def all_media() -> dict[str, dict]:
    with _lock:
        return _read_json(_media_index(), {})


def get_media(mid: str) -> dict:
    m = all_media().get(mid)
    if not m:
        raise NotFoundError("Media tidak ditemukan di pustaka.")
    return m


def put_media(m: dict) -> dict:
    with _lock:
        idx = all_media()
        idx[m["id"]] = m
        _write_json(_media_index(), idx)
    return m


def update_media(mid: str, **fields) -> dict | None:
    with _lock:
        idx = all_media()
        if mid not in idx:
            return None
        idx[mid].update(fields)
        _write_json(_media_index(), idx)
        return idx[mid]


def forget_media(mid: str) -> None:
    """Hapus dari pustaka. File asli pengguna TIDAK pernah dihapus; hanya salinan unggahan
    milik aplikasi (folder data/compiler/media) beserta thumbnail/proxy yang ikut dibersihkan."""
    with _lock:
        idx = all_media()
        m = idx.pop(mid, None)
        _write_json(_media_index(), idx)
    if not m:
        return
    d = dirs()
    owned = [m.get("thumb"), m.get("wave"), m.get("proxy_path")]
    if m.get("uploaded") and m.get("path") and Path(m["path"]).resolve().is_relative_to(d["media"].resolve()):
        owned.append(m["path"])
    for p in owned:
        if p:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass


def media_in_use(mid: str, except_project: str | None = None) -> bool:
    for p in list_projects(full=True):
        if p["id"] == except_project:
            continue
        if any(m.get("id") == mid for m in p.get("media", [])):
            return True
    return False


# ====================================================================== projects
DEFAULT_TRACKS = [
    {"id": "T1", "kind": "text", "name": "T1 · Teks"},
    {"id": "I1", "kind": "image", "name": "I1 · Gambar"},
    {"id": "V2", "kind": "video", "name": "V2 · Overlay"},
    {"id": "V1", "kind": "video", "name": "V1 · Video utama"},
    {"id": "A1", "kind": "audio", "name": "A1 · Audio utama"},
    {"id": "A2", "kind": "audio", "name": "A2 · Musik latar"},
]


def blank_project(name: str = "Proyek tanpa judul") -> dict:
    ts = now_iso()
    return {
        "id": new_id("p"), "name": name.strip() or "Proyek tanpa judul", "version": 1,
        "created_at": ts, "updated_at": ts,
        "settings": {"aspect": "16:9", "fps": 30, "background": "#000000", "length": None},
        "media": [],
        "tracks": [{**t, "hidden": False, "muted": False, "volume": 1.0, "locked": False} for t in DEFAULT_TRACKS],
        "clips": [],
        "export": {"resolution": "1080", "fps": "source", "codec": "h264", "quality": "very_high"},
    }


def _project_path(pid: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", pid or ""):
        raise NotFoundError("ID proyek tidak valid.")
    return dirs()["projects"] / f"{pid}.json"


def project_duration(p: dict) -> float:
    end = max((c["start"] + c["duration"] for c in p.get("clips", [])), default=0.0)
    length = (p.get("settings") or {}).get("length")
    return float(length) if length else float(end)


def normalize(p: dict) -> dict:
    """Pastikan struktur proyek lengkap (proyek lama / file impor tetap dapat dibuka)."""
    base = blank_project(p.get("name") or "Proyek")
    out = {**base, **{k: v for k, v in p.items() if k in base}}
    out["settings"] = {**base["settings"], **(p.get("settings") or {})}
    out["export"] = {**base["export"], **(p.get("export") or {})}
    have = {t["id"]: t for t in (p.get("tracks") or []) if isinstance(t, dict) and t.get("id")}
    tracks = [{**bt, **have.get(bt["id"], {})} for bt in base["tracks"]]
    order = [t["id"] for t in (p.get("tracks") or []) if isinstance(t, dict)]
    if order:
        tracks.sort(key=lambda t: order.index(t["id"]) if t["id"] in order else 99)
    out["tracks"] = tracks
    valid = {t["id"] for t in tracks}
    out["clips"] = [c for c in (p.get("clips") or []) if isinstance(c, dict) and c.get("track") in valid]
    for c in out["clips"]:
        c.setdefault("id", new_id("c"))
        c["start"] = max(0.0, float(c.get("start") or 0))
        c["duration"] = max(0.04, float(c.get("duration") or 1))
        c["in"] = max(0.0, float(c.get("in") or 0))
    return out


def save_project(p: dict) -> dict:
    p = normalize(p)
    p["updated_at"] = now_iso()
    p["duration"] = round(project_duration(p), 3)
    with _lock:
        _write_json(_project_path(p["id"]), p)
    return p


def create_project(name: str = "Proyek tanpa judul", settings: dict | None = None) -> dict:
    p = blank_project(name)
    if settings:
        p["settings"].update(settings)
    return save_project(p)


def get_project(pid: str) -> dict:
    path = _project_path(pid)
    if not path.is_file():
        raise NotFoundError("Proyek tidak ditemukan.")
    data = _read_json(path, None)
    if not isinstance(data, dict):
        raise CompilerError("File proyek rusak.")
    return normalize(data) | {"duration": round(project_duration(data), 3), "updated_at": data.get("updated_at")}


def list_projects(full: bool = False) -> list[dict]:
    out = []
    for f in dirs()["projects"].glob("*.json"):
        data = _read_json(f, None)
        if not isinstance(data, dict) or "id" not in data:
            continue
        if full:
            out.append(data)
            continue
        thumb = next((m["id"] for m in data.get("media", []) if m.get("kind") in ("video", "image")), None)
        out.append({"id": data["id"], "name": data.get("name"), "updated_at": data.get("updated_at"),
                    "created_at": data.get("created_at"), "duration": round(project_duration(data), 2),
                    "clips": len(data.get("clips", [])), "media": len(data.get("media", [])),
                    "aspect": (data.get("settings") or {}).get("aspect"), "thumb_media": thumb})
    out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return out


def rename_project(pid: str, name: str) -> dict:
    if not name.strip():
        raise CompilerError("Nama proyek tidak boleh kosong.")
    p = get_project(pid)
    p["name"] = name.strip()
    return save_project(p)


def duplicate_project(pid: str, name: str | None = None) -> dict:
    p = deepcopy(get_project(pid))
    p["id"] = new_id("p")
    p["name"] = name or f"{p['name']} (salinan)"
    p["created_at"] = now_iso()
    return save_project(p)


def delete_project(pid: str) -> None:
    p = get_project(pid)
    _project_path(pid).unlink(missing_ok=True)
    for m in p.get("media", []):
        full = all_media().get(m.get("id"))
        if full and full.get("uploaded") and not media_in_use(m["id"]):
            forget_media(m["id"])


def import_project(data: dict) -> dict:
    """Muat proyek dari file JSON (mis. hasil 'Simpan ke file'). Selalu jadi proyek baru."""
    if not isinstance(data, dict) or "clips" not in data or "tracks" not in data:
        raise CompilerError("File bukan proyek Drone Video Compiler.")
    p = normalize(deepcopy(data))
    p["id"] = new_id("p")
    p["created_at"] = now_iso()
    lib = all_media()
    missing = [m.get("name") for m in p["media"] if m.get("id") not in lib]
    p = save_project(p)
    return p | {"missing_media": missing}


def cleanup_temp(max_age_hours: float = 12) -> None:
    cutoff = time.time() - max_age_hours * 3600
    for f in dirs()["temp"].glob("*"):
        try:
            if f.stat().st_mtime < cutoff:
                if f.is_dir():
                    import shutil
                    shutil.rmtree(f, ignore_errors=True)
                else:
                    f.unlink()
        except OSError:
            pass

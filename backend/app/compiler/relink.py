"""Media hilang/berpindah folder: cek keberadaan, panggil ulang (relink) per file atau cari otomatis
di folder baru, dialog pilih file/folder bawaan Windows, dan membuka lokasi di Explorer."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import media as M
from . import store as S
from .store import CompilerError

MAX_SCAN_FILES = 60000


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def check(items: list[dict]) -> list[dict]:
    """``items`` = media proyek (id, name, path). Mengembalikan status keberadaan tiap media."""
    lib = S.all_media()
    out = []
    for it in items:
        mid = it.get("id")
        m = lib.get(mid)
        path = (m or {}).get("path") or it.get("path") or ""
        exists = bool(path) and Path(path).is_file()
        out.append({"id": mid, "name": it.get("name") or Path(path).name, "path": path, "exists": exists,
                    "in_library": m is not None, "kind": (m or it).get("kind"), "size": (m or it).get("size"),
                    "nearest_folder": nearest_existing(path)})
    return out


def nearest_existing(path: str) -> str | None:
    if not path:
        return None
    p = Path(path)
    for cand in [p, *p.parents]:
        try:
            if cand.is_dir():
                return str(cand)
        except OSError:
            continue
    return None


def relink(mid: str, new_path: str, expected_kind: str | None = None) -> dict:
    """Tautkan media ``mid`` ke file di lokasi baru. ID dipertahankan bila media ada di pustaka,
    sehingga semua klip di timeline langsung tersambung kembali."""
    p = Path((new_path or "").strip().strip('"')).expanduser()
    if not p.is_file():
        raise CompilerError(f"File tidak ditemukan: {p}")
    kind = S.kind_of(p.name)
    if kind == "svg":
        raise CompilerError("Pilih file PNG hasil konversi, bukan SVG.")
    lib = S.all_media()
    old = lib.get(mid)
    want = expected_kind or (old or {}).get("kind")
    info = M.probe_any(str(p))
    real_kind = kind
    if kind == "video" and not info["has_video"]:
        real_kind = "audio" if info["has_audio"] else None
    if want and real_kind and want != real_kind:
        raise CompilerError(f"Jenis file berbeda: media asli adalah {want}, file yang dipilih {real_kind}.")
    if old is None:
        m = M.register_file(str(p))
        return M.public(m) | {"relinked_from": mid}
    upd = {"path": str(p.resolve()), "size": p.stat().st_size, **info,
           "has_audio": bool(info["has_audio"]) and old["kind"] in ("video", "audio"), "relinked": True}
    if old["kind"] == "image":
        upd["duration"] = None
    m = S.update_media(mid, **upd)
    if not m.get("thumb") or not Path(m["thumb"]).is_file() or (m.get("has_audio") and not m.get("wave")):
        M._bg.submit(M._post_process, mid)
    warn = None
    if old.get("duration") and info.get("duration") and info["duration"] + 0.05 < old["duration"]:
        warn = (f"Durasi file baru ({info['duration']:.1f} dtk) lebih pendek dari file lama "
                f"({old['duration']:.1f} dtk); klip di bagian akhir mungkin terpotong.")
    return M.public(m) | {"relinked_from": mid, "warning": warn}


def find_in_folder(folder: str, items: list[dict], recursive: bool = True) -> dict:
    """Cari file dengan nama yang sama (tidak peka huruf besar/kecil) di folder baru.
    Bila ada beberapa kandidat, yang ukurannya sama dengan file lama diutamakan."""
    root = Path((folder or "").strip().strip('"')).expanduser()
    if not root.is_dir():
        raise CompilerError(f"Folder tidak ditemukan: {root}")
    wanted: dict[str, list[dict]] = {}
    for it in items:
        wanted.setdefault(_norm(it.get("name")), []).append(it)
    cands: dict[str, list[Path]] = {}
    n = 0
    walker = os.walk(root) if recursive else [(str(root), [], os.listdir(root))]
    for dirpath, dirnames, filenames in walker:
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "$")) and d not in ("node_modules", "__pycache__")]
        for f in filenames:
            n += 1
            key = _norm(f)
            if key in wanted:
                cands.setdefault(key, []).append(Path(dirpath) / f)
        if n > MAX_SCAN_FILES:
            break
    relinked, not_found, errors = [], [], []
    for key, its in wanted.items():
        for it in its:
            paths = cands.get(key) or []
            if not paths:
                not_found.append(it.get("id"))
                continue
            paths.sort(key=lambda q: (abs(q.stat().st_size - (it.get("size") or 0)), len(str(q))))
            try:
                relinked.append(relink(it["id"], str(paths[0]), it.get("kind")))
            except CompilerError as e:
                errors.append({"id": it.get("id"), "error": str(e)})
    return {"relinked": relinked, "not_found": not_found, "errors": errors, "scanned": n}


_FILE_PICKER = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw()
try:
    root.attributes('-topmost', True)
except Exception:
    pass
title = sys.argv[2] or 'Pilih file'
name = sys.argv[3]
ext = name.rsplit('.', 1)[-1] if '.' in name else ''
types = ([('File ' + ext.upper(), '*.' + ext)] if ext else []) + [('Semua file', '*.*')]
path = filedialog.askopenfilename(initialdir=sys.argv[1] or None, title=title, filetypes=types, initialfile=name)
root.destroy()
sys.stdout.write(path or '')
"""


def pick_file(initial: str | None, name: str = "") -> str | None:
    try:
        proc = subprocess.run([sys.executable, "-c", _FILE_PICKER, initial or "", f"Cari ulang: {name}", name],
                              capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise CompilerError("Dialog pemilihan file terlalu lama tidak dijawab.") from exc
    if proc.returncode != 0:
        raise CompilerError("Dialog file bawaan tidak tersedia — ketik/tempel path file secara manual.")
    out = proc.stdout.strip()
    return str(Path(out)) if out else None


def pick_folder(initial: str | None) -> str | None:
    from ..downloader import localfs
    try:
        return localfs.pick_folder_native(initial)
    except localfs.FolderError as e:
        raise CompilerError(str(e)) from e


def open_location(path: str) -> str:
    """Buka lokasi di Explorer. File yang ada -> folder dengan file terpilih; file hilang -> folder
    terdekat yang masih ada dari path lamanya."""
    p = Path(path or "")
    if p.is_file():
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", str(p)])
            return str(p.parent)
        target = str(p.parent)
    else:
        target = nearest_existing(path)
    if not target:
        raise CompilerError("Folder lama sudah tidak ada di komputer ini.")
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        try:
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
    return target

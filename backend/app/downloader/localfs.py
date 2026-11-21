"""Pemilihan & validasi folder tujuan di komputer lokal."""
from __future__ import annotations

import os
import shutil
import string
import subprocess
import sys
import uuid
from pathlib import Path

from .naming import sanitize_filename

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
SKIP_NAMES = {"$recycle.bin", "system volume information", "$windows.~bt", "$windows.~ws", "recovery",
              "config.msi", "__pycache__", "node_modules"}
STAGING_DIRNAME = ".byd-tmp"


class FolderError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _is_hidden(entry: os.DirEntry) -> bool:
    name = entry.name
    if name.startswith(".") or name.startswith("$") or name.lower() in SKIP_NAMES:
        return True
    try:
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
    except OSError:
        return True


def resolve_dir(path: str | os.PathLike) -> Path:
    raw = str(path or "").strip().strip('"')
    if not raw:
        raise FolderError("Path folder kosong.")
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not p.is_absolute():
        raise FolderError("Path folder harus absolut, contoh: D:\\Arsip Video")
    try:
        p = p.resolve()
    except OSError as exc:
        raise FolderError(f"Path tidak dapat dibaca: {exc}") from exc
    return p


def free_space(p: Path) -> int | None:
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


def is_writable(p: Path) -> bool:
    probe = p / f".byd-write-test-{uuid.uuid4().hex[:8]}"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def validate_output_dir(path: str, create: bool = False) -> Path:
    p = resolve_dir(path)
    if not p.exists():
        if not create:
            raise FolderError(f"Folder tidak ditemukan: {p}", 404)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FolderError(f"Folder tidak dapat dibuat: {exc}") from exc
    if not p.is_dir():
        raise FolderError(f"Bukan folder: {p}")
    if not is_writable(p):
        raise FolderError(f"Tidak ada izin menulis ke folder: {p}", 403)
    return p


def list_roots() -> list[dict]:
    roots: list[dict] = []
    home = Path.home()
    for label, sub in (("Video", "Videos"), ("Unduhan", "Downloads"), ("Desktop", "Desktop"),
                       ("Dokumen", "Documents")):
        p = home / sub
        if p.is_dir():
            roots.append({"name": label, "path": str(p), "kind": "shortcut"})
    roots.append({"name": "Folder pengguna", "path": str(home), "kind": "home"})
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                roots.append({"name": f"Drive {letter}:", "path": drive, "kind": "drive",
                              "free_bytes": free_space(Path(drive))})
    else:
        roots.append({"name": "/", "path": "/", "kind": "drive", "free_bytes": free_space(Path("/"))})
    return roots


def list_folder(path: str) -> dict:
    p = resolve_dir(path)
    if not p.exists():
        raise FolderError(f"Folder tidak ditemukan: {p}", 404)
    if not p.is_dir():
        raise FolderError(f"Bukan folder: {p}")
    children = []
    error = None
    try:
        with os.scandir(p) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False) and not _is_hidden(entry):
                        children.append({"name": entry.name, "path": str(Path(entry.path))})
                except OSError:
                    continue
    except PermissionError:
        error = "Akses ke folder ini ditolak oleh Windows."
    except OSError as exc:
        error = f"Folder tidak dapat dibaca: {exc}"
    children.sort(key=lambda c: c["name"].lower())
    parent = str(p.parent) if p.parent != p else None
    video_count = 0
    if not error:
        try:
            video_count = sum(1 for f in p.iterdir() if f.suffix.lower() in {".mp4", ".mkv", ".webm"})
        except OSError:
            pass
    return {
        "path": str(p),
        "name": p.name or str(p),
        "parent": parent,
        "children": children[:1000],
        "truncated": len(children) > 1000,
        "writable": is_writable(p) if not error else False,
        "free_bytes": free_space(p),
        "video_count": video_count,
        "error": error,
    }


def create_folder(parent: str, name: str) -> dict:
    base = validate_output_dir(parent)
    clean = sanitize_filename(name)
    target = base / clean
    if target.exists():
        raise FolderError(f"Folder '{clean}' sudah ada.", 409)
    try:
        target.mkdir()
    except OSError as exc:
        raise FolderError(f"Folder tidak dapat dibuat: {exc}") from exc
    return {"name": clean, "path": str(target)}


_PICKER_SCRIPT = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw()
try:
    root.attributes('-topmost', True)
except Exception:
    pass
path = filedialog.askdirectory(initialdir=sys.argv[1] or None, title='Pilih folder tujuan unduhan', mustexist=True)
root.destroy()
sys.stdout.write(path or '')
"""


def pick_folder_native(initial: str | None = None, timeout: int = 600) -> str | None:
    """Membuka dialog 'Pilih Folder' bawaan Windows (tkinter) di komputer ini.

    Dijalankan sebagai subprocess agar tidak mengganggu event loop server.
    Mengembalikan None jika pengguna menekan Batal.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PICKER_SCRIPT, initial or ""],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise FolderError("Dialog pemilihan folder terlalu lama tidak dijawab.", 408) from exc
    if proc.returncode != 0:
        raise FolderError(
            "Dialog folder bawaan tidak tersedia (tkinter). Gunakan penjelajah folder di aplikasi.", 501
        )
    out = proc.stdout.strip()
    return str(Path(out)) if out else None


def open_in_explorer(path: str) -> None:
    p = resolve_dir(path)
    if not p.is_dir():
        raise FolderError(f"Folder tidak ditemukan: {p}", 404)
    if os.name == "nt":
        os.startfile(str(p))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])

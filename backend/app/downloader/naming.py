"""Penamaan file otomatis: DD.MM_HH.MM_NamaLokasi_KondisiLalin.<ext>"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f%#]')
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_BASENAME_LEN = 150  # menyisakan ruang untuk path folder (batas 260 karakter Windows)


def clean_component(value: str | None, *, drop_dots: bool = True) -> str:
    """Membersihkan satu komponen nama file agar aman untuk Windows."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("*", "").replace("_", " ")
    text = ILLEGAL_CHARS_RE.sub(" ", text)
    if drop_dots:
        text = text.replace(".", " ")
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return text


def sanitize_filename(name: str) -> str:
    """Membersihkan nama file utuh (tanpa ekstensi) yang mungkin diedit manual."""
    text = unicodedata.normalize("NFKC", name or "")
    text = ILLEGAL_CHARS_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if text.upper() in WINDOWS_RESERVED or text.split(".")[0].upper() in WINDOWS_RESERVED:
        text = f"_{text}"
    if len(text) > MAX_BASENAME_LEN:
        text = text[:MAX_BASENAME_LEN].rstrip(" .")
    return text or "video"


def build_base_name(
    date_iso: str | None,
    time_hhmm: str | None,
    location: str | None,
    traffic: str | None,
) -> str:
    """Menyusun nama dasar (tanpa ekstensi).

    date_iso: 'YYYY-MM-DD'; time_hhmm: 'HH:MM'.
    """
    if date_iso and re.match(r"^\d{4}-\d{2}-\d{2}$", date_iso):
        _, mm, dd = date_iso.split("-")
        date_part = f"{dd}.{mm}"
    else:
        date_part = "00.00"
    if time_hhmm and re.match(r"^\d{1,2}[:.]\d{2}$", time_hhmm):
        hh, mi = re.split(r"[:.]", time_hhmm)
        time_part = f"{int(hh):02d}.{mi}"
    else:
        time_part = "00.00"
    loc = clean_component(location) or "TanpaLokasi"
    lalin = clean_component(traffic) or "TanpaKeterangan"
    return sanitize_filename(f"{date_part}_{time_part}_{loc}_{lalin}")


def make_unique(names: Iterable[str]) -> list[str]:
    """Menambahkan nomor urut pada nama duplikat (case-insensitive seperti Windows)."""
    result: list[str] = []
    used: set[str] = set()
    for name in names:
        candidate = name
        n = 2
        while candidate.lower() in used:
            candidate = f"{name}_{n}"
            n += 1
        used.add(candidate.lower())
        result.append(candidate)
    return result


def with_extension(base: str, ext: str | None) -> str:
    ext = (ext or "mp4").lstrip(".").lower()
    return f"{base}.{ext}"

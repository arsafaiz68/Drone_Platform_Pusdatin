"""Standar penamaan: Clipped_DD.MM_HH.MM_NamaLokasi_KondisiLalin.mp4"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from ..core.config import DEFAULT_TRAFFIC, TRAFFIC_CONDITIONS

PREFIX = "Clipped"
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}
_PATTERN = re.compile(r"^Clipped_(\d{2})\.(\d{2})_(\d{2})\.(\d{2})_([^_]+)_([^_]+)(_\d{2})?\.mp4$")


def to_token(text: str | None, fallback: str) -> str:
    """Ubah teks menjadi token PascalCase tanpa spasi/karakter tidak valid.

    "Terminal Pulo Gebang" -> "TerminalPuloGebang", "GT Cikampek" -> "GTCikampek",
    "Padat Merayap" -> "PadatMerayap", "Rest Area KM 57" -> "RestAreaKM57".
    """
    if not text:
        return fallback
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    t = _INVALID.sub(" ", t)
    t = re.sub(r"[^A-Za-z0-9]+", " ", t)
    words = [w for w in t.split() if w]
    tok = "".join(w if w.isupper() or w[0].isupper() else w[0].upper() + w[1:] for w in words)
    tok = tok[:60]
    if not tok or tok.upper() in _RESERVED:
        return fallback
    return tok


def traffic_token(cond: str | None) -> str:
    if not cond:
        cond = DEFAULT_TRAFFIC
    return to_token(cond, "TidakTeridentifikasi")


def resolve_event_datetime(event_date: str | None, event_time: str | None,
                           metadata_iso: str | None, metadata_is_utc: bool = True,
                           utc_offset_hours: float = 7, offset_seconds: float = 0.0
                           ) -> tuple[datetime | None, str]:
    """Tentukan waktu kejadian.

    Prioritas: input operator (bila diisi) > metadata waktu video > tidak diketahui.
    Waktu ekspor TIDAK pernah dipakai sebagai waktu kejadian.
    """
    if event_date and event_time:
        d = date.fromisoformat(event_date)
        hh, mm = [int(x) for x in event_time.split(":")[:2]]
        return datetime.combine(d, time(hh, mm)), "operator"
    if metadata_iso:
        dt = datetime.fromisoformat(metadata_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc if metadata_is_utc else timezone(timedelta(hours=utc_offset_hours)))
        local = dt.astimezone(timezone(timedelta(hours=utc_offset_hours))) if metadata_is_utc else dt
        local = local + timedelta(seconds=offset_seconds)
        return local.replace(tzinfo=None), "metadata"
    if event_date or event_time:
        return None, "incomplete"
    return None, "unknown"


def build_filename(event_dt: datetime | None, location: str | None, traffic: str | None,
                   suffix: str = "") -> str:
    if event_dt is None:
        raise ValueError("Tanggal dan waktu kejadian belum tersedia. Isi tanggal/waktu secara manual.")
    loc = to_token(location, "Lokasi")
    tr = traffic_token(traffic)
    name = f"{PREFIX}_{event_dt:%d.%m}_{event_dt:%H.%M}_{loc}_{tr}{suffix}.mp4"
    return name


def sanitize_custom(name: str) -> str:
    """Bersihkan nama file kustom dari operator tanpa mengubah format utama."""
    name = name.strip()
    if name.lower().endswith(".mp4"):
        name = name[:-4]
    name = _INVALID.sub("", name)
    name = re.sub(r"\s+", "", name).strip(". ")
    if not name:
        raise ValueError("Nama file kosong setelah karakter tidak valid dihapus.")
    if not name.startswith(PREFIX + "_"):
        raise ValueError("Nama file harus diawali 'Clipped_' sesuai format standar.")
    full = name + ".mp4"
    if not _PATTERN.match(full):
        raise ValueError("Format harus Clipped_DD.MM_HH.MM_NamaLokasi_KondisiLalin.mp4")
    return full


def is_valid_standard(name: str) -> bool:
    return bool(_PATTERN.match(name))


def unique_path(directory: Path, filename: str, reserved: set[str] | None = None) -> Path:
    """Hindari menimpa file: tambahkan _01, _02, ... bila nama sudah dipakai."""
    directory.mkdir(parents=True, exist_ok=True)
    reserved = {r.lower() for r in (reserved or set())}
    stem = filename[:-4] if filename.lower().endswith(".mp4") else filename
    stem = re.sub(r"_\d{2}$", "", stem) if re.search(r"_[^_]+_[^_]+_\d{2}$", stem) else stem
    cand = directory / f"{stem}.mp4"
    i = 1
    while cand.exists() or cand.name.lower() in reserved:
        cand = directory / f"{stem}_{i:02d}.mp4"
        i += 1
    return cand


def segment_filename(final_name: str, index: int, point_code: str, direction: str) -> str:
    stem = final_name[:-4] if final_name.lower().endswith(".mp4") else final_name
    d = "Pergi" if direction == "outbound" else "Kembali"
    p = "H" if point_code == "H" else f"T{point_code}"
    return f"{stem}_Seg{index:02d}_{p}{d}.mp4"


__all__ = ["to_token", "traffic_token", "build_filename", "unique_path", "sanitize_custom",
           "resolve_event_datetime", "segment_filename", "TRAFFIC_CONDITIONS", "is_valid_standard"]

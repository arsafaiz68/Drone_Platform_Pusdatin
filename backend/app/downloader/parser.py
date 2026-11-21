"""Parser laporan pemantauan (format WhatsApp) berbasis blok.

Setiap blok diawali oleh baris nama lokasi (mis. ``*Pel. Ketapang*``), diikuti
baris tanggal/waktu, metadata (Cuaca, Lalin, Rekayasa Lalin) dan URL YouTube.
Metadata hanya berlaku di dalam bloknya sendiri sehingga dua lokasi tidak
pernah tercampur.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date

from .naming import build_base_name, make_unique, sanitize_filename
from .urls import check_youtube_url, find_urls

MONTHS = {
    "jan": 1, "januari": 1, "january": 1,
    "feb": 2, "februari": 2, "pebruari": 2, "february": 2,
    "mar": 3, "maret": 3, "march": 3,
    "apr": 4, "april": 4,
    "mei": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6,
    "jul": 7, "juli": 7, "july": 7,
    "agu": 8, "agt": 8, "ags": 8, "agus": 8, "agustus": 8, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10, "oct": 10, "october": 10,
    "nov": 11, "nopember": 11, "november": 11,
    "des": 12, "desember": 12, "dec": 12, "december": 12,
}
DAY_NAMES = r"(?:senin|selasa|rabu|kamis|jum'?at|sabtu|minggu|ahad|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
TZ_RE = r"(WIB|WITA|WIT)"

TEXT_DATE_RE = re.compile(
    rf"(?:{DAY_NAMES}\s*,?\s*)?(\d{{1,2}})\s+([A-Za-z]+)\.?\s+(\d{{4}})",
    re.IGNORECASE,
)
NUM_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
TIME_RE = re.compile(rf"(?<![\d.])(\d{{1,2}})[:.](\d{{2}})(?![\d.])\s*{TZ_RE}?", re.IGNORECASE)

KV_RE = re.compile(r"^\s*([A-Za-z][A-Za-z /.]{1,40}?)\s*:\s*(.*)$")
WEATHER_RE = re.compile(r"cuaca\s*:\s*([^,\n]+)", re.IGNORECASE)
WAVE_RE = re.compile(r"tinggi\s*gelombang\s*:\s*([^\n(,]+?)\s*(?:\(([^)]*)\))?\s*(?:,|$)", re.IGNORECASE)
TRAFFIC_RE = re.compile(r"^\s*(?:lalin|lalu\s*lintas|kondisi\s*lalin)\s*:\s*(.*)$", re.IGNORECASE)
ENGINEERING_RE = re.compile(r"^\s*rekayasa\s*(?:lalin|lalu\s*lintas)\s*:\s*(.*)$", re.IGNORECASE)
HEADER_DATE_RE = re.compile(r"^\s*hari\s*/?\s*tanggal\s*:\s*(.*)$", re.IGNORECASE)
TIME_ONLY_RE = re.compile(
    r"^(?:jam|pukul|waktu|pkl\.?)?\s*:?\s*\d{1,2}[:.]\d{2}\s*(?:WIB|WITA|WIT)?$", re.IGNORECASE
)
HEADER_HOURS_RE = re.compile(r"^\s*jam\s*laporan\s*:\s*(.*)$", re.IGNORECASE)

KNOWN_KEYS = {
    "cuaca", "lalin", "lalu lintas", "kondisi lalin", "rekayasa lalin",
    "rekayasa lalu lintas", "hari/tanggal", "hari / tanggal", "tanggal",
    "jam laporan", "tinggi gelombang", "keterangan", "catatan",
}


def _strip_markup(line: str) -> str:
    """Menghapus penanda format WhatsApp (*tebal*, _miring_, ~coret~)."""
    text = line.replace("‎", "").replace("‏", "").replace("\xa0", " ")
    text = re.sub(r"(?<!\w)[*_~]+|[*_~]+(?!\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    v = _strip_markup(value).strip(" ,;")
    return v or None


def parse_date(text: str) -> date | None:
    m = TEXT_DATE_RE.search(text)
    if m:
        month = MONTHS.get(m.group(2).lower().rstrip("."))
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                return None
    m = NUM_DATE_RE.search(text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def parse_time(text: str) -> tuple[str, str | None] | None:
    for m in TIME_RE.finditer(text):
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            tz = m.group(3).upper() if m.group(3) else None
            return f"{hh:02d}:{mm:02d}", tz
    return None


def _is_datetime_line(text: str) -> bool:
    return parse_date(text) is not None and parse_time(text) is not None


@dataclass
class ParsedEntry:
    id: str
    index: int
    location: str | None = None
    date: str | None = None  # YYYY-MM-DD
    time: str | None = None  # HH:MM
    timezone: str | None = None
    weather: str | None = None
    wave_height: str | None = None
    wave_direction: str | None = None
    traffic: str | None = None
    traffic_engineering: str | None = None
    notes: list[str] = field(default_factory=list)
    url_original: str = ""
    url: str | None = None
    video_id: str | None = None
    url_valid: bool = False
    url_error: str | None = None
    filename: str = ""
    filename_manual: bool = False
    warnings: list[str] = field(default_factory=list)
    raw_block: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Block:
    location: str | None = None
    location_bold: bool = False
    date: date | None = None
    time: str | None = None
    timezone: str | None = None
    weather: str | None = None
    wave_height: str | None = None
    wave_direction: str | None = None
    traffic: str | None = None
    traffic_engineering: str | None = None
    notes: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def has_content(self) -> bool:
        return bool(
            self.location or self.date or self.time or self.weather or self.traffic
            or self.traffic_engineering or self.urls
        )


@dataclass
class ParseResult:
    entries: list[ParsedEntry]
    warnings: list[str]
    report_date: str | None
    report_hours: str | None

    def to_dict(self) -> dict:
        valid = sum(1 for e in self.entries if e.url_valid)
        return {
            "entries": [e.to_dict() for e in self.entries],
            "warnings": self.warnings,
            "report_date": self.report_date,
            "report_hours": self.report_hours,
            "summary": {
                "total_urls": len(self.entries),
                "valid_urls": valid,
                "invalid_urls": len(self.entries) - valid,
                "entries_with_warnings": sum(1 for e in self.entries if e.warnings),
            },
        }


def _apply_metadata_line(block: _Block, clean: str) -> bool:
    """Mengisi metadata dari satu baris. True jika baris dikenali sebagai metadata."""
    handled = False
    m = ENGINEERING_RE.match(clean)
    if m:
        block.traffic_engineering = _clean_value(m.group(1))
        return True
    m = TRAFFIC_RE.match(clean)
    if m:
        block.traffic = _clean_value(m.group(1))
        return True
    m = WEATHER_RE.search(clean)
    if m:
        block.weather = _clean_value(m.group(1))
        handled = True
    m = WAVE_RE.search(clean)
    if m:
        block.wave_height = _clean_value(m.group(1))
        block.wave_direction = _clean_value(m.group(2))
        handled = True
    return handled


def parse_report(text: str) -> ParseResult:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    global_warnings: list[str] = []
    report_date: date | None = None
    report_hours: str | None = None

    blocks: list[_Block] = []
    current = _Block()

    def close_current() -> None:
        nonlocal current
        if current.has_content():
            blocks.append(current)
        current = _Block()

    # Pre-compute baris non-kosong berikutnya untuk deteksi judul lokasi.
    cleaned = [_strip_markup(line) for line in lines]
    next_nonempty: list[str | None] = [None] * len(lines)
    upcoming: str | None = None
    for i in range(len(lines) - 1, -1, -1):
        next_nonempty[i] = upcoming
        if cleaned[i]:
            upcoming = cleaned[i]

    for i, raw in enumerate(lines):
        clean = cleaned[i]
        if not clean:
            continue

        # --- Header laporan (berlaku global, bukan bagian dari blok) ---
        m = HEADER_DATE_RE.match(clean)
        if m:
            report_date = parse_date(m.group(1)) or report_date
            continue
        m = HEADER_HOURS_RE.match(clean)
        if m:
            report_hours = _clean_value(m.group(1))
            continue

        # --- URL ---
        urls = find_urls(raw)
        if urls:
            current.urls.extend(urls)
            current.lines.append(raw)
            # Teks lain di baris yang sama (jarang) diabaikan.
            continue

        # --- Tanggal & waktu pengamatan ---
        if _is_datetime_line(clean) and not KV_RE.match(clean.split(",")[0]):
            if current.urls:  # tanggal baru setelah URL → blok baru tanpa judul
                close_current()
            d = parse_date(clean)
            t = parse_time(clean)
            current.date = d
            if t:
                current.time, current.timezone = t
            current.lines.append(raw)
            continue

        # --- Waktu saja (tanpa tanggal), mis. "Pukul 09:30 WIB" ---
        if TIME_ONLY_RE.match(clean) and current.time is None:
            t = parse_time(clean)
            if t:
                current.time, current.timezone = t
                current.lines.append(raw)
                continue

        # --- Metadata kunci : nilai ---
        if _apply_metadata_line(current, clean):
            current.lines.append(raw)
            continue

        kv = KV_RE.match(clean)
        if kv and kv.group(1).strip().lower() not in KNOWN_KEYS and not re.match(r"^\s*pel\.", clean, re.I):
            current.notes.append(clean)
            current.lines.append(raw)
            continue

        # --- Kandidat judul lokasi ---
        is_bold = raw.strip().startswith("*") and raw.strip().rstrip().endswith("*")
        next_is_dt = bool(next_nonempty[i] and _is_datetime_line(next_nonempty[i]))
        if current.urls or current.date or current.weather or current.traffic:
            if current.urls or is_bold or next_is_dt or current.location is None:
                close_current()
                current.location = clean
                current.location_bold = is_bold
                current.lines.append(raw)
            else:
                current.notes.append(clean)
                current.lines.append(raw)
        elif current.location is None:
            current.location = clean
            current.location_bold = is_bold
            current.lines.append(raw)
        elif is_bold or next_is_dt:
            # Judul sebelumnya tidak memiliki data apa pun (mis. judul laporan) → ganti.
            current = _Block(location=clean, location_bold=is_bold, lines=[raw])
        else:
            current.notes.append(clean)
            current.lines.append(raw)

    close_current()

    entries: list[ParsedEntry] = []
    for block in blocks:
        if not block.urls:
            if block.date or block.traffic or block.weather:
                global_warnings.append(
                    f"Blok '{block.location or 'tanpa nama'}' tidak memiliki URL YouTube dan dilewati."
                )
            continue
        for url_raw in block.urls:
            entries.append(_entry_from_block(block, url_raw, len(entries) + 1, report_date))

    if not entries:
        global_warnings.append("Tidak ada URL YouTube yang terdeteksi pada laporan.")

    apply_filenames(entries)

    # Duplikasi URL di dalam satu laporan.
    seen: dict[str, int] = {}
    for e in entries:
        if e.video_id:
            if e.video_id in seen:
                e.warnings.append(f"URL sama dengan entri No. {seen[e.video_id]}")
            else:
                seen[e.video_id] = e.index

    return ParseResult(
        entries=entries,
        warnings=global_warnings,
        report_date=report_date.isoformat() if report_date else None,
        report_hours=report_hours,
    )


def _entry_from_block(block: _Block, url_raw: str, index: int, report_date: date | None) -> ParsedEntry:
    check = check_youtube_url(url_raw)
    d = block.date or report_date
    entry = ParsedEntry(
        id=uuid.uuid4().hex[:12],
        index=index,
        location=block.location,
        date=d.isoformat() if d else None,
        time=block.time,
        timezone=block.timezone,
        weather=block.weather,
        wave_height=block.wave_height,
        wave_direction=block.wave_direction,
        traffic=block.traffic,
        traffic_engineering=block.traffic_engineering,
        notes=list(block.notes),
        url_original=url_raw,
        url=check.normalized,
        video_id=check.video_id,
        url_valid=check.valid,
        url_error=check.error,
        raw_block="\n".join(block.lines),
    )
    if len(block.urls) > 1:
        entry.warnings.append("Blok ini berisi lebih dari satu URL; metadata yang sama dipakai untuk semua URL.")
    if block.date is None and report_date is not None:
        entry.warnings.append("Tanggal pengamatan tidak ditemukan; memakai tanggal laporan.")
    entry.warnings.extend(validate_entry_fields(entry))
    return entry


def validate_entry_fields(entry: ParsedEntry) -> list[str]:
    warnings = []
    if not entry.location:
        warnings.append("Nama lokasi tidak ditemukan.")
    if not entry.date:
        warnings.append("Tanggal tidak ditemukan.")
    if not entry.time:
        warnings.append("Waktu pengamatan tidak ditemukan.")
    if not entry.traffic:
        warnings.append("Kondisi lalu lintas (Lalin) tidak ditemukan.")
    if not entry.url_valid:
        warnings.append(f"URL tidak valid: {entry.url_error}")
    return warnings


def apply_filenames(entries: list[ParsedEntry]) -> None:
    """Menghitung ulang nama file (kecuali yang diedit manual) dan memastikan unik."""
    bases = []
    for e in entries:
        if e.filename_manual and e.filename:
            bases.append(sanitize_filename(re.sub(r"\.(mp4|mkv|webm)$", "", e.filename, flags=re.I)))
        else:
            bases.append(build_base_name(e.date, e.time, e.location, e.traffic))
    for e, name in zip(entries, make_unique(bases)):
        e.filename = name

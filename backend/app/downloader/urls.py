"""Validasi & normalisasi URL YouTube (allowlist domain untuk mencegah SSRF)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Menangkap kandidat URL di dalam teks bebas (dengan atau tanpa skema).
URL_IN_TEXT_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/[^\s<>\"'*]+"
    r"|https?://[^\s<>\"'*]+",
    re.IGNORECASE,
)


@dataclass
class UrlCheck:
    original: str
    valid: bool
    normalized: str | None = None
    video_id: str | None = None
    kind: str | None = None  # watch | live | shorts | youtu.be | embed
    error: str | None = None


def find_urls(text: str) -> list[str]:
    """Mengambil seluruh kandidat URL dari sebuah teks, urut kemunculan."""
    found = []
    for m in URL_IN_TEXT_RE.finditer(text):
        # Catatan: '_' dan '-' tidak dibuang karena bisa menjadi bagian ID video.
        url = m.group(0).rstrip(".,;:)]}>~")
        found.append(url)
    return found


def check_youtube_url(raw: str) -> UrlCheck:
    original = (raw or "").strip()
    if not original:
        return UrlCheck(original, False, error="URL kosong")
    candidate = original
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", candidate):
        candidate = "https://" + candidate
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return UrlCheck(original, False, error="Format URL tidak dapat dibaca")

    if parts.scheme.lower() not in {"http", "https"}:
        return UrlCheck(original, False, error="Hanya URL http/https yang diizinkan")
    if parts.username or parts.password:
        return UrlCheck(original, False, error="URL dengan kredensial tidak diizinkan")
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in ALLOWED_HOSTS:
        return UrlCheck(original, False, error=f"Domain '{host or '-'}' bukan domain YouTube yang diizinkan")
    if parts.port not in (None, 80, 443):
        return UrlCheck(original, False, error="Port URL tidak diizinkan")

    path = parts.path or "/"
    segments = [s for s in path.split("/") if s]
    query = parse_qs(parts.query)
    video_id: str | None = None
    kind: str | None = None

    if host.endswith("youtu.be"):
        if segments:
            video_id, kind = segments[0], "youtu.be"
    elif segments[:1] == ["watch"]:
        video_id, kind = (query.get("v") or [None])[0], "watch"
    elif len(segments) >= 2 and segments[0] in {"live", "shorts", "embed", "v"}:
        video_id, kind = segments[1], segments[0]

    if not video_id:
        return UrlCheck(original, False, error="URL YouTube tidak berisi ID video (watch/live/shorts/youtu.be)")
    if not VIDEO_ID_RE.match(video_id):
        return UrlCheck(original, False, error=f"ID video '{video_id}' tidak valid")

    # Parameter pelacakan (si, feature, pp, dll.) dibuang; hanya ID yang dipertahankan.
    normalized = f"https://www.youtube.com/watch?v={video_id}"
    return UrlCheck(original, True, normalized=normalized, video_id=video_id, kind=kind)

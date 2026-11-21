"""Modul pengunduhan YouTube berbasis yt-dlp + FFmpeg.

Tidak ada bypass DRM / pembatasan akses: video privat, dihapus, dibatasi usia,
khusus member, atau siaran yang masih berlangsung akan gagal dengan pesan jelas.
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

log = logging.getLogger("app.downloader.ytdlp")


class DownloadCancelledError(Exception):
    """Pengunduhan dibatalkan oleh pengguna."""


class DownloadFailedError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class ProgressInfo:
    stage: str  # "downloading" | "processing"
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    percent: float | None = None
    speed: float | None = None  # byte/detik
    eta: float | None = None  # detik


@dataclass
class DownloadResult:
    path: Path
    size: int
    ext: str
    height: int | None = None
    title: str | None = None


ProgressCallback = Callable[[ProgressInfo], None]


class Downloader(Protocol):
    def download(
        self,
        url: str,
        out_dir: Path,
        base_name: str,
        quality: int,
        on_progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> DownloadResult: ...


def build_format_selector(quality: int) -> str:
    """Kualitas maksimal `quality`; jika tidak tersedia, ambil tertinggi di bawahnya."""
    h = int(quality)
    return (
        f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
        f"bv*[height<={h}]+ba/"
        f"b[height<={h}]/"
        f"wv*+ba/w"
    )


# Pemetaan pesan error yt-dlp → pesan bahasa Indonesia. (kata kunci, pesan, retryable)
ERROR_MAP: list[tuple[tuple[str, ...], str, bool]] = [
    (("private video",), "Video bersifat privat dan tidak dapat diakses.", False),
    (("video unavailable", "this video is not available", "no longer available"),
     "Video tidak tersedia (dihapus atau tidak dapat diakses).", False),
    (("has been removed", "account associated with this video has been terminated"),
     "Video telah dihapus dari YouTube.", False),
    (("sign in to confirm your age", "age-restricted", "inappropriate for some users"),
     "Video dibatasi usia dan memerlukan login YouTube; tidak diunduh.", False),
    (("members-only", "join this channel"), "Video khusus member channel; tidak dapat diunduh.", False),
    (("not available in your country", "geo restrict", "blocked it in your country"),
     "Video dibatasi wilayah (geo-restricted).", False),
    (("drm",), "Video dilindungi DRM dan tidak dapat diunduh.", False),
    (("this live event will begin", "premieres in", "is_upcoming"),
     "Siaran langsung belum dimulai.", False),
    (("sign in to confirm you", "not a bot"),
     "YouTube meminta verifikasi (anti-bot). Coba lagi nanti atau perbarui yt-dlp.", True),
    (("http error 429", "too many requests"), "Terlalu banyak permintaan ke YouTube (HTTP 429). Coba lagi nanti.", True),
    (("timed out", "timeout", "connection reset", "connection aborted", "temporary failure",
      "network is unreachable", "getaddrinfo", "remote end closed", "incomplete read",
      "unable to download webpage", "http error 5"),
     "Koneksi terputus atau jaringan bermasalah.", True),
    (("ffmpeg", "ffprobe"), "FFmpeg tidak ditemukan atau gagal memproses video.", False),
]


def translate_error(message: str) -> tuple[str, bool]:
    low = (message or "").lower()
    for keys, text, retryable in ERROR_MAP:
        if any(k in low for k in keys):
            return text, retryable
    short = (message or "Kesalahan tidak diketahui").replace("ERROR: ", "").strip()
    return f"Gagal mengunduh: {short[:300]}", False


def find_ffmpeg(configured: str | None = None) -> str | None:
    if configured:
        p = Path(configured)
        if p.is_dir():
            for name in ("ffmpeg.exe", "ffmpeg"):
                if (p / name).exists():
                    return str(p / name)
        elif p.exists():
            return str(p)
    return shutil.which("ffmpeg")


def yt_dlp_version() -> str | None:
    try:
        from yt_dlp.version import __version__  # type: ignore

        return __version__
    except Exception:
        return None


class YtDlpDownloader:
    def __init__(self, ffmpeg_location: str | None = None, socket_timeout: int = 30):
        self.ffmpeg_location = ffmpeg_location
        self.socket_timeout = socket_timeout

    def _base_opts(self, quality: int) -> dict:
        opts: dict = {
            "format": build_format_selector(quality),
            "merge_output_format": "mp4/mkv",  # mp4 bila kompatibel, selain itu mkv
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "windowsfilenames": True,
            "restrictfilenames": False,
            "socket_timeout": self.socket_timeout,
            "retries": 10,
            "fragment_retries": 10,
            "continuedl": True,
            "overwrites": False,
            "nopart": False,
            "logger": _YtLogger(),
        }
        ffmpeg = find_ffmpeg(self.ffmpeg_location)
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg
        return opts

    def download(
        self,
        url: str,
        out_dir: Path,
        base_name: str,
        quality: int,
        on_progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> DownloadResult:
        try:
            import yt_dlp  # type: ignore
            from yt_dlp.utils import DownloadCancelled, DownloadError  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise DownloadFailedError("yt-dlp belum terpasang. Jalankan: pip install -r requirements.txt") from exc

        if not find_ffmpeg(self.ffmpeg_location):
            raise DownloadFailedError(
                "FFmpeg tidak ditemukan. Pasang FFmpeg dan tambahkan ke PATH atau isi FFMPEG_LOCATION di .env."
            )

        out_dir.mkdir(parents=True, exist_ok=True)
        safe_base = base_name.replace("%", "%%")
        opts = self._base_opts(quality)
        opts["outtmpl"] = {"default": str(out_dir / f"{safe_base}.%(ext)s")}
        opts["paths"] = {"home": str(out_dir), "temp": str(out_dir)}

        state = {"expected_total": None, "finished_bytes": 0, "current_file": None, "last": 0.0}

        def progress_hook(d: dict) -> None:
            if cancel_event.is_set():
                raise DownloadCancelled("Dibatalkan oleh pengguna")
            status = d.get("status")
            filename = d.get("filename")
            if status == "downloading":
                if state["current_file"] != filename:
                    state["current_file"] = filename
                downloaded = d.get("downloaded_bytes") or 0
                part_total = d.get("total_bytes") or d.get("total_bytes_estimate")
                expected = state["expected_total"]
                done = state["finished_bytes"] + downloaded
                if expected:
                    total = max(expected, done)
                elif part_total:
                    total = state["finished_bytes"] + part_total
                else:
                    total = None
                percent = min(99.5, done / total * 100) if total else None
                now = time.monotonic()
                if now - state["last"] < 0.25:
                    return
                state["last"] = now
                on_progress(ProgressInfo(
                    stage="downloading",
                    downloaded_bytes=done,
                    total_bytes=int(total) if total else None,
                    percent=percent,
                    speed=d.get("speed"),
                    eta=d.get("eta"),
                ))
            elif status == "finished":
                state["finished_bytes"] += d.get("total_bytes") or d.get("downloaded_bytes") or 0
                state["current_file"] = None

        def pp_hook(d: dict) -> None:
            if cancel_event.is_set():
                raise DownloadCancelled("Dibatalkan oleh pengguna")
            if d.get("status") == "started":
                on_progress(ProgressInfo(stage="processing"))

        opts["progress_hooks"] = [progress_hook]
        opts["postprocessor_hooks"] = [pp_hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise DownloadFailedError("Informasi video tidak dapat dibaca.")
                live_status = info.get("live_status")
                if info.get("is_live") or live_status == "is_live":
                    raise DownloadFailedError(
                        "Siaran langsung masih berlangsung. Unduh setelah siaran selesai (rekaman tersedia).",
                        retryable=False,
                    )
                if live_status == "is_upcoming":
                    raise DownloadFailedError("Siaran langsung belum dimulai.", retryable=False)
                if live_status == "post_live":
                    raise DownloadFailedError(
                        "Siaran baru selesai dan rekaman masih diproses YouTube. Coba lagi nanti.",
                        retryable=True,
                    )
                requested = info.get("requested_formats") or [info]
                sizes = [f.get("filesize") or f.get("filesize_approx") for f in requested]
                if sizes and all(sizes):
                    state["expected_total"] = int(sum(sizes))
                on_progress(ProgressInfo(
                    stage="downloading", downloaded_bytes=0,
                    total_bytes=state["expected_total"], percent=0.0,
                ))
                result_info = ydl.process_ie_result(info, download=True)
        except DownloadCancelled as exc:
            raise DownloadCancelledError(str(exc)) from exc
        except DownloadFailedError:
            raise
        except DownloadError as exc:
            if cancel_event.is_set():
                raise DownloadCancelledError("Dibatalkan oleh pengguna") from exc
            msg, retryable = translate_error(str(exc))
            raise DownloadFailedError(msg, retryable) from exc
        except Exception as exc:  # error jaringan tak terduga, dsb.
            if cancel_event.is_set():
                raise DownloadCancelledError("Dibatalkan oleh pengguna") from exc
            msg, retryable = translate_error(str(exc))
            raise DownloadFailedError(msg, retryable) from exc

        path = _resolve_output_path(result_info, out_dir, base_name)
        if path is None or not path.exists():
            raise DownloadFailedError("File hasil unduhan tidak ditemukan setelah proses selesai.")
        return DownloadResult(
            path=path,
            size=path.stat().st_size,
            ext=path.suffix.lstrip(".").lower(),
            height=result_info.get("height"),
            title=result_info.get("title"),
        )


def _resolve_output_path(info: dict, out_dir: Path, base_name: str) -> Optional[Path]:
    for d in info.get("requested_downloads") or []:
        fp = d.get("filepath") or d.get("_filename")
        if fp and Path(fp).exists():
            return Path(fp)
    fp = info.get("filepath") or info.get("_filename")
    if fp and Path(fp).exists():
        return Path(fp)
    for ext in ("mp4", "mkv", "webm"):
        p = out_dir / f"{base_name}.{ext}"
        if p.exists():
            return p
    return None


class _YtLogger:
    def debug(self, msg: str) -> None:
        if not msg.startswith("[debug] "):
            log.debug(msg)

    def info(self, msg: str) -> None:
        log.debug(msg)

    def warning(self, msg: str) -> None:
        log.warning(msg)

    def error(self, msg: str) -> None:
        log.error(msg)

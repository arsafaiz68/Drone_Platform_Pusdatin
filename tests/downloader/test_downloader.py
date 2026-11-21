"""Pengujian YtDlpDownloader dengan modul yt_dlp tiruan (tanpa internet)."""
import sys
import threading
import types

import pytest

from app.downloader import ytdlp as dlmod
from app.downloader.ytdlp import (
    DownloadCancelledError,
    DownloadFailedError,
    YtDlpDownloader,
    build_format_selector,
    translate_error,
)


class _DownloadError(Exception):
    pass


class _DownloadCancelled(Exception):
    pass


def install_fake_ytdlp(monkeypatch, info: dict | None = None, error: str | None = None, write_ext="mp4"):
    created = {}

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts
            created["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            if error:
                raise _DownloadError(error)
            return dict(info or {})

        def process_ie_result(self, info, download=True):
            tmpl = self.opts["outtmpl"]["default"].replace("%%", "%")
            path = tmpl.replace("%(ext)s", write_ext)
            for hook in self.opts["progress_hooks"]:
                hook({"status": "downloading", "filename": "v", "downloaded_bytes": 500, "total_bytes": 1000})
                hook({"status": "finished", "filename": "v", "total_bytes": 1000})
            for hook in self.opts["postprocessor_hooks"]:
                hook({"status": "started", "postprocessor": "Merger"})
            with open(path, "wb") as fh:
                fh.write(b"\0" * 1500)
            return {**info, "requested_downloads": [{"filepath": path}], "height": 1080}

    utils = types.ModuleType("yt_dlp.utils")
    utils.DownloadError = _DownloadError
    utils.DownloadCancelled = _DownloadCancelled
    mod = types.ModuleType("yt_dlp")
    mod.YoutubeDL = FakeYDL
    mod.utils = utils
    monkeypatch.setitem(sys.modules, "yt_dlp", mod)
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", utils)
    monkeypatch.setattr(dlmod, "find_ffmpeg", lambda *_: "/usr/bin/ffmpeg")
    return created


def test_format_selector_caps_quality():
    sel = build_format_selector(720)
    assert "height<=720" in sel and "1080" not in sel


def test_successful_download_reports_real_progress(monkeypatch, tmp_path):
    info = {"live_status": "was_live", "requested_formats": [{"filesize": 800}, {"filesize_approx": 200}]}
    created = install_fake_ytdlp(monkeypatch, info)
    events = []
    res = YtDlpDownloader().download("https://www.youtube.com/watch?v=tqvej7BovSQ", tmp_path,
                                     "01.04_14.10_Pel Ketapang_Padat", 1080, events.append, threading.Event())
    assert res.path.name == "01.04_14.10_Pel Ketapang_Padat.mp4"
    assert res.size == 1500 and res.ext == "mp4"
    assert created["opts"]["merge_output_format"] == "mp4/mkv"
    stages = [e.stage for e in events]
    assert "downloading" in stages and "processing" in stages
    assert events[0].total_bytes == 1000  # dari estimasi format


def test_mkv_fallback_extension(monkeypatch, tmp_path):
    install_fake_ytdlp(monkeypatch, {"requested_formats": []}, write_ext="mkv")
    res = YtDlpDownloader().download("u", tmp_path, "nama", 1080, lambda p: None, threading.Event())
    assert res.ext == "mkv" and res.path.suffix == ".mkv"


def test_ongoing_live_stream_rejected(monkeypatch, tmp_path):
    install_fake_ytdlp(monkeypatch, {"is_live": True, "live_status": "is_live"})
    with pytest.raises(DownloadFailedError, match="masih berlangsung"):
        YtDlpDownloader().download("u", tmp_path, "x", 1080, lambda p: None, threading.Event())


@pytest.mark.parametrize("msg,expected,retryable", [
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "privat", False),
    ("ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader", "tidak tersedia", False),
    ("ERROR: Sign in to confirm your age", "dibatasi usia", False),
    ("ERROR: Unable to download webpage: <urlopen error timed out>", "Koneksi terputus", True),
    ("ERROR: HTTP Error 429: Too Many Requests", "429", True),
])
def test_error_translation(monkeypatch, tmp_path, msg, expected, retryable):
    install_fake_ytdlp(monkeypatch, error=msg)
    with pytest.raises(DownloadFailedError) as ei:
        YtDlpDownloader().download("u", tmp_path, "x", 1080, lambda p: None, threading.Event())
    assert expected in str(ei.value)
    assert ei.value.retryable is retryable
    assert translate_error(msg)[1] is retryable


def test_cancel_during_download(monkeypatch, tmp_path):
    install_fake_ytdlp(monkeypatch, {"requested_formats": []})
    ev = threading.Event()
    ev.set()
    with pytest.raises(DownloadCancelledError):
        YtDlpDownloader().download("u", tmp_path, "x", 1080, lambda p: None, ev)


def test_missing_ffmpeg(monkeypatch, tmp_path):
    install_fake_ytdlp(monkeypatch, {})
    monkeypatch.setattr(dlmod, "find_ffmpeg", lambda *_: None)
    with pytest.raises(DownloadFailedError, match="FFmpeg tidak ditemukan"):
        YtDlpDownloader().download("u", tmp_path, "x", 1080, lambda p: None, threading.Event())

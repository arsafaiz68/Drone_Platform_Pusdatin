"""Modul Drone Video Downloader — endpoint FastAPI di bawah ``/api/downloader``.

Sebelumnya modul ini adalah aplikasi terpisah (Batch YouTube Downloader). Sekarang
dipasang sebagai router di backend platform yang sama dengan Drone Video Trimmer,
sehingga riwayat unduhan (beserta hasil parsing laporan) dapat dibaca langsung oleh
Trimmer.
"""
from __future__ import annotations

import ipaddress
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from . import localfs
from .config import _DEFAULT_ORIGINS, Settings, settings as default_settings
from .jobs import BatchError, BatchManager
from .localfs import FolderError
from .parser import ParsedEntry, apply_filenames, parse_report, validate_entry_fields
from .urls import check_youtube_url
from .websocket import ConnectionManager
from .ytdlp import Downloader, YtDlpDownloader, find_ffmpeg, yt_dlp_version

log = logging.getLogger("app.downloader")

PREFIX = "/api/downloader"


# ---------------------------------------------------------------- schemas
class ParseRequest(BaseModel):
    text: str = Field(..., max_length=2_000_000)


class EntryIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = None
    index: Optional[int] = None
    location: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    timezone: Optional[str] = None
    weather: Optional[str] = None
    wave_height: Optional[str] = None
    wave_direction: Optional[str] = None
    traffic: Optional[str] = None
    traffic_engineering: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    url_original: Optional[str] = None
    url: Optional[str] = None
    filename: Optional[str] = None
    filename_manual: bool = False
    raw_block: Optional[str] = None


class NamingPreviewRequest(BaseModel):
    entries: list[EntryIn] = Field(..., max_length=2000)


class BatchCreate(BaseModel):
    entries: list[EntryIn] = Field(..., min_length=1, max_length=2000)
    output_dir: str = Field(..., min_length=1, max_length=1000)
    create_dir: bool = False
    quality: int = 1080
    parallel: int = 3
    conflict_behavior: str = "rename"
    report_date: Optional[str] = None
    note: Optional[str] = None


class RetryRequest(BaseModel):
    job_ids: Optional[list[str]] = None


class CreateFolderRequest(BaseModel):
    parent: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=200)


class PickRequest(BaseModel):
    initial: Optional[str] = None


class PathRequest(BaseModel):
    path: str = Field(..., min_length=1)


# ---------------------------------------------------------------- helpers
def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host in {"localhost", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def entry_from_input(e: EntryIn, index: int) -> ParsedEntry:
    raw_url = (e.url_original or e.url or "").strip()
    check = check_youtube_url(raw_url)
    entry = ParsedEntry(
        id=e.id or uuid.uuid4().hex[:12],
        index=index,
        location=(e.location or "").strip() or None,
        date=(e.date or "").strip() or None,
        time=(e.time or "").strip() or None,
        timezone=e.timezone,
        weather=e.weather,
        wave_height=e.wave_height,
        wave_direction=e.wave_direction,
        traffic=(e.traffic or "").strip() or None,
        traffic_engineering=e.traffic_engineering,
        notes=list(e.notes or []),
        url_original=raw_url,
        url=check.normalized,
        video_id=check.video_id,
        url_valid=check.valid,
        url_error=check.error,
        filename=e.filename or "",
        filename_manual=bool(e.filename_manual and e.filename),
        raw_block=e.raw_block or "",
    )
    entry.warnings = validate_entry_fields(entry)
    return entry


def _folder_error(exc: FolderError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


# ---------------------------------------------------------------- modul
class DownloaderModule:
    """Router + manajer batch unduhan. ``startup()`` dipanggil dari lifespan aplikasi."""

    def __init__(self, settings: Settings | None = None, downloader: Downloader | None = None):
        self.settings = settings = settings or default_settings
        settings.ensure_dirs()
        # asal (origin) frontend platform selalu diizinkan, termasuk port 8000 (build produksi)
        self.allowed_origins = list(dict.fromkeys([*settings.allowed_origins, *_DEFAULT_ORIGINS]))
        self.ws = ConnectionManager()
        self.jobs = BatchManager(
            downloader or YtDlpDownloader(settings.ffmpeg_location),
            settings.history_dir,
            download_retries=settings.download_retries,
            max_parallel=settings.max_parallel,
            notifier=self.ws.broadcast,
        )
        self.router = self._build_router()

    def startup(self) -> None:
        n = self.jobs.load_history()
        log.info("Modul downloader siap. %d batch riwayat dimuat. Data: %s", n, self.settings.data_dir)
        if not find_ffmpeg(self.settings.ffmpeg_location):
            log.warning("FFmpeg tidak ditemukan — penggabungan audio/video unduhan akan gagal.")

    # ------------------------------------------------------------ router
    def _build_router(self) -> APIRouter:
        settings, jobs, ws_manager, origins = self.settings, self.jobs, self.ws, self.allowed_origins

        def local_only(conn: HTTPConnection) -> None:
            if conn.scope.get("type") == "websocket":
                return  # diperiksa di handler WebSocket
            client = conn.client.host if conn.client else None
            if not _is_loopback(client):
                raise HTTPException(403, "Hanya akses lokal yang diizinkan")
            origin = conn.headers.get("origin")
            if origin and origin not in origins:
                raise HTTPException(403, f"Origin {origin} tidak diizinkan")

        r = APIRouter(prefix=PREFIX, dependencies=[Depends(local_only)])

        # ------------------------------------------------------------ umum
        @r.get("/health", tags=["Downloader"])
        def health():
            ffmpeg = find_ffmpeg(settings.ffmpeg_location)
            return {
                "status": "ok",
                "version": __version__,
                "ffmpeg": bool(ffmpeg),
                "ffmpeg_path": ffmpeg,
                "yt_dlp_version": yt_dlp_version(),
                "max_parallel": settings.max_parallel,
                "default_quality": settings.default_quality,
                "default_output_dir": str(settings.default_output_dir),
                "log_dir": str(settings.log_dir),
            }

        @r.post("/parse", tags=["Downloader"])
        def parse(req: ParseRequest):
            return parse_report(req.text).to_dict()

        @r.post("/naming/preview", tags=["Downloader"])
        def naming_preview(req: NamingPreviewRequest):
            """Validasi ulang URL & hitung ulang nama file setelah metadata diedit."""
            entries = [entry_from_input(e, i) for i, e in enumerate(req.entries, start=1)]
            apply_filenames(entries)
            return {"entries": [e.to_dict() for e in entries]}

        @r.get("/validate-url", tags=["Downloader"])
        def validate_url(url: str):
            c = check_youtube_url(url)
            return {"valid": c.valid, "normalized": c.normalized, "video_id": c.video_id, "error": c.error}

        # ------------------------------------------------------------ folder lokal
        @r.get("/local/roots", tags=["Folder lokal"])
        def local_roots():
            """Pintasan (Video, Unduhan, Desktop, …) dan daftar drive."""
            return {"roots": localfs.list_roots(), "default": str(settings.default_output_dir)}

        @r.get("/local/folders", tags=["Folder lokal"])
        def local_folders(path: str):
            try:
                return localfs.list_folder(path)
            except FolderError as exc:
                raise _folder_error(exc)

        @r.post("/local/folders", tags=["Folder lokal"], status_code=201)
        def local_create_folder(req: CreateFolderRequest):
            try:
                return localfs.create_folder(req.parent, req.name)
            except FolderError as exc:
                raise _folder_error(exc)

        @r.post("/local/validate", tags=["Folder lokal"])
        def local_validate(req: PathRequest):
            try:
                p = localfs.validate_output_dir(req.path)
                return {"valid": True, "path": str(p), "free_bytes": localfs.free_space(p)}
            except FolderError as exc:
                return {"valid": False, "path": req.path, "error": str(exc)}

        @r.post("/local/pick", tags=["Folder lokal"])
        async def local_pick(req: PickRequest):
            """Membuka dialog 'Pilih Folder' bawaan Windows di komputer ini."""
            try:
                path = await run_in_threadpool(localfs.pick_folder_native, req.initial)
            except FolderError as exc:
                raise _folder_error(exc)
            return {"path": path}

        @r.post("/local/open", tags=["Folder lokal"])
        def local_open(req: PathRequest):
            try:
                localfs.open_in_explorer(req.path)
            except FolderError as exc:
                raise _folder_error(exc)
            return {"ok": True}

        # ------------------------------------------------------------ batch
        @r.post("/batches", tags=["Downloader"], status_code=201)
        async def create_batch(req: BatchCreate):
            entries = [entry_from_input(e, i) for i, e in enumerate(req.entries, start=1)]
            apply_filenames(entries)
            try:
                batch = jobs.create_batch(
                    [e.to_dict() for e in entries],
                    output_dir=req.output_dir,
                    create_dir=req.create_dir,
                    quality=req.quality,
                    parallel=req.parallel,
                    conflict_behavior=req.conflict_behavior,
                    report_date=req.report_date,
                    note=req.note,
                )
            except BatchError as exc:
                raise HTTPException(exc.status, str(exc))
            jobs.start(batch)
            return batch.to_dict()

        @r.get("/batches", tags=["Downloader"])
        def list_batches():
            return {"batches": [b.to_dict(include_jobs=False) for b in jobs.list()]}

        @r.get("/batches/{batch_id}", tags=["Downloader"])
        def get_batch(batch_id: str):
            try:
                return jobs.get(batch_id).to_dict()
            except BatchError as exc:
                raise HTTPException(exc.status, str(exc))

        @r.post("/batches/{batch_id}/cancel", tags=["Downloader"])
        async def cancel_batch(batch_id: str):
            try:
                return (await jobs.cancel_batch(batch_id)).to_dict()
            except BatchError as exc:
                raise HTTPException(exc.status, str(exc))

        @r.post("/batches/{batch_id}/retry", tags=["Downloader"])
        async def retry_batch(batch_id: str, req: RetryRequest | None = None):
            try:
                retried = await jobs.retry(batch_id, req.job_ids if req else None)
                return {"retried": len(retried), "batch": jobs.get(batch_id).to_dict()}
            except BatchError as exc:
                raise HTTPException(exc.status, str(exc))

        @r.post("/batches/{batch_id}/jobs/{job_id}/cancel", tags=["Downloader"])
        async def cancel_job(batch_id: str, job_id: str):
            try:
                return (await jobs.cancel_job(batch_id, job_id)).to_dict()
            except BatchError as exc:
                raise HTTPException(exc.status, str(exc))

        @r.post("/batches/{batch_id}/jobs/{job_id}/retry", tags=["Downloader"])
        async def retry_job(batch_id: str, job_id: str):
            try:
                retried = await jobs.retry(batch_id, [job_id])
                return {"retried": len(retried), "batch": jobs.get(batch_id).to_dict()}
            except BatchError as exc:
                raise HTTPException(exc.status, str(exc))

        @r.websocket("/batches/{batch_id}/ws")
        async def batch_ws(websocket: WebSocket, batch_id: str):
            origin = websocket.headers.get("origin")
            client = websocket.client.host if websocket.client else None
            if (origin and origin not in origins) or not _is_loopback(client):
                await websocket.close(code=1008)
                return
            try:
                batch = jobs.get(batch_id)
            except BatchError:
                await websocket.close(code=4404)
                return
            await ws_manager.connect(batch_id, websocket)
            try:
                await websocket.send_json({"type": "snapshot", "batch": batch.to_dict()})
                while True:
                    msg = await websocket.receive_text()
                    if msg == "ping":
                        await websocket.send_text('{"type":"pong"}')
                    elif msg == "snapshot":
                        await websocket.send_json({"type": "snapshot", "batch": jobs.get(batch_id).to_dict()})
            except WebSocketDisconnect:
                pass
            finally:
                await ws_manager.disconnect(batch_id, websocket)

        return r


def create_app(settings: Settings | None = None, downloader: Downloader | None = None) -> FastAPI:
    """Aplikasi mandiri berisi modul downloader saja (dipakai pengujian)."""
    module = DownloaderModule(settings, downloader)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        module.startup()
        yield

    app = FastAPI(title="Drone Video Downloader", version=__version__, lifespan=lifespan)
    app.state.downloader = module
    app.include_router(module.router)
    return app

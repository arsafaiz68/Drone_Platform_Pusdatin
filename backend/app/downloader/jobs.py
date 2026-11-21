"""Job queue batch: unduh (yt-dlp) → simpan ke folder tujuan lokal.

Mendukung retry otomatis & manual, pembatalan, progres real-time, penanganan
konflik nama file, dan riwayat lokal (JSON).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable

from .ytdlp import (
    DownloadCancelledError,
    DownloadFailedError,
    Downloader,
    ProgressInfo,
)
from .localfs import STAGING_DIRNAME, FolderError, validate_output_dir
from .manifest import record_video
from .naming import make_unique, sanitize_filename
from .urls import check_youtube_url

log = logging.getLogger("app.downloader.jobs")

VIDEO_EXTS = ("mp4", "mkv", "webm")


class JobStatus(str, Enum):
    PENDING = "pending"            # Menunggu
    DOWNLOADING = "downloading"    # Mengunduh
    PROCESSING = "processing"      # Memproses video (gabung audio+video / simpan)
    SUCCESS = "success"            # Berhasil
    SKIPPED = "skipped"            # Dilewati (file sudah ada)
    FAILED = "failed"              # Gagal
    CANCELLED = "cancelled"        # Dibatalkan


FINAL_STATUSES = {JobStatus.SUCCESS, JobStatus.SKIPPED, JobStatus.FAILED, JobStatus.CANCELLED}
CONFLICT_BEHAVIORS = {"rename", "skip", "replace"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    batch_id: str
    index: int
    url: str
    base_name: str
    metadata: dict
    status: JobStatus = JobStatus.PENDING
    download_progress: float = 0.0
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: float | None = None
    file_size: int | None = None
    ext: str | None = None
    output_path: str | None = None
    final_filename: str | None = None
    note: str | None = None
    error: str | None = None
    attempts: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        d = dict(d)
        d["status"] = JobStatus(d.get("status", "pending"))
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Batch:
    id: str
    created_at: str
    quality: int
    parallel: int
    output_dir: str
    conflict_behavior: str
    jobs: list[Job]
    report_date: str | None = None
    note: str | None = None
    cancel_requested: bool = False

    def summary(self) -> dict:
        count = lambda st: sum(1 for j in self.jobs if j.status == st)  # noqa: E731
        s = {
            "total": len(self.jobs),
            "success": count(JobStatus.SUCCESS),
            "skipped": count(JobStatus.SKIPPED),
            "failed": count(JobStatus.FAILED),
            "cancelled": count(JobStatus.CANCELLED),
            "pending": count(JobStatus.PENDING),
            "total_bytes": sum(j.file_size or 0 for j in self.jobs if j.status == JobStatus.SUCCESS),
        }
        s["in_progress"] = s["total"] - s["success"] - s["skipped"] - s["failed"] - s["cancelled"] - s["pending"]
        s["finished"] = s["in_progress"] == 0 and s["pending"] == 0
        return s

    @property
    def status(self) -> str:
        s = self.summary()
        if not s["finished"]:
            return "running"
        done = s["success"] + s["skipped"]
        if done == s["total"]:
            return "completed"
        if s["cancelled"] and not s["failed"] and not done:
            return "cancelled"
        if done == 0:
            return "failed"
        return "partial"

    def to_dict(self, include_jobs: bool = True) -> dict:
        d = {
            "id": self.id,
            "created_at": self.created_at,
            "quality": self.quality,
            "parallel": self.parallel,
            "output_dir": self.output_dir,
            "conflict_behavior": self.conflict_behavior,
            "report_date": self.report_date,
            "note": self.note,
            "cancel_requested": self.cancel_requested,
            "status": self.status,
            "summary": self.summary(),
        }
        if include_jobs:
            d["jobs"] = [j.to_dict() for j in self.jobs]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Batch":
        return cls(
            id=d["id"],
            created_at=d["created_at"],
            quality=d.get("quality", 1080),
            parallel=d.get("parallel", 3),
            output_dir=d.get("output_dir", ""),
            conflict_behavior=d.get("conflict_behavior", "rename"),
            jobs=[Job.from_dict(j) for j in d.get("jobs", [])],
            report_date=d.get("report_date"),
            note=d.get("note"),
            cancel_requested=d.get("cancel_requested", False),
        )


Notifier = Callable[[str, dict], Awaitable[None]]


class BatchError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def find_existing(folder: Path, base: str) -> Path | None:
    for ext in VIDEO_EXTS:
        p = folder / f"{base}.{ext}"
        if p.exists():
            return p
    return None


def resolve_final_path(folder: Path, base: str, ext: str, conflict: str) -> Path:
    """Menentukan path akhir. rename → tambah _2, _3 jika nama sudah dipakai."""
    target = folder / f"{base}.{ext}"
    if conflict == "replace" or not target.exists():
        return target
    n = 2
    while True:
        candidate = folder / f"{base}_{n}.{ext}"
        if not candidate.exists():
            return candidate
        n += 1


class BatchManager:
    def __init__(
        self,
        downloader: Downloader,
        history_dir: Path,
        *,
        download_retries: int = 3,
        retry_base_delay: float = 5.0,
        max_parallel: int = 3,
        notifier: Notifier | None = None,
    ):
        self.downloader = downloader
        self.history_dir = Path(history_dir)
        self.download_retries = download_retries
        self.retry_base_delay = retry_base_delay
        self.max_parallel = max_parallel
        self.notifier = notifier
        self.batches: dict[str, Batch] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._tasks: dict[str, set[asyncio.Task]] = {}
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._save_lock: asyncio.Lock | None = None
        self._last_emit: dict[str, float] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self.history_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ util
    def _job_event(self, job: Job) -> threading.Event:
        ev = self._cancel_events.get(job.id)
        if ev is None:
            ev = threading.Event()
            self._cancel_events[job.id] = ev
        return ev

    def get(self, batch_id: str) -> Batch:
        batch = self.batches.get(batch_id)
        if batch is None:
            raise BatchError("Batch tidak ditemukan", 404)
        return batch

    def list(self) -> list[Batch]:
        return sorted(self.batches.values(), key=lambda b: b.created_at, reverse=True)

    def save(self, batch: Batch) -> None:
        path = self.history_dir / f"{batch.id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(batch.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def load_history(self) -> int:
        """Memuat riwayat dari disk. Job yang terputus karena aplikasi berhenti ditandai gagal."""
        count = 0
        for p in sorted(self.history_dir.glob("*.json")):
            try:
                batch = Batch.from_dict(json.loads(p.read_text(encoding="utf-8")))
            except Exception as exc:
                log.warning("Riwayat %s tidak dapat dibaca: %s", p.name, exc)
                continue
            changed = False
            for job in batch.jobs:
                if job.status not in FINAL_STATUSES:
                    job.status = JobStatus.FAILED
                    job.error = "Proses terhenti karena aplikasi ditutup. Klik 'Ulangi' untuk melanjutkan."
                    job.speed = job.eta = None
                    changed = True
            self.batches[batch.id] = batch
            if changed:
                self.save(batch)
            count += 1
        return count

    async def _notify(self, batch: Batch, job: Job | None = None, kind: str = "job") -> None:
        if not self.notifier:
            return
        msg: dict[str, Any] = {"type": kind, "batch_id": batch.id, "summary": batch.summary(),
                               "status": batch.status}
        if job is not None:
            msg["job"] = job.to_dict()
        try:
            await self.notifier(batch.id, msg)
        except Exception as exc:  # pragma: no cover
            log.debug("Gagal mengirim notifikasi: %s", exc)

    async def _set_status(self, batch: Batch, job: Job, status: JobStatus, **fields) -> None:
        job.status = status
        for k, v in fields.items():
            setattr(job, k, v)
        job.updated_at = _now()
        if status in FINAL_STATUSES:
            job.finished_at = job.updated_at
            job.speed = None
            job.eta = None
        self.save(batch)
        await self._notify(batch, job)
        if batch.summary()["finished"]:
            self._cleanup_staging(batch)

    def _progress_threadsafe(self, batch: Batch, job: Job, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit.get(job.id, 0) < 0.3:
            return
        self._last_emit[job.id] = now
        job.updated_at = _now()
        if self._loop is not None and self.notifier is not None:
            asyncio.run_coroutine_threadsafe(self._notify(batch, job), self._loop)

    def staging_dir(self, batch: Batch) -> Path:
        # Folder sementara di dalam folder tujuan → pemindahan akhir cukup rename (cepat, satu drive).
        return Path(batch.output_dir) / STAGING_DIRNAME / batch.id

    def _cleanup_staging(self, batch: Batch) -> None:
        """Hapus folder sementara jika tidak ada lagi sisa unduhan (file .part disimpan untuk resume)."""
        staging = self.staging_dir(batch)
        try:
            if staging.exists() and not any(staging.iterdir()):
                staging.rmdir()
            parent = staging.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass

    # ------------------------------------------------------------ public API
    def create_batch(
        self,
        entries: list[dict],
        *,
        output_dir: str,
        quality: int = 1080,
        parallel: int = 3,
        conflict_behavior: str = "rename",
        report_date: str | None = None,
        note: str | None = None,
        create_dir: bool = False,
    ) -> Batch:
        if quality not in (480, 720, 1080):
            raise BatchError("Kualitas harus 480, 720, atau 1080")
        parallel = max(1, min(int(parallel), self.max_parallel))
        if conflict_behavior not in CONFLICT_BEHAVIORS:
            raise BatchError("conflict_behavior harus rename, skip, atau replace")
        if not entries:
            raise BatchError("Tidak ada entri untuk diproses.")
        try:
            folder = validate_output_dir(output_dir, create=create_dir)
        except FolderError as exc:
            raise BatchError(f"Folder tujuan tidak valid: {exc}", exc.status) from exc

        prepared, errors = [], []
        for i, e in enumerate(entries, start=1):
            check = check_youtube_url(e.get("url") or e.get("url_original") or "")
            if not check.valid:
                errors.append(f"Entri {e.get('index', i)}: {check.error}")
                continue
            base = sanitize_filename(str(e.get("filename") or "").removesuffix(".mp4"))
            prepared.append((e, check.normalized, base))
        if errors:
            raise BatchError("URL tidak valid — " + "; ".join(errors[:10]), 422)

        batch_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        meta_keys = ["location", "date", "time", "timezone", "weather", "wave_height", "wave_direction",
                     "traffic", "traffic_engineering", "notes", "url_original", "video_id", "raw_block"]
        jobs = [
            Job(id=uuid.uuid4().hex[:12], batch_id=batch_id, index=idx, url=url, base_name=base,
                metadata={k: e.get(k) for k in meta_keys})
            for idx, ((e, url, _), base) in enumerate(
                zip(prepared, make_unique([p[2] for p in prepared])), start=1)
        ]
        batch = Batch(
            id=batch_id, created_at=_now(), quality=quality, parallel=parallel, output_dir=str(folder),
            conflict_behavior=conflict_behavior, jobs=jobs, report_date=report_date, note=note,
        )
        self.batches[batch.id] = batch
        self.save(batch)
        log.info("Batch %s dibuat: %d video, %dp, paralel %d, tujuan %s",
                 batch.id, len(jobs), quality, parallel, folder)
        return batch

    def start(self, batch: Batch, jobs: list[Job] | None = None) -> None:
        self._loop = asyncio.get_running_loop()
        batch.cancel_requested = False
        if batch.id not in self._sems:
            self._sems[batch.id] = asyncio.Semaphore(batch.parallel)
        if self._save_lock is None:
            self._save_lock = asyncio.Lock()
        tasks = self._tasks.setdefault(batch.id, set())
        for job in jobs if jobs is not None else batch.jobs:
            if job.status in FINAL_STATUSES:
                continue
            self._cancel_events[job.id] = threading.Event()
            t = asyncio.create_task(self._run_job(batch, job))
            tasks.add(t)
            t.add_done_callback(tasks.discard)

    async def wait(self, batch_id: str) -> None:
        """Menunggu semua task batch selesai (dipakai pada pengujian)."""
        while self._tasks.get(batch_id):
            await asyncio.gather(*list(self._tasks[batch_id]), return_exceptions=True)

    async def cancel_batch(self, batch_id: str) -> Batch:
        batch = self.get(batch_id)
        batch.cancel_requested = True
        for job in batch.jobs:
            if job.status in FINAL_STATUSES:
                continue
            self._job_event(job).set()
            if job.status == JobStatus.PENDING:
                await self._set_status(batch, job, JobStatus.CANCELLED, error="Dibatalkan oleh pengguna")
        self.save(batch)
        await self._notify(batch, kind="batch")
        log.info("Batch %s dibatalkan", batch_id)
        return batch

    async def cancel_job(self, batch_id: str, job_id: str) -> Job:
        batch = self.get(batch_id)
        job = self._find_job(batch, job_id)
        if job.status not in FINAL_STATUSES:
            self._job_event(job).set()
            if job.status == JobStatus.PENDING:
                await self._set_status(batch, job, JobStatus.CANCELLED, error="Dibatalkan oleh pengguna")
        return job

    async def retry(self, batch_id: str, job_ids: list[str] | None = None) -> list[Job]:
        batch = self.get(batch_id)
        try:
            validate_output_dir(batch.output_dir)
        except FolderError as exc:
            raise BatchError(f"Folder tujuan tidak tersedia: {exc}", exc.status) from exc
        selected = [j for j in batch.jobs if j.status in (JobStatus.FAILED, JobStatus.CANCELLED)
                    and (job_ids is None or j.id in job_ids)]
        for job in selected:
            job.status = JobStatus.PENDING
            job.error = None
            job.note = None
            job.finished_at = None
            job.download_progress = 0.0
            job.updated_at = _now()
        self.save(batch)
        self.start(batch, selected)
        await self._notify(batch, kind="batch")
        log.info("Batch %s: mengulang %d pekerjaan", batch_id, len(selected))
        return selected

    @staticmethod
    def _find_job(batch: Batch, job_id: str) -> Job:
        for j in batch.jobs:
            if j.id == job_id:
                return j
        raise BatchError("Pekerjaan tidak ditemukan", 404)

    # -------------------------------------------------------------- worker
    async def _run_job(self, batch: Batch, job: Job) -> None:
        try:
            await self._process(batch, job, self._job_event(job))
        except Exception as exc:  # pengaman: error satu job tidak menghentikan batch
            log.exception("[%s] #%d error tak terduga", batch.id, job.index)
            await self._set_status(batch, job, JobStatus.FAILED, error=f"Kesalahan internal: {exc}")

    async def _cancellable_sleep(self, seconds: float, ev: threading.Event) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if ev.is_set():
                return False
            await asyncio.sleep(min(0.25, max(0.0, end - time.monotonic())))
        return not ev.is_set()

    async def _process(self, batch: Batch, job: Job, cancel_ev: threading.Event) -> None:
        folder = Path(batch.output_dir)
        async with self._sems[batch.id]:
            if cancel_ev.is_set() or job.status == JobStatus.CANCELLED:
                if job.status != JobStatus.CANCELLED:
                    await self._set_status(batch, job, JobStatus.CANCELLED, error="Dibatalkan oleh pengguna")
                return

            if batch.conflict_behavior == "skip":
                existing = find_existing(folder, job.base_name)
                if existing is not None:
                    await self._set_status(
                        batch, job, JobStatus.SKIPPED, output_path=str(existing), final_filename=existing.name,
                        file_size=existing.stat().st_size, note="File dengan nama sama sudah ada; dilewati.",
                        error=None,
                    )
                    record_video(existing, job.metadata, batch_id=batch.id, job_id=job.id,
                                 report_date=batch.report_date)
                    log.info("[%s] #%d dilewati, sudah ada: %s", batch.id, job.index, existing.name)
                    return

            staging = self.staging_dir(batch)
            max_attempts = self.download_retries + 1
            for attempt in range(1, max_attempts + 1):
                job.attempts += 1
                job.started_at = job.started_at or _now()
                await self._set_status(batch, job, JobStatus.DOWNLOADING, error=None)

                def on_progress(p: ProgressInfo, _job=job) -> None:
                    if p.stage == "processing":
                        if _job.status != JobStatus.PROCESSING:
                            _job.status = JobStatus.PROCESSING
                            _job.speed = _job.eta = None
                            self._progress_threadsafe(batch, _job, force=True)
                        return
                    _job.status = JobStatus.DOWNLOADING
                    if p.percent is not None:
                        _job.download_progress = round(p.percent, 1)
                    _job.downloaded_bytes = p.downloaded_bytes
                    _job.total_bytes = p.total_bytes
                    _job.speed = p.speed
                    _job.eta = p.eta
                    self._progress_threadsafe(batch, _job)

                log.info("[%s] #%d mulai unduh (percobaan %d): %s", batch.id, job.index, attempt, job.url)
                try:
                    result = await asyncio.to_thread(
                        self.downloader.download, job.url, staging, job.base_name, batch.quality,
                        on_progress, cancel_ev,
                    )
                except DownloadCancelledError:
                    await self._set_status(batch, job, JobStatus.CANCELLED, error="Dibatalkan oleh pengguna")
                    log.info("[%s] #%d dibatalkan", batch.id, job.index)
                    return
                except DownloadFailedError as exc:
                    log.warning("[%s] #%d gagal unduh: %s", batch.id, job.index, exc)
                    if exc.retryable and attempt < max_attempts:
                        job.error = f"{exc} — mencoba lagi ({attempt}/{self.download_retries})"
                        job.status = JobStatus.PENDING
                        self.save(batch)
                        await self._notify(batch, job)
                        if not await self._cancellable_sleep(self.retry_base_delay * attempt, cancel_ev):
                            await self._set_status(batch, job, JobStatus.CANCELLED,
                                                   error="Dibatalkan oleh pengguna")
                            return
                        continue
                    await self._set_status(batch, job, JobStatus.FAILED, error=str(exc))
                    return

                # Pindahkan dari folder sementara ke folder tujuan dengan aturan konflik nama.
                job.status = JobStatus.PROCESSING
                assert self._save_lock is not None
                async with self._save_lock:
                    final = resolve_final_path(folder, job.base_name, result.ext, batch.conflict_behavior)
                    replaced = final.exists()
                    try:
                        os.replace(result.path, final)
                    except OSError:
                        try:
                            shutil.move(str(result.path), str(final))
                        except OSError as exc:
                            await self._set_status(
                                batch, job, JobStatus.FAILED,
                                error=f"Video terunduh tetapi gagal disimpan ke folder tujuan: {exc}",
                            )
                            return
                note = None
                if final.stem != job.base_name:
                    note = f"Nama sudah dipakai, disimpan sebagai {final.name}"
                elif replaced:
                    note = "File lama dengan nama sama ditimpa."
                size = final.stat().st_size
                await self._set_status(
                    batch, job, JobStatus.SUCCESS, output_path=str(final), final_filename=final.name,
                    ext=result.ext, file_size=size, download_progress=100.0, downloaded_bytes=size,
                    total_bytes=size, note=note, error=None,
                )
                record_video(final, job.metadata, batch_id=batch.id, job_id=job.id, report_date=batch.report_date)
                log.info("[%s] #%d tersimpan: %s (%d byte)", batch.id, job.index, final, size)
                return

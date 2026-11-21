"""Titik masuk Drone Video Platform (FastAPI).

Satu backend untuk dua modul:
  * Drone Video Downloader  -> /api/downloader/...   (laporan WhatsApp -> unduh video YouTube)
  * Drone Video Trimmer     -> /api/...              (analisis AI & pemotongan video)
  * Drone Video Compiler    -> /api/compiler/...     (editor multi-track & render FFmpeg)
  * Integrasi               -> /api/integration/...  (hasil unduhan langsung dibaca Trimmer)
Frontend (menu utama, /downloader/, /trimmer/) disajikan dari frontend/dist.

Jalankan:  python -m app.main            (server di http://127.0.0.1:8000)
           python -m app.main --init-db  (hanya menyiapkan database & direktori)
"""
from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import routes_batch, routes_core, routes_final, routes_integration
from .compiler import router as compiler_router
from .core.config import APP_NAME, APP_VERSION, FRONTEND_DIST, paths
from .core.logging_setup import get_logger, setup_logging
from .database import db
from .downloader.router import DownloaderModule
from .services import batch_service, export_service, hardware_service
from .services.timeline_service import NotFound, ValidationError
from .workers import batch_worker

log = get_logger("main")

downloader_module = DownloaderModule()


def bootstrap() -> dict:
    setup_logging()
    paths.ensure()
    db.init_db()
    recovered = batch_service.recover_on_startup()
    hardware_service.detect(force=True)
    try:
        from .compiler import store as compiler_store
        compiler_store.dirs()
        compiler_store.cleanup_temp()
    except OSError:
        pass
    return recovered


@asynccontextmanager
async def lifespan(app: FastAPI):
    rec = bootstrap()
    app.state.recovered = rec
    downloader_module.startup()
    if os.environ.get("ADT_DISABLE_WORKER") != "1":
        batch_worker.start()
    log.info("%s %s siap. Data: %s", APP_NAME, APP_VERSION, paths.data)
    yield
    batch_worker.stop(wait=False)


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
app.state.downloader = downloader_module
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(NotFound)
async def _nf(_: Request, exc: NotFound):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(ValidationError)
async def _ve(_: Request, exc: ValidationError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(export_service.ExportError)
async def _ee(_: Request, exc: Exception):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(ValueError)
async def _vae(_: Request, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


app.include_router(downloader_module.router)      # harus sebelum router Trimmer (/api/...)
app.include_router(routes_integration.router)
app.include_router(compiler_router.router)      # Drone Video Compiler (/api/compiler/...)
app.include_router(routes_core.router)
app.include_router(routes_batch.router)
app.include_router(routes_final.router)


# ---------------------------------------------------------------- frontend (hasil build Vite)
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


# Halaman HTML tidak boleh di-cache browser: setelah build ulang, nama file aset (hash) berubah.
_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Endpoint tidak ditemukan"}, status_code=404)
    root = FRONTEND_DIST.resolve()
    candidate = (FRONTEND_DIST / full_path).resolve()
    if full_path and candidate.is_relative_to(root):
        if candidate.is_file():
            return FileResponse(str(candidate), headers=_NO_CACHE if candidate.suffix == ".html" else None)
        # halaman modul: /downloader/ dan /trimmer/ (build multi-halaman Vite)
        if (candidate / "index.html").is_file():
            if not full_path.endswith("/"):
                return RedirectResponse(f"/{full_path}/")
            return FileResponse(str(candidate / "index.html"), headers=_NO_CACHE)
        first = full_path.split("/", 1)[0]
        if (root / first / "index.html").is_file():
            return FileResponse(str(root / first / "index.html"), headers=_NO_CACHE)
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(str(index), headers=_NO_CACHE)
    return JSONResponse({"detail": "Frontend belum di-build. Jalankan start.bat atau 'npm run build' di folder frontend."},
                        status_code=503)


def main():
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("ADT_PORT", "8000")))
    ap.add_argument("--init-db", action="store_true", help="Siapkan database dan direktori lalu keluar")
    args = ap.parse_args()
    if args.init_db:
        bootstrap()
        print(f"Database siap: {paths.database}")
        return
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

"""Streaming file video dengan dukungan HTTP Range (untuk seek di video player)."""
from __future__ import annotations

import mimetypes
import os

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

CHUNK = 1024 * 1024


def stream_file(path: str, request: Request, download_name: str | None = None):
    if not path or not os.path.isfile(path):
        raise HTTPException(404, "File tidak ditemukan")
    size = os.path.getsize(path)
    ctype = mimetypes.guess_type(path)[0] or "video/mp4"
    if download_name:
        return FileResponse(path, media_type=ctype, filename=download_name)
    rng = request.headers.get("range")
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-cache"}
    if not rng or not rng.startswith("bytes="):
        headers["Content-Length"] = str(size)
        return StreamingResponse(_iter(path, 0, size - 1), media_type=ctype, headers=headers)
    try:
        a, b = rng[6:].split(",")[0].split("-")
        start = int(a) if a else max(0, size - int(b))
        end = int(b) if (a and b) else size - 1
    except ValueError:
        raise HTTPException(416, "Range tidak valid")
    if start >= size:
        raise HTTPException(416, "Range di luar ukuran file")
    end = min(end, size - 1)
    headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
    return StreamingResponse(_iter(path, start, end), status_code=206, media_type=ctype, headers=headers)


def _iter(path: str, start: int, end: int):
    with open(path, "rb") as fh:
        fh.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = fh.read(min(CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data

"""Endpoint HTTP Drone Video Compiler (prefix /api/compiler)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..api.media import stream_file
from . import media as M
from . import relink as RL
from . import render as R
from . import store as S

router = APIRouter(prefix="/api/compiler", tags=["compiler"])


def _err(e: Exception):
    code = 404 if isinstance(e, S.NotFoundError) else 400
    raise HTTPException(code, str(e))


class PathsBody(BaseModel):
    paths: list[str] = Field(default_factory=list)


class NewProject(BaseModel):
    name: str = "Proyek tanpa judul"
    settings: dict | None = None


class RenameBody(BaseModel):
    name: str


class RenderBody(BaseModel):
    export: dict | None = None
    text_images: dict[str, str] = Field(default_factory=dict)


class IdsBody(BaseModel):
    ids: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ sistem
@router.get("/system")
def system():
    return R.system_info() | {"resolutions": list(R.RESOLUTIONS), "fps": list(R.FPS_OPTIONS),
                              "aspects": [*R.ASPECTS, "original"], "qualities": {
                                  k: {"preset": v[0], "crf_h264": v[1], "crf_h265": v[2]} for k, v in R.QUALITY.items()}}


# ------------------------------------------------------------------ media
@router.get("/media")
def media_list():
    return [M.public(m) for m in S.all_media().values()]


@router.post("/media/upload")
async def media_upload(request: Request, filename: str):
    """Unggah file dari browser ke backend LOKAL (127.0.0.1) — ditulis ke disk per potongan,
    tidak pernah dimuat utuh ke RAM dan tidak dikirim ke server luar."""
    kind = S.kind_of(filename)
    if kind is None or kind == "svg":
        raise HTTPException(400, f"Tipe file tidak didukung: {Path(filename).suffix or filename}")
    dst = M.upload_target(filename)
    size = 0
    try:
        with open(dst, "wb") as fh:
            async for chunk in request.stream():
                fh.write(chunk)
                size += len(chunk)
        if size == 0:
            raise S.CompilerError("File kosong.")
        m = await asyncio.to_thread(M.register_file, str(dst), Path(filename).name, True)
        return M.public(m)
    except S.CompilerError as e:
        dst.unlink(missing_ok=True)
        _err(e)


@router.post("/media/register")
def media_register(body: PathsBody):
    res = M.register_paths(body.paths)
    return {"added": [M.public(m) for m in res["added"]], "errors": res["errors"]}


@router.post("/media/status")
def media_status(body: IdsBody):
    lib = S.all_media()
    return {i: M.public(lib[i]) for i in body.ids if i in lib}


@router.get("/media/{mid}")
def media_get(mid: str):
    try:
        return M.public(S.get_media(mid))
    except S.CompilerError as e:
        _err(e)


@router.get("/media/{mid}/file")
def media_file(mid: str, request: Request, proxy: int = 1):
    try:
        m = S.get_media(mid)
    except S.CompilerError as e:
        _err(e)
    path = m["proxy_path"] if proxy and m.get("proxy") == "ready" and m.get("proxy_path") else m["path"]
    if m["kind"] == "image":
        return FileResponse(path, headers={"Cache-Control": "max-age=3600"})
    return stream_file(path, request)


@router.get("/media/{mid}/thumb")
def media_thumb(mid: str):
    m = S.all_media().get(mid)
    if not m or not m.get("thumb") or not Path(m["thumb"]).is_file():
        raise HTTPException(404, "Thumbnail belum tersedia")
    return FileResponse(m["thumb"], headers={"Cache-Control": "max-age=3600"})


@router.get("/media/{mid}/wave")
def media_wave(mid: str):
    m = S.all_media().get(mid)
    if not m or not m.get("wave") or not Path(m["wave"]).is_file():
        raise HTTPException(404, "Waveform belum tersedia")
    return FileResponse(m["wave"], headers={"Cache-Control": "max-age=3600"})


@router.delete("/media/{mid}")
def media_forget(mid: str, project_id: str | None = None):
    """Lepas media dari pustaka bila tidak dipakai proyek lain. File asli pengguna tidak dihapus."""
    if S.media_in_use(mid, except_project=project_id):
        return {"removed": False, "reason": "masih dipakai proyek lain"}
    S.forget_media(mid)
    return {"removed": True}


class CheckBody(BaseModel):
    media: list[dict] = Field(default_factory=list)


class RelinkBody(BaseModel):
    media_id: str
    path: str
    kind: str | None = None


class FindBody(BaseModel):
    folder: str
    items: list[dict] = Field(default_factory=list)
    recursive: bool = True


class PickBody(BaseModel):
    initial: str | None = None
    name: str = ""


class PathBody(BaseModel):
    path: str


@router.post("/media/check")
def media_check(body: CheckBody):
    """Cek media proyek yang hilang/berpindah folder."""
    return RL.check(body.media)


@router.post("/media/relink")
def media_relink(body: RelinkBody):
    try:
        return RL.relink(body.media_id, body.path, body.kind)
    except S.CompilerError as e:
        _err(e)


@router.post("/media/find")
def media_find(body: FindBody):
    try:
        return RL.find_in_folder(body.folder, body.items, body.recursive)
    except S.CompilerError as e:
        _err(e)


@router.post("/pick-file")
def pick_file(body: PickBody):
    try:
        return {"path": RL.pick_file(body.initial, body.name)}
    except S.CompilerError as e:
        _err(e)


@router.post("/pick-folder")
def pick_folder(body: PickBody):
    try:
        return {"path": RL.pick_folder(body.initial)}
    except S.CompilerError as e:
        _err(e)


@router.post("/open-location")
def open_location(body: PathBody):
    try:
        return {"opened": RL.open_location(body.path)}
    except S.CompilerError as e:
        _err(e)


# ------------------------------------------------------------------ proyek
@router.get("/projects")
def projects():
    return S.list_projects()


@router.post("/projects")
def project_new(body: NewProject):
    return S.create_project(body.name, body.settings)


@router.post("/projects/import")
def project_import(body: dict):
    try:
        return S.import_project(body)
    except S.CompilerError as e:
        _err(e)


@router.get("/projects/{pid}")
def project_get(pid: str):
    try:
        return S.get_project(pid)
    except S.CompilerError as e:
        _err(e)


@router.put("/projects/{pid}")
def project_save(pid: str, body: dict):
    try:
        S.get_project(pid)
        body["id"] = pid
        return S.save_project(body)
    except S.CompilerError as e:
        _err(e)


@router.post("/projects/{pid}/rename")
def project_rename(pid: str, body: RenameBody):
    try:
        return S.rename_project(pid, body.name)
    except S.CompilerError as e:
        _err(e)


@router.post("/projects/{pid}/duplicate")
def project_duplicate(pid: str, body: RenameBody | None = None):
    try:
        return S.duplicate_project(pid, body.name if body else None)
    except S.CompilerError as e:
        _err(e)


@router.delete("/projects/{pid}")
def project_delete(pid: str):
    try:
        S.delete_project(pid)
        return {"deleted": pid}
    except S.CompilerError as e:
        _err(e)


# ------------------------------------------------------------------ render
@router.post("/projects/{pid}/estimate")
def project_estimate(pid: str, body: RenderBody | None = None):
    try:
        p = S.get_project(pid)
        return R.estimate(p, {**p["export"], **((body.export if body else None) or {})})
    except S.CompilerError as e:
        _err(e)


@router.post("/projects/{pid}/render")
def project_render(pid: str, body: RenderBody):
    try:
        return R.start_render(pid, body.export, body.text_images)
    except S.CompilerError as e:
        _err(e)


@router.get("/projects/{pid}/renders")
def project_renders(pid: str):
    return R.list_jobs(pid)


@router.get("/renders/{jid}")
def render_get(jid: str):
    try:
        return R.get_job(jid)
    except S.CompilerError as e:
        _err(e)


@router.post("/renders/{jid}/cancel")
def render_cancel(jid: str):
    try:
        return R.cancel(jid)
    except S.CompilerError as e:
        _err(e)


@router.get("/renders/{jid}/download")
def render_download(jid: str):
    try:
        path = R.output_file(jid)
    except S.CompilerError as e:
        _err(e)
    return FileResponse(path, media_type="video/mp4", filename=Path(path).name)


@router.get("/renders/{jid}/stream")
def render_stream(jid: str, request: Request):
    try:
        path = R.output_file(jid)
    except S.CompilerError as e:
        _err(e)
    return stream_file(path, request)



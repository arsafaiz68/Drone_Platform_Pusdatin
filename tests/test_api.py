"""Uji end-to-end HTTP: menjalankan server FastAPI sungguhan lalu memanggil endpoint."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

requests = pytest.importorskip("requests")
ROOT = Path(__file__).resolve().parents[1]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    try:
        import fastapi  # noqa: F401
    except ImportError:
        if not os.environ.get("ADT_TEST_PYTHONPATH"):
            pytest.skip("FastAPI belum terpasang")
    port = _free_port()
    env = dict(os.environ, ADT_DATA_DIR=str(tmp_path_factory.mktemp("apidata")))
    if os.environ.get("ADT_TEST_PYTHONPATH"):
        env["PYTHONPATH"] = os.environ["ADT_TEST_PYTHONPATH"]
    proc = subprocess.Popen([sys.executable, "-m", "app.main", "--port", str(port)], cwd=ROOT / "backend", env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/api"
    for _ in range(100):
        try:
            if requests.get(base + "/health", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail(proc.stdout.read().decode(errors="replace"))
    yield base
    proc.terminate()
    proc.wait(10)


def ok(r):
    assert r.status_code < 300, r.text
    return r.json()


def test_full_flow(server, assets):
    s = server
    assert ok(requests.get(s + "/health"))["status"] == "ok"
    assert len(ok(requests.get(s + "/templates"))) == 6
    hw = ok(requests.get(s + "/hardware"))
    assert hw["mode"] in ("cpu", "cuda")
    assert "values" in ok(requests.get(s + "/settings"))

    p = ok(requests.post(s + "/projects", json={"name": "API", "template_code": "terminal",
                                               "location_name": "Terminal Pulogebang"}))
    assert any(x["id"] == p["id"] for x in ok(requests.get(s + "/projects")))
    b = ok(requests.post(s + "/batches", json={"project_id": p["id"], "final_duration": 30,
                                              "trip_mode": "round_trip", "concurrency": 2}))
    bid = b["id"]
    # validasi input
    assert requests.post(s + "/batches", json={"project_id": p["id"], "final_duration": 90}).status_code == 422

    # 25 file sekaligus ditolak
    files = [("files", (f"v{i}.mp4", b"x", "video/mp4")) for i in range(25)]
    r = requests.post(f"{s}/batches/{bid}/videos", files=files)
    assert r.status_code == 400 and "24" in r.json()["detail"]
    assert ok(requests.get(f"{s}/batches/{bid}"))["stats"]["total"] == 0

    with open(assets["roundtrip"], "rb") as fh:
        vids = ok(requests.post(f"{s}/batches/{bid}/videos", files=[("files", ("DJI_0001.MP4", fh, "video/mp4"))]))
    vid = vids[0]["id"]
    ok(requests.post(f"{s}/batches/{bid}/videos/paths", json={"paths": [str(assets["short720"])]}))

    ok(requests.post(f"{s}/batches/{bid}/start"))
    for _ in range(300):
        st = ok(requests.get(f"{s}/batches/{bid}"))
        if st["stats"]["completed"] + st["stats"]["failed"] == 2:
            break
        time.sleep(0.3)
    assert st["stats"]["completed"] == 2, st
    items = ok(requests.get(f"{s}/batches/{bid}/items"))
    assert all(i["status_label"] == "Menunggu review" for i in items)

    cands = ok(requests.get(f"{s}/videos/{vid}/candidates"))
    assert cands
    c = cands[0]
    upd = ok(requests.patch(f"{s}/candidates/{c['id']}", json={"start": c["start"] + 0.2}))
    assert upd["edited"] == 1
    ok(requests.post(f"{s}/candidates/{c['id']}/reset"))

    # streaming dengan HTTP Range
    r = requests.get(f"{s}/videos/{vid}/stream", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100

    gid = st["groups"][0]["id"]
    ok(requests.patch(f"{s}/location-groups/{gid}", json={"location_name": "Terminal Pulogebang",
                                                          "traffic_condition": "Padat",
                                                          "event_date": "2026-11-18", "event_time": "07:30"}))
    finals = ok(requests.post(f"{s}/batches/{bid}/final-videos"))
    fid = finals[0]["id"]
    f = ok(requests.get(f"{s}/final-videos/{fid}"))
    assert f["duration_status"]["state"] == "ok"
    assert f["output_filename"] == "Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4"
    seg = f["segments"][0]
    ok(requests.patch(f"{s}/final-videos/{fid}/segments/{seg['id']}", json={"allocated": 2.0}))
    f = ok(requests.post(f"{s}/final-videos/{fid}/select-segments"))
    assert f["duration_status"]["total"] == pytest.approx(30, abs=0.05)
    meta = ok(requests.get(f"{s}/final-videos/{fid}/metadata"))
    assert meta["filename_valid"]

    job = ok(requests.post(f"{s}/final-videos/{fid}/export", json={"kind": "final"}))
    for _ in range(300):
        e = ok(requests.get(f"{s}/exports/{job['id']}"))
        if e["status"] in ("done", "failed"):
            break
        time.sleep(0.3)
    assert e["status"] == "done", e
    r = requests.get(f"{s}/exports/{job['id']}/download")
    assert r.status_code == 200 and len(r.content) > 10000
    assert "Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4" in r.headers.get("content-disposition", "")
    rep = ok(requests.get(f"{s}/batches/{bid}/report"))
    assert len(rep["exports_succeeded"]) == 1
    assert ok(requests.get(f"{s}/models"))["heuristic_mode"] in (True, False)
    assert requests.get(s + "/tidak-ada").status_code == 404


def test_platform_modules(server):
    s = server
    h = requests.get(s + "/downloader/health")
    assert h.ok and "yt_dlp_version" in h.json()
    assert requests.get(s + "/integration/downloads").json() == []
    assert requests.post(s + "/downloader/parse", json={"text": "x"},
                         headers={"Origin": "https://evil.example"}).status_code == 403
    assert requests.get(s + "/meta").json()["final_durations"] == list(range(10, 61, 5))

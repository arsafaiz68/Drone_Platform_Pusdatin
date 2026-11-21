"""Pengujian endpoint FastAPI (memerlukan fastapi + httpx dari requirements-dev.txt)."""
import time
from dataclasses import replace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.downloader.config import load_settings  # noqa: E402
from app.downloader.router import create_app  # noqa: E402

from .conftest import SAMPLE_REPORT, FakeDownloader  # noqa: E402

ORIGIN = "http://localhost:5173"


@pytest.fixture
def client(tmp_path):
    s = replace(
        load_settings(),
        data_dir=tmp_path, log_dir=tmp_path / "logs", history_dir=tmp_path / "hist",
        default_output_dir=tmp_path / "out",
        allowed_hosts=["testserver", "127.0.0.1", "localhost"],
    )
    app = create_app(s, downloader=FakeDownloader())
    with TestClient(app) as c:
        c.tmp = tmp_path
        yield c


def test_health(client):
    r = client.get("/api/downloader/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_rejects_foreign_origin(client):
    r = client.post("/api/downloader/parse", json={"text": "x"}, headers={"Origin": "https://evil.com"})
    assert r.status_code == 403


def test_parse_and_preview(client):
    r = client.post("/api/downloader/parse", json={"text": SAMPLE_REPORT}, headers={"Origin": ORIGIN})
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total_urls"] == 6
    entries = data["entries"]
    entries[0]["traffic"] = "Padat Merayap"
    entries[1]["location"] = entries[0]["location"]
    entries[1]["time"] = entries[0]["time"]
    entries[1]["traffic"] = "Padat Merayap"
    names = [e["filename"] for e in client.post("/api/downloader/naming/preview", json={"entries": entries}).json()["entries"]]
    assert names[0] == "01.04_14.10_Pel Ketapang_Padat Merayap"
    assert names[1] == "01.04_14.10_Pel Ketapang_Padat Merayap_2"


def test_local_folder_browser(client):
    base = client.tmp / "arsip"
    (base / "April").mkdir(parents=True)
    assert client.get("/api/downloader/local/roots").status_code == 200
    r = client.get("/api/downloader/local/folders", params={"path": str(base)}).json()
    assert r["children"][0]["name"] == "April"
    created = client.post("/api/downloader/local/folders", json={"parent": str(base), "name": "Mei"})
    assert created.status_code == 201
    assert client.get("/api/downloader/local/folders", params={"path": str(base / "nope")}).status_code == 404
    assert client.post("/api/downloader/local/validate", json={"path": str(base)}).json()["valid"] is True


def test_batch_lifecycle_with_websocket(client):
    out = client.tmp / "hasil"
    out.mkdir()
    entries = client.post("/api/downloader/parse", json={"text": SAMPLE_REPORT}).json()["entries"]
    r = client.post("/api/downloader/batches", json={"entries": entries, "output_dir": str(out), "quality": 720, "parallel": 2})
    assert r.status_code == 201, r.text
    batch_id = r.json()["id"]
    with client.websocket_connect(f"/api/downloader/downloader/batches/{batch_id}/ws") as ws:
        assert ws.receive_json()["type"] == "snapshot"
    for _ in range(100):
        b = client.get(f"/api/downloader/downloader/batches/{batch_id}").json()
        if b["summary"]["finished"]:
            break
        time.sleep(0.05)
    assert b["summary"]["success"] == 6
    assert len(list(out.glob("*.mp4"))) == 6
    assert client.get("/api/downloader/batches").json()["batches"][0]["id"] == batch_id


def test_batch_rejects_invalid_url_and_folder(client):
    entries = client.post("/api/downloader/parse", json={"text": SAMPLE_REPORT}).json()["entries"]
    out = client.tmp / "ok"
    out.mkdir()
    bad = [dict(entries[0], url_original="https://evil.com/watch?v=tqvej7BovSQ")]
    assert client.post("/api/downloader/batches", json={"entries": bad, "output_dir": str(out)}).status_code == 422
    r = client.post("/api/downloader/batches", json={"entries": entries, "output_dir": str(client.tmp / "tidak-ada")})
    assert r.status_code == 404

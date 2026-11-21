"""Drone Video Compiler — impor media, proyek JSON, render komposisi multi-track (FFmpeg native).

Video uji berupa warna polos agar posisi klip di hasil render dapat diverifikasi per piksel.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest


def _ff(*a):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *a], check=True)


@pytest.fixture(scope="module")
def cassets(tmp_path_factory):
    d = tmp_path_factory.mktemp("cmedia")
    out = {}
    for name, color, freq in (("merah", "red", 300), ("hijau", "lime", 500), ("biru", "blue", 700)):
        p = d / f"{name}.mp4"
        _ff("-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=25:d=6", "-f", "lavfi", "-i", f"sine=f={freq}:d=6",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(p))
        out[name] = p
    out["musik"] = d / "musik.wav"
    _ff("-f", "lavfi", "-i", "sine=f=220:d=20:sample_rate=48000", "-af", "volume=0.5", str(out["musik"]))
    out["logo"] = d / "logo.png"
    _ff("-f", "lavfi", "-i", "color=c=yellow:s=200x200:d=1", "-frames:v", "1", str(out["logo"]))
    out["hevc"] = d / "pip.mkv"
    _ff("-f", "lavfi", "-i", "color=c=white:s=320x240:r=30:d=4", "-c:v", "libx265", "-x265-params", "log-level=error",
        "-preset", "ultrafast", str(out["hevc"]))
    return out


@pytest.fixture()
def cenv(env):
    from app.compiler import media, render, store
    yield {"store": store, "media": media, "render": render, **env}


def _wait_media(store, ids, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        lib = store.all_media()
        if all(lib[i]["proxy"] in ("none", "ready", "failed") and (lib[i]["kind"] == "audio" or lib[i]["thumb"])
               for i in ids):
            return lib
        time.sleep(0.2)
    raise TimeoutError("media belum selesai diproses")


def _frame(path, t, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3)


def _mean_db(path, a, b):
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{a}", "-t", f"{b - a}", "-i", str(path), "-vn",
                        "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "mean_volume" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0])
    return -999.0


def _text_png(w, h):
    from PIL import Image
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y in range(int(h * 0.85), int(h * 0.95)):
        for x in range(int(w * 0.3), int(w * 0.7)):
            img.putpixel((x, y), (255, 0, 255, 255))
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def test_import_media_kinds_and_library(cassets, cenv):
    M, S = cenv["media"], cenv["store"]
    res = M.register_paths([str(cassets["merah"]), str(cassets["musik"]), str(cassets["logo"]), str(cassets["hevc"])])
    assert not res["errors"], res["errors"]
    kinds = {Path(m["path"]).name: m for m in res["added"]}
    assert kinds["merah.mp4"]["kind"] == "video" and kinds["merah.mp4"]["duration"] == pytest.approx(6, abs=0.1)
    assert kinds["merah.mp4"]["width"] == 640 and kinds["merah.mp4"]["has_audio"]
    assert kinds["musik.wav"]["kind"] == "audio" and kinds["musik.wav"]["duration"] == pytest.approx(20, abs=0.1)
    assert kinds["logo.png"]["kind"] == "image" and kinds["logo.png"]["width"] == 200
    assert kinds["pip.mkv"]["proxy"] == "pending"   # HEVC/MKV -> proxy preview untuk browser
    lib = _wait_media(S, [m["id"] for m in res["added"]])
    assert lib[kinds["pip.mkv"]["id"]]["proxy"] == "ready"
    assert lib[kinds["merah.mp4"]["id"]]["thumb"] and lib[kinds["musik.wav"]["id"]]["wave"]
    # mendaftarkan file yang sama dua kali tidak menduplikasi pustaka
    again = M.register_paths([str(cassets["merah"])])["added"][0]
    assert again["id"] == kinds["merah.mp4"]["id"]
    # folder: semua file media di dalamnya terdaftar
    folder = M.register_paths([str(cassets["merah"].parent)])
    assert len(folder["added"]) >= 6
    # lepas dari pustaka tidak menghapus file asli
    S.forget_media(kinds["logo.png"]["id"])
    assert cassets["logo"].exists()


def test_project_crud_and_json(cenv):
    S = cenv["store"]
    p = S.create_project("Kompilasi Mudik")
    assert [t["id"] for t in p["tracks"]] == ["T1", "I1", "V2", "V1", "A1", "A2"]
    p["clips"].append({"id": "c1", "track": "V1", "media_id": "x", "start": 2, "in": 0, "duration": 5})
    S.save_project(p)
    got = S.get_project(p["id"])
    assert got["duration"] == 7 and got["clips"][0]["start"] == 2
    d = S.duplicate_project(p["id"])
    assert d["id"] != p["id"] and d["name"].endswith("(salinan)") and d["clips"][0]["id"] == "c1"
    r = S.rename_project(d["id"], "Versi 2")
    assert S.get_project(d["id"])["name"] == "Versi 2" == r["name"]
    imp = S.import_project(json.loads(json.dumps(got)))
    assert imp["id"] != p["id"] and imp["missing_media"] == [] and len(imp["clips"]) == 1
    S.delete_project(d["id"])
    assert {x["id"] for x in S.list_projects()} == {p["id"], imp["id"]}
    with pytest.raises(S.CompilerError):
        S.import_project({"foo": 1})


def test_render_full_composition(cassets, cenv):
    """3 video berurutan + crossfade, overlay V2 (HEVC), gambar I1, teks T1, musik A2 dengan fade."""
    M, S, R = cenv["media"], cenv["store"], cenv["render"]
    reg = {Path(m["path"]).stem: m for m in M.register_paths(
        [str(cassets[k]) for k in ("merah", "hijau", "biru", "musik", "logo", "hevc")])["added"]}
    _wait_media(S, [m["id"] for m in reg.values()])
    p = S.create_project("Uji Render")
    p["settings"]["aspect"] = "16:9"
    p["media"] = [S.get_media(m["id"]) for m in reg.values()]
    p["clips"] = [
        {"id": "v1", "track": "V1", "media_id": reg["merah"]["id"], "start": 0, "in": 0, "duration": 4},
        {"id": "v2", "track": "V1", "media_id": reg["hijau"]["id"], "start": 4, "in": 1, "duration": 4},
        # klip ketiga crossfade 1 dtk di atas ekor klip kedua
        {"id": "v3", "track": "V1", "media_id": reg["biru"]["id"], "start": 7.5, "in": 0, "duration": 4.5,
         "transition": "crossfade", "transition_duration": 1.0},
        {"id": "pip", "track": "V2", "media_id": reg["pip"]["id"], "start": 1, "in": 0, "duration": 2,
         "scale": 0.25, "x": 0.85, "y": 0.2, "opacity": 1},
        {"id": "img", "track": "I1", "media_id": reg["logo"]["id"], "start": 5, "in": 0, "duration": 2,
         "scale": 0.2, "x": 0.15, "y": 0.2},
        {"id": "txt", "track": "T1", "start": 9, "duration": 2, "text": "Judul"},
        {"id": "mus", "track": "A2", "media_id": reg["musik"]["id"], "start": 0, "in": 0, "duration": 12,
         "volume": 1.0, "fade_in": 2.0, "fade_out": 2.0},
    ]
    p["tracks"] = [t | ({"muted": True} if t["id"] == "V1" else {}) for t in p["tracks"]]  # hanya musik terdengar
    p = S.save_project(p)
    est = R.estimate(p, {"resolution": "1080", "fps": "source", "codec": "h264", "quality": "high"})
    assert (est["width"], est["height"], est["fps"]) == (1920, 1080, 25)
    assert est["estimated_size_bytes"] > 0
    job = R.start_render(p["id"], {"resolution": "1080", "fps": "source", "codec": "h264", "quality": "high"},
                         {"txt": _text_png(1920, 1080)})
    done = R.wait(job["id"], 600)
    assert done["status"] == "done", done["error"]
    out = Path(done["output_path"])
    res = done["result"]
    assert (res["width"], res["height"]) == (1920, 1080) and res["vcodec"] == "h264" and res["acodec"] == "aac"
    assert res["duration"] == pytest.approx(12, abs=0.1) and res["size_bytes"] == out.stat().st_size
    W, H = 1920, 1080
    c = lambda t, x, y: _frame(out, t, W, H)[y, x].astype(int)  # noqa: E731
    assert c(0.5, 960, 540)[0] > 200 and c(0.5, 960, 540)[1] < 60            # merah 0–4 dtk
    assert c(5.5, 960, 540)[1] > 200 and c(5.5, 960, 540)[0] < 60            # hijau 4–8 dtk
    mid = c(7.8, 960, 540)                                                     # crossfade hijau->biru
    assert mid[1] > 60 and mid[2] > 40
    assert c(10, 960, 300)[2] > 200 and c(10, 960, 300)[1] < 60              # biru
    pip = c(2.0, int(0.85 * W), int(0.2 * H))
    assert pip.min() > 200                                                     # overlay putih V2 di 1–3 dtk
    assert c(4.5, int(0.85 * W), int(0.2 * H))[1] > 200                       # overlay hilang -> hijau
    logo = c(6.0, int(0.15 * W), int(0.2 * H))
    assert logo[0] > 200 and logo[1] > 200 and logo[2] < 80                   # gambar kuning di 5–7 dtk
    txt = c(10, W // 2, int(H * 0.9))
    assert txt[0] > 200 and txt[2] > 200 and txt[1] < 80                      # teks magenta di 9–11 dtk
    assert c(11.5, W // 2, int(H * 0.9))[2] > 200                             # teks hilang -> biru
    # audio: fade in & fade out musik
    full, start, end = _mean_db(out, 4, 8), _mean_db(out, 0, 0.4), _mean_db(out, 11.6, 12)
    assert start < full - 8 and end < full - 8


def test_render_cancel_and_aspect(cassets, cenv):
    M, S, R = cenv["media"], cenv["store"], cenv["render"]
    m = M.register_paths([str(cassets["merah"])])["added"][0]
    p = S.create_project("Vertikal")
    p["settings"]["aspect"] = "9:16"
    p["clips"] = [{"id": "a", "track": "V1", "media_id": m["id"], "start": 0, "in": 0, "duration": 6}]
    p = S.save_project(p)
    cv = R.canvas(p, {"resolution": "1080"})
    assert (cv["width"], cv["height"]) == (1080, 1920)
    assert (R.canvas(p, {"resolution": "1440"})["width"], R.canvas(p, {"resolution": "1440"})["height"]) == (1440, 2560)
    p["settings"]["aspect"] = "original"
    p = S.save_project(p)
    cv = R.canvas(p, {"resolution": "source", "fps": 50})
    assert (cv["width"], cv["height"], cv["fps"]) == (640, 360, 50)
    job = R.start_render(p["id"], {"resolution": "2160", "quality": "max"}, {})
    time.sleep(0.5)
    R.cancel(job["id"])
    done = R.wait(job["id"], 120)
    assert done["status"] in ("cancelled", "done")
    if done["status"] == "cancelled":
        assert not Path(done["output_path"]).exists()


def test_empty_timeline_rejected(cenv):
    S, R = cenv["store"], cenv["render"]
    p = S.create_project("Kosong")
    with pytest.raises(S.CompilerError, match="kosong"):
        R.start_render(p["id"], {}, {})


def test_http_upload_project_render(cassets, cenv):
    """Alur HTTP lengkap (dilewati bila paket fastapi tidak terpasang)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as cl:
        data = cassets["merah"].read_bytes()
        r = cl.post("/api/compiler/media/upload", params={"filename": "merah.mp4"}, content=data,
                    headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["kind"] == "video" and m["uploaded"] and m["duration"] == pytest.approx(6, abs=0.1)
        assert cl.get(f"/api/compiler/media/{m['id']}/file", headers={"Range": "bytes=0-99"}).status_code == 206
        p = cl.post("/api/compiler/projects", json={"name": "HTTP"}).json()
        p["media"] = [m]
        p["clips"] = [{"id": "a", "track": "V1", "media_id": m["id"], "start": 0, "in": 0, "duration": 3}]
        saved = cl.put(f"/api/compiler/projects/{p['id']}", json=p).json()
        assert saved["duration"] == 3
        assert cl.get(f"/api/compiler/projects/{p['id']}").json()["clips"][0]["media_id"] == m["id"]
        job = cl.post(f"/api/compiler/projects/{p['id']}/render", json={"export": {"quality": "high"}}).json()
        cenv["render"].wait(job["id"], 300)
        j = cl.get(f"/api/compiler/renders/{job['id']}").json()
        assert j["status"] == "done", j["error"]
        assert cl.get(f"/api/compiler/renders/{job['id']}/download").status_code == 200
        assert cl.post("/api/compiler/media/upload", params={"filename": "x.exe"}, content=b"1").status_code == 400


def test_relink_moved_media(cassets, cenv, tmp_path):
    """File berpindah folder: terdeteksi hilang, dipanggil ulang per file atau via pencarian folder."""
    import shutil
    M, S = cenv["media"], cenv["store"]
    from app.compiler import relink as RL
    src = tmp_path / "lama"
    src.mkdir()
    a, b = src / "Klip A.mp4", src / "Musik B.wav"
    shutil.copy(cassets["merah"], a)
    shutil.copy(cassets["musik"], b)
    ma, mb = (M.register_file(str(x)) for x in (a, b))
    p = S.create_project("Pindah")
    p["media"] = [ma, mb]
    p["clips"] = [{"id": "x", "track": "V1", "media_id": ma["id"], "start": 0, "in": 1, "duration": 3},
                  {"id": "y", "track": "A2", "media_id": mb["id"], "start": 0, "in": 0, "duration": 5}]
    S.save_project(p)
    baru = tmp_path / "arsip" / "2026" / "sub"
    baru.mkdir(parents=True)
    shutil.move(str(a), baru / "Klip A.mp4")
    shutil.move(str(b), tmp_path / "arsip" / "musik b.WAV")
    st = {x["id"]: x for x in RL.check(p["media"])}
    assert not st[ma["id"]]["exists"] and not st[mb["id"]]["exists"]
    assert st[ma["id"]]["nearest_folder"] == str(src)
    # panggil ulang satu file -> id tetap sama sehingga klip langsung tersambung
    r = RL.relink(ma["id"], str(baru / "Klip A.mp4"))
    assert r["id"] == ma["id"] and r["path"].endswith("Klip A.mp4") and S.get_media(ma["id"])["path"] == r["path"]
    with pytest.raises(S.CompilerError, match="Jenis file berbeda"):
        RL.relink(mb["id"], str(baru / "Klip A.mp4"))
    # cari otomatis di folder (rekursif, tidak peka huruf besar/kecil)
    res = RL.find_in_folder(str(tmp_path / "arsip"), [{"id": mb["id"], "name": "Musik B.wav", "size": mb["size"], "kind": "audio"}])
    assert [x["id"] for x in res["relinked"]] == [mb["id"]] and not res["not_found"]
    assert all(x["exists"] for x in RL.check(p["media"]))
    # media dari komputer lain (tidak ada di pustaka) -> didaftarkan, id baru dilaporkan
    foreign = RL.relink("m_dari_pc_lain", str(baru / "Klip A.mp4"), "video")
    assert foreign["relinked_from"] == "m_dari_pc_lain" and foreign["kind"] == "video"
    assert RL.open_location(str(src / "hilang.mp4")) == str(src)

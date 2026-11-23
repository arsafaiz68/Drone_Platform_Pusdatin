"""Platform gabungan: 1 video sumber = 1 video hasil (30/45/60 dtk) & integrasi Downloader -> Trimmer."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from app.downloader.manifest import MANIFEST_NAME, guess_from_filename, read_manifest, record_video
from app.services import batch_service as B, export_service as E, integration_service as I
from app.services import selection_service as S, timeline_service as T
from app.services.timeline_service import ValidationError
from conftest import wait_batch


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True).stdout
    return float(out)


def _dl_folder(tmp_path, assets):
    """Folder hasil unduhan tiruan: 2 video bernama standar + manifest downloader."""
    folder = tmp_path / "Arsip Unduhan"
    folder.mkdir()
    a = folder / "27.03_14.00_Pel Merak_Normal Lancar.mp4"
    b = folder / "27.03_08.00_GT Cikatama_Padat.mp4"
    shutil.copy(assets["long"], a)
    shutil.copy(assets["roundtrip"], b)
    record_video(a, {"location": "Pel. Merak", "date": "2026-03-27", "time": "14:00", "timezone": "WIB",
                     "weather": "Berawan", "traffic": "Normal Lancar",
                     "url_original": "https://www.youtube.com/live/3CiaEbWk_Ak"}, batch_id="dl1", job_id="j1")
    return folder, a, b


# ------------------------------------------------------------------ manifest & nama file
def test_manifest_and_filename_guess(tmp_path, assets):
    folder, a, b = _dl_folder(tmp_path, assets)
    man = read_manifest(folder)
    assert man[a.name]["location"] == "Pel. Merak" and man[a.name]["batch_id"] == "dl1"
    g = guess_from_filename(b.name, year=2026)
    assert g["location"] == "GT Cikatama" and g["traffic"] == "Padat"
    assert g["date"] == "2026-03-27" and g["time"] == "08:00"
    assert guess_from_filename("random_name.mp4") == {}
    scan = I.scan_folder(str(folder))
    assert scan["has_manifest"] and len(scan["videos"]) == 2
    by = {v["filename"]: v for v in scan["videos"]}
    assert by[a.name]["info_source"] == "manifest" and by[b.name]["info_source"] == "filename"
    assert by[a.name]["fields"] == {"location_name": "Pel. Merak", "traffic_condition": "Normal Lancar",
                                    "event_date": "2026-03-27", "event_time": "14:00"}


def test_local_path_reads_info_automatically(project, tmp_path, assets):
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, 30, "round_trip", 2)
    vids = B.add_local_paths(bt["id"], [str(a), str(b)])
    va, vb = vids
    assert va["location_name"] == "Pel. Merak" and va["event_time"] == "14:00" and va["source_origin"] == "downloader"
    assert va["source_meta"]["weather"] == "Berawan"
    assert vb["location_name"] == "GT Cikatama" and vb["traffic_condition"] == "Padat"
    items = B.list_items(bt["id"])
    assert items[0]["location_name"] == "Pel. Merak"


# ------------------------------------------------------------------ riwayat downloader
class _FakeBatch:
    def __init__(self, d):
        self.d = d
        self.created_at = d["created_at"]

    def to_dict(self, include_jobs=True):
        return self.d


class _FakeManager:
    def __init__(self, batches):
        self.batches = {b["id"]: _FakeBatch(b) for b in batches}

    def list(self):
        return list(self.batches.values())

    def get(self, bid):
        if bid not in self.batches:
            raise KeyError(bid)
        return self.batches[bid]


def test_import_from_downloader_history(project, tmp_path, assets):
    folder, a, b = _dl_folder(tmp_path, assets)
    dl = {"id": "20261118-1", "created_at": "2026-11-18T07:00:00", "report_date": "2026-03-27",
          "output_dir": str(folder), "status": "completed", "summary": {},
          "jobs": [
              {"id": "j1", "index": 1, "status": "success", "output_path": str(a),
               "metadata": {"location": "Pel. Merak", "date": "2026-03-27", "time": "14:00", "traffic": "Normal Lancar"}},
              {"id": "j2", "index": 2, "status": "success", "output_path": str(b),
               "metadata": {"location": "GT Cikatama", "date": "2026-03-27", "time": "08:00", "traffic": "Padat"}},
              {"id": "j3", "index": 3, "status": "failed", "output_path": None, "metadata": {}},
          ]}
    mgr = _FakeManager([dl])
    lst = I.list_download_batches(mgr)
    assert lst[0]["available"] == 2 and len(lst[0]["videos"]) == 2
    bt = B.create_batch(project["id"], None, 45, "round_trip", 2)
    vids = I.download_batch_videos(mgr, dl["id"])
    added = I.import_videos(bt["id"], [{"path": v["path"], "info": v["info"]} for v in vids])
    assert [v["location_name"] for v in added] == ["Pel. Merak", "GT Cikatama"]
    assert added[1]["event_time"] == "08:00"
    with pytest.raises(ValidationError):  # duplikat
        I.import_videos(bt["id"], [{"path": str(a), "info": None}])
    with pytest.raises(ValidationError):  # > 24 video
        I.import_videos(bt["id"], [{"path": str(a)}] * 25)


# ------------------------------------------------------------------ 1 video = 1 video hasil
def test_fill_from_source_spreads_without_overlap():
    st = {"min_segment_seconds": 3.0, "max_segment_seconds": 20.0}
    segs, warns = S.fill_from_source([], 7, 240.0, 60, st)
    assert abs(sum(s["end"] - s["start"] for s in segs) - 60) < 0.05
    assert all(s["end"] - s["start"] <= 20.0 + 1e-6 for s in segs)
    for x, y in zip(segs, segs[1:]):
        assert x["end"] <= y["start"] + 1e-6  # kronologis & tidak tumpang tindih
    assert segs[0]["start"] > 0 and segs[-1]["end"] < 240
    base = [{"candidate_id": 1, "video_id": 7, "point_code": "1", "direction": "outbound", "role": "point",
             "start": 10.0, "end": 22.0, "allocated": 12.0}]
    segs, _ = S.fill_from_source(base, 7, 240.0, 45, st)
    assert abs(sum(s["end"] - s["start"] for s in segs) - 45) < 0.05
    assert segs[0]["candidate_id"] == 1 or any(s["candidate_id"] == 1 for s in segs)
    short, warns = S.fill_from_source([], 7, 12.0, 30, st)
    assert len(short) == 1 and short[0]["end"] == 12.0 and warns


@pytest.mark.parametrize("target", [30, 45, 60])
def test_each_source_video_gets_its_own_output(project, tmp_path, assets, worker, target):
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, target, "round_trip", 2)
    B.add_local_paths(bt["id"], [str(a), str(b), str(assets["short720"])])
    B.start_batch(bt["id"])
    wait_batch(bt["id"])
    finals = [T.create_video_output(it["video_id"], target) for it in B.list_items(bt["id"])]
    assert len(finals) == 3                                     # 3 video masuk -> 3 video hasil
    assert len({f["source_video_id"] for f in finals}) == 3
    for f in finals:
        assert {s["video_id"] for s in f["segments"]} == {f["source_video_id"]}   # tidak dicampur
        src_dur = f["source_video"]["duration"]
        expect = min(target, src_dur)
        assert f["duration_status"]["total"] == pytest.approx(expect, abs=0.06)
        starts = [s["start"] for s in f["segments"]]
        assert starts == sorted(starts)
    fa = next(f for f in finals if f["source_video"]["filename"] == a.name)
    assert fa["output_filename"] == "Clipped_27.03_14.00_PelMerak_NormalLancar.mp4"
    assert fa["metadata"]["cuaca"] == "Berawan"
    assert fa["duration_status"]["state"] == "ok"
    short = next(f for f in finals if f["source_video"]["filename"] == assets["short720"].name)
    assert short["duration_status"]["state"] == "under"        # sumber 12 dtk < target
    again = T.create_video_output(fa["source_video_id"], target)   # idempoten
    assert again["id"] == fa["id"]


def test_per_video_segments_restricted_and_info_sync(project, tmp_path, assets, worker):
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, 30, "round_trip", 2)
    va, vb = B.add_local_paths(bt["id"], [str(a), str(b)])
    B.start_batch(bt["id"])
    wait_batch(bt["id"])
    fa = T.create_video_output(va["id"])
    with pytest.raises(ValidationError):
        T.add_segment(fa["id"], video_id=vb["id"], start=0, end=3)
    B.update_video(va["id"], {"traffic_condition": "Padat", "event_time": "15.30"})
    f = T.get_final(fa["id"])
    assert f["traffic_condition"] == "Padat" and f["event_time"] == "15:30"
    assert f["output_filename"] == "Clipped_27.03_15.30_PelMerak_Padat.mp4"
    with pytest.raises(ValidationError):
        B.update_video(va["id"], {"event_date": "27-03-2026"})


def test_export_one_output_per_video(project, tmp_path, assets, worker):
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, 30, "round_trip", 2)
    B.add_local_paths(bt["id"], [str(a), str(b)])
    B.start_batch(bt["id"])
    wait_batch(bt["id"])
    finals = [T.create_video_output(it["video_id"]) for it in B.list_items(bt["id"])]
    for f in finals:
        E.start_export(f["id"], "final")
    E.wait_all(300)
    outs = []
    for f in finals:
        job = T.get_final(f["id"])["exports"][0]
        assert job["status"] == "done", job.get("error")
        outs.append(Path(job["output_path"]))
        assert dur(job["output_path"]) == pytest.approx(30, abs=0.6)
        side = json.loads(Path(job["output_path"]).with_suffix(".json").read_text(encoding="utf-8"))
        assert side["metadata"]["video_sumber"] == f["source_video"]["filename"]
    assert len({o.name for o in outs}) == 2


def test_duration_options():
    from app.core.config import FINAL_DURATIONS, MAX_BATCH_VIDEOS
    assert FINAL_DURATIONS == tuple(range(10, 61, 5)) and MAX_BATCH_VIDEOS == 24


def test_batch_accepts_45_and_rejects_others(project):
    b = B.create_batch(project["id"], None, 45, "round_trip", 2)
    assert b["final_duration"] == 45
    assert B.create_batch(project["id"], None, 15, "round_trip", 2)["final_duration"] == 15
    for bad in (0, 5, 7, 65, 90):
        with pytest.raises(ValidationError):
            B.create_batch(project["id"], None, bad, "round_trip", 2)


# ------------------------------------------------------------------ migrasi database lama
def test_migrates_v1_database(tmp_path, monkeypatch):
    old_schema = Path(__file__).parent / "fixtures" / "schema_v1.sql"
    data = tmp_path / "data"
    (data / "database").mkdir(parents=True)
    dbfile = data / "database" / "ai_drone_trimmer.db"
    con = sqlite3.connect(dbfile)
    con.executescript(old_schema.read_text(encoding="utf-8"))
    con.execute("INSERT INTO schema_version(version) VALUES (1)")
    con.commit()
    con.close()
    monkeypatch.setenv("ADT_DATA_DIR", str(data))
    from app.core.config import paths
    from app.database import db
    paths.refresh()
    db.init_db()
    cols = {r["name"] for r in db.query("PRAGMA table_info(source_videos)")}
    assert {"location_name", "event_date", "event_time", "traffic_condition", "source_meta_json"} <= cols
    assert "source_video_id" in {r["name"] for r in db.query("PRAGMA table_info(final_videos)")}
    assert db.scalar("SELECT version FROM schema_version") == 2


# ------------------------------------------------------------------ jenis lokasi per video
@pytest.mark.parametrize("name,code", [
    ("Pel. Merak", "pelabuhan"), ("Pelabuhan Bakauheni", "pelabuhan"),
    ("Terminal Pulo Gebang", "terminal"), ("Stasiun Gambir", "stasiun"),
    ("Tol Jakarta-Cikampek KM 47", "jalan_tol"), ("GT Cikatama", "gerbang_tol"),
    ("RA KM 57 Tol Jakarta-Cikampek", "rest_area"), ("Rest Area 207A", "rest_area"),
    ("Jl. Raya Puncak", "jalan_arteri"), ("Simpang Jomin", "jalan_arteri"), ("Bandara Soetta", None),
])
def test_detect_location_type(name, code):
    from app.core.templates_config import detect_template
    assert detect_template(name) == code


def test_mixed_locations_in_one_batch(project, tmp_path, assets, worker):
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, 30, "round_trip", 2)      # template batch: terminal
    va, vb = B.add_local_paths(bt["id"], [str(a), str(b)])
    assert va["template_code"] == "pelabuhan" and vb["template_code"] == "gerbang_tol"
    B.start_batch(bt["id"])
    wait_batch(bt["id"])
    fa, fb = T.create_video_output(va["id"]), T.create_video_output(vb["id"])
    assert fa["template_code"] == "pelabuhan" and fa["location_type"] == "Pelabuhan"
    assert fb["template_code"] == "gerbang_tol"
    pts_a = {c["point_code"] for c in T.list_candidates(va["id"])}
    assert pts_a <= {"H", "1", "2", "3", "4"}
    assert fa["duration_status"]["state"] == "ok"
    # ubah jenis lokasi -> kandidat lama dihapus, perlu analisis ulang
    B.update_video(va["id"], {"template_code": "terminal"})
    v = B.get_video(va["id"])
    assert v["template_code"] == "terminal" and v["candidate_count"] == 0 and v["item"]["status"] == "waiting"
    assert T.get_final(fa["id"])["template_code"] == "terminal"


# ------------------------------------------------------------------ hapus batch & ZIP
def test_zip_and_delete_batch(project, tmp_path, assets, worker):
    import zipfile as zf
    from app.services import archive_service as A
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, 30, "round_trip", 2)
    B.add_local_paths(bt["id"], [str(a), str(b)])
    with pytest.raises(ValidationError):
        A.build_zip(batch_id=bt["id"])                      # belum ada ekspor
    B.start_batch(bt["id"])
    wait_batch(bt["id"])
    finals = [T.create_video_output(it["video_id"]) for it in B.list_items(bt["id"])]
    for f in finals:
        E.start_export(f["id"], "final")
    E.wait_all(300)
    assert A.zip_summary(batch_id=bt["id"])["ready"] == 2
    path, name = A.build_zip(batch_id=bt["id"])
    names = zf.ZipFile(path).namelist()
    assert sorted(n for n in names if n.endswith(".mp4")) == sorted(T.get_final(f["id"])["output_filename"] for f in finals)
    assert "daftar_video_hasil.csv" in names and sum(n.endswith(".json") for n in names) == 3
    csv_text = zf.ZipFile(path).read("daftar_video_hasil.csv").decode("utf-8-sig")
    assert "Pel. Merak" in csv_text and "GT Cikatama" in csv_text
    ppath, _ = A.build_zip(project_id=project["id"])
    assert any(n.endswith(".mp4") for n in zf.ZipFile(ppath).namelist())
    out_files = [T.get_final(f["id"])["exports"][0]["output_path"] for f in finals]
    res = A.delete_batch(bt["id"])
    assert res["deleted"] and res["final_videos"] == 2
    from app.database import db
    assert db.get("batch_jobs", bt["id"]) is None
    assert not db.query("SELECT id FROM source_videos WHERE batch_id=?", (bt["id"],))
    assert not db.query("SELECT id FROM final_videos WHERE id IN (?,?)", [f["id"] for f in finals])
    assert a.exists() and b.exists()                      # file sumber tidak disentuh
    assert all(Path(p).exists() for p in out_files)       # hasil ekspor dipertahankan (default)


def test_delete_batch_with_exports_and_running_guard(project, tmp_path, assets, worker):
    from app.services import archive_service as A
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, 30, "round_trip", 2)
    B.add_local_paths(bt["id"], [str(a)])
    from app.database import db
    db.update("batch_jobs", bt["id"], {"status": "running"})
    with pytest.raises(ValidationError):
        A.delete_batch(bt["id"])
    db.update("batch_jobs", bt["id"], {"status": "draft"})
    B.start_batch(bt["id"])
    wait_batch(bt["id"])
    f = T.create_video_output(B.list_items(bt["id"])[0]["video_id"])
    E.start_export(f["id"], "final")
    E.wait_all(300)
    out = Path(T.get_final(f["id"])["exports"][0]["output_path"])
    assert out.exists()
    A.delete_batch(bt["id"], delete_exports=True)
    assert not out.exists() and not out.with_suffix(".json").exists() and a.exists()


# ------------------------------------------------------------------ status review & hapus proyek
def test_review_status_follows_verification(project, tmp_path, assets, worker):
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, 30, "round_trip", 2)
    va, vb = B.add_local_paths(bt["id"], [str(a), str(b)])
    B.start_batch(bt["id"])
    wait_batch(bt["id"])
    assert B.get_batch(bt["id"])["status"] == "review"
    cands = T.list_candidates(va["id"])
    assert cands
    for c in cands[:-1]:
        T.update_candidate(c["id"], {"verified": True})
    assert B.get_video(va["id"])["item"]["status"] == "review"          # masih ada yang belum
    T.update_candidate(cands[-1]["id"], {"verified": True})
    it = B.get_video(va["id"])["item"]
    assert it["status"] == "done" and it["status_label"] == "Selesai direview"
    assert B.get_batch(bt["id"])["status"] == "review"                  # video B belum direview
    T.update_candidate(cands[0]["id"], {"verified": False})             # batalkan verifikasi
    assert B.get_video(va["id"])["item"]["status"] == "review"
    T.set_review_status(va["id"], True)                                 # tombol manual
    first, *rest = T.list_candidates(vb["id"])
    T.delete_candidate(first["id"])                                     # kandidat ditolak tidak dihitung
    for c in rest:
        T.update_candidate(c["id"], {"verified": True})
    assert B.get_video(vb["id"])["item"]["status"] == "done"
    bb = B.get_batch(bt["id"])
    assert bb["status"] == "completed" and bb["status_label"] == "Selesai"


def test_delete_project(project, tmp_path, assets, worker):
    from app.database import db
    from app.services import archive_service as A
    folder, a, b = _dl_folder(tmp_path, assets)
    b1 = B.create_batch(project["id"], None, 30, "round_trip", 2)
    b2 = B.create_batch(project["id"], None, 45, "round_trip", 2)
    B.add_local_paths(b1["id"], [str(a)])
    B.add_local_paths(b2["id"], [str(b)])
    B.start_batch(b1["id"])
    wait_batch(b1["id"])
    T.create_video_output(B.list_items(b1["id"])[0]["video_id"])
    db.update("batch_jobs", b2["id"], {"status": "running"})
    with pytest.raises(ValidationError):
        A.delete_project(project["id"])
    db.update("batch_jobs", b2["id"], {"status": "draft"})
    # Worker sudah terlanjur menjadwalkan analisis video b2 saat statusnya "running";
    # tunggu analisis yang sedang berjalan itu selesai sebelum menghapus proyek,
    # karena delete_batch memang menolak batch yang itemnya masih "analyzing".
    # (Bila worker belum sempat menjadwalkan, item masih "waiting" dan tidak perlu ditunggu.)
    if B.list_items(b2["id"])[0]["status"] in ("analyzing", "processing", "analyzed"):
        wait_batch(b2["id"])
    r = A.delete_project(project["id"])
    assert r["deleted"] and r["batches"] == 2 and r["final_videos"] >= 1
    assert db.get("projects", project["id"]) is None
    assert not db.query("SELECT id FROM batch_jobs WHERE project_id=?", (project["id"],))
    assert not db.query("SELECT id FROM source_videos WHERE project_id=?", (project["id"],))
    assert a.exists() and b.exists()



# ------------------------------------------------------------------ hapus kandidat & verifikasi semua
def test_deleting_candidate_shortens_result(project, tmp_path, assets, worker):
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, 30, "round_trip", 2)
    va, = B.add_local_paths(bt["id"], [str(a)])
    B.start_batch(bt["id"])
    wait_batch(bt["id"])
    f = T.create_video_output(va["id"])
    assert f["duration_status"]["total"] == pytest.approx(30, abs=0.06)
    used = next(s for s in f["segments"] if s.get("candidate_id"))
    r = T.delete_candidate(used["candidate_id"])
    after = T.get_final(f["id"])
    assert after["duration_status"]["total"] == pytest.approx(30 - used["duration"], abs=0.06)
    assert r["removed_from_finals"][0]["final_video_id"] == f["id"]
    assert all(s.get("candidate_id") != used["candidate_id"] for s in after["segments"])
    # susun ulang: rentang kandidat yang ditolak tidak dipakai lagi sebagai pengisi
    re = T.select_for_final(f["id"])
    for s in re["segments"]:
        assert s["end"] <= used["start"] + 1e-6 or s["start"] >= used["end"] - 1e-6


def test_verify_all(project, tmp_path, assets, worker):
    folder, a, b = _dl_folder(tmp_path, assets)
    bt = B.create_batch(project["id"], None, 20, "round_trip", 2)
    va, vb = B.add_local_paths(bt["id"], [str(a), str(b)])
    B.start_batch(bt["id"])
    wait_batch(bt["id"])
    r = T.verify_all(va["id"])
    assert r["verified"] == len(T.list_candidates(va["id"])) > 0
    assert all(c["verified"] for c in T.list_candidates(va["id"]))
    assert B.get_video(va["id"])["item"]["status"] == "done"
    assert T.verify_all(va["id"])["verified"] == 0
    T.verify_all(vb["id"])
    assert B.get_batch(bt["id"])["status"] == "completed"

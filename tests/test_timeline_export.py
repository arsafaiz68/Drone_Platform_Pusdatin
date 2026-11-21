"""Timeline editing & ekspor — uji #9, #15–#20, #26–#29."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from app.services import batch_service as B, export_service as E, timeline_service as T
from app.services.timeline_service import ValidationError
from conftest import wait_batch


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out)


@pytest.fixture()
def final(project, assets, worker):
    b = B.create_batch(project["id"], None, 30, "round_trip", 2)
    B.add_local_paths(b["id"], [str(assets["roundtrip"]), str(assets["short720"])])
    B.start_batch(b["id"])
    wait_batch(b["id"])
    g = b["groups"][0]["id"]
    f = T.create_final_video(project["id"], [g], 30, "round_trip", batch_id=b["id"])
    return f


def test_final_duration_and_metadata(final, assets):
    # waktu dari metadata video (short720 creation_time 00:30 UTC -> 07:30 WIB) bila operator tidak mengisi
    assert final["time_source_resolved"] in ("metadata", "unknown")
    f = T.update_final(final["id"], {"event_date": "2026-11-18", "event_time": "07:30",
                                     "location_name": "Terminal Pulogebang", "traffic_condition": "Padat"})
    assert f["output_filename"] == "Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4"
    assert f["metadata"]["kondisi_lalin"] == "Padat" and f["metadata"]["jenis_lokasi"] == "Terminal"
    assert f["metadata"]["jumlah_video_sumber"] >= 1
    with pytest.raises(ValidationError):
        T.update_final(final["id"], {"event_time": "25:99"})


def test_manual_timestamp_edit(final):
    s = final["segments"][0]
    f = T.update_segment(s["id"], {"start": s["start"] + 0.5, "end": s["end"]})
    s2 = next(x for x in f["segments"] if x["id"] == s["id"])
    assert s2["start"] == pytest.approx(s["start"] + 0.5) and s2["edited"] == 1
    with pytest.raises(ValidationError):
        T.update_segment(s["id"], {"start": 5, "end": 4})
    with pytest.raises(ValidationError):
        T.update_segment(s["id"], {"start": 0, "end": 9999})
    f = T.reset_segment(s["id"])
    s3 = next(x for x in f["segments"] if x["id"] == s["id"])
    assert s3["start"] == pytest.approx(s["ai_start"]) and s3["edited"] == 0


def test_candidate_correction_saved_as_feedback(final, env):
    vid = final["segments"][0]["video_id"]
    c = T.list_candidates(vid)[0]
    T.update_candidate(c["id"], {"point_code": "2", "direction": "return", "start": c["start"], "end": c["end"] - 0.2})
    T.update_candidate(c["id"], {"verified": True})
    T.reset_candidate(c["id"])
    n = env["db"].scalar("SELECT COUNT(*) FROM operator_feedback")
    assert n >= 2
    fb = env["db"].query("SELECT * FROM operator_feedback WHERE action='correct_candidate'")[0]
    assert fb["template_code"] == "terminal" and fb["point_code"] == "2" and fb["direction"] == "return"
    added = T.add_candidate(vid, 1.0, 4.0, "1", "outbound")
    assert added["origin"] == "operator"


def test_replace_reorder_allocation(final):
    segs = final["segments"]
    fid = final["id"]
    # ganti kandidat
    used = {s["candidate_id"] for s in segs}
    pool = [c for vid in {s["video_id"] for s in segs} for c in T.list_candidates(vid) if c["id"] not in used]
    assert pool, "butuh kandidat cadangan"
    f = T.replace_segment(segs[0]["id"], pool[0]["id"])
    assert f["segments"][0]["candidate_id"] == pool[0]["id"]
    # ubah urutan
    ids = [s["id"] for s in f["segments"]][::-1]
    f = T.reorder_segments(fid, ids)
    assert [s["id"] for s in f["segments"]] == ids
    with pytest.raises(ValidationError):
        T.reorder_segments(fid, ids[:-1])
    # ubah alokasi durasi + total berjalan
    s = f["segments"][0]
    f = T.set_allocations(fid, {s["id"]: 1.5})
    s2 = next(x for x in f["segments"] if x["id"] == s["id"])
    assert s2["duration"] == pytest.approx(1.5, abs=0.01)
    assert f["duration_status"]["state"] == "under"
    assert f["duration_status"]["remaining"] > 0
    # durasi lebih pendek dari target diizinkan langsung (tanpa persetujuan)
    assert not [e for e in E.validate_for_export(T.get_final(fid), "final") if "Setujui" in e]
    # durasi melebihi target tetap perlu persetujuan operator
    seg = f["segments"][0]
    T.update_segment(seg["id"], {"start": 0, "end": min(T._video(seg["video_id"])["duration"], 40)})
    over = T.get_final(fid)
    if over["duration_status"]["state"] == "over":
        with pytest.raises(E.ExportError, match="Setujui"):
            E.start_export(fid, "final")


def test_export_final_and_individual(final, env):
    fid = final["id"]
    T.update_final(fid, {"event_date": "2026-11-18", "event_time": "07:30",
                         "location_name": "Terminal Pulogebang", "traffic_condition": "Padat"})
    f = T.get_final(fid)
    assert f["duration_status"]["state"] == "ok"
    j1 = E.start_export(fid, "final")
    j2 = E.start_export(fid, "final")   # nama duplikat -> _01
    j3 = E.start_export(fid, "individual")
    E.wait_all(300)
    db = env["db"]
    e1, e2, e3 = (db.get("export_jobs", j["id"]) for j in (j1, j2, j3))
    assert e1["status"] == "done", e1["error"]
    names = sorted(Path(e["output_path"]).name for e in (e1, e2))
    assert names == ["Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4",
                     "Clipped_18.11_07.30_TerminalPulogebang_Padat_01.mp4"]
    assert dur(e1["output_path"]) == pytest.approx(30, abs=0.25)
    side = json.loads(Path(e1["output_path"]).with_suffix(".json").read_text(encoding="utf-8"))
    assert side["metadata"]["nama_lokasi"] == "Terminal Pulogebang"
    assert e3["status"] == "done", e3["error"]
    seg_files = sorted(p for p in os.listdir(e3["output_path"]) if p.endswith(".mp4"))
    assert len(seg_files) == len(f["segments"])
    assert seg_files[0].startswith("Clipped_18.11_07.30_TerminalPulogebang_Padat_Seg01_")
    total = sum(dur(Path(e3["output_path"]) / p) for p in seg_files)
    assert total == pytest.approx(30, abs=0.6)
    assert T.get_final(fid)["status"] == "exported"


def test_source_files_untouched(final, assets):
    before = {k: (p.stat().st_size, p.stat().st_mtime) for k, p in assets.items() if k in ("roundtrip", "short720")}
    T.update_final(final["id"], {"event_date": "2026-11-18", "event_time": "07:30"})
    E.start_export(final["id"], "final")
    E.wait_all(300)
    after = {k: (assets[k].stat().st_size, assets[k].stat().st_mtime) for k in before}
    assert before == after


def test_no_time_metadata_requires_operator_input(project, assets, worker):
    b = B.create_batch(project["id"], None, 30, "round_trip", 1)
    B.add_local_paths(b["id"], [str(assets["roundtrip"])])  # tanpa creation_time
    B.start_batch(b["id"])
    wait_batch(b["id"])
    f = T.create_final_video(project["id"], [b["groups"][0]["id"]], 30, "round_trip", batch_id=b["id"])
    assert f["time_source_resolved"] == "unknown" and f["output_filename"] is None
    T.update_final(f["id"], {"approved_duration_mismatch": True})
    with pytest.raises(E.ExportError, match="[Tt]anggal"):
        E.start_export(f["id"], "final")
    f = T.update_final(f["id"], {"event_date": "2026-11-18", "event_time": "06:00", "custom_filename":
                                 "Clipped_18.11_06.00_TerminalBaru_Lancar"})
    assert f["output_filename"] == "Clipped_18.11_06.00_TerminalBaru_Lancar.mp4"


def test_preview_render(final, env):
    j = E.start_export(final["id"], "preview")
    E.wait_all(300)
    e = env["db"].get("export_jobs", j["id"])
    assert e["status"] == "done" and os.path.exists(e["output_path"])


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
                         capture_output=True, text=True).stdout
    st = json.loads(out)["streams"]
    return next(s for s in st if s["codec_type"] == "video"), next((s for s in st if s["codec_type"] == "audio"), None)


def test_export_quality_keeps_source_resolution_and_fps(project, assets, worker, env):
    """Ekspor re-encode mempertahankan resolusi & fps asli, H.264 high + AAC kualitas tinggi."""
    db = env["db"]
    assert db.get_settings()["export_crf"] <= 18 and db.get_settings()["export_preset"] in ("slow", "veryslow")
    db.set_settings({"export_mode": "reencode"})
    b = B.create_batch(project["id"], None, 10, "round_trip", 1)
    B.add_local_paths(b["id"], [str(assets["short720"])])
    B.start_batch(b["id"])
    wait_batch(b["id"])
    vid = B.list_items(b["id"])[0]["video_id"]
    f = T.create_video_output(vid, 10)
    T.update_final(f["id"], {"event_date": "2026-11-18", "event_time": "07:30",
                             "location_name": "Terminal Uji", "traffic_condition": "Lancar"})
    info = E.export_info(f["id"])
    assert info["output"]["width"] == 1280 and info["output"]["height"] == 720
    assert info["output"]["keeps_source_fps"] and info["mode"] == "reencode"
    assert info["quality"]["crf"] <= 18 and info["estimated_size_bytes"] > 0
    assert info["sources"][0]["fps"] == pytest.approx(25)
    j = E.start_export(f["id"], "final")
    E.wait_all(300)
    e = db.get("export_jobs", j["id"])
    assert e["status"] == "done", e["error"]
    v, a = _probe(e["output_path"])
    assert (v["width"], v["height"]) == (1280, 720)
    assert v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p" and v["profile"] == "High"
    num, den = (int(x) for x in v["avg_frame_rate"].split("/"))
    assert num / den == pytest.approx(25, abs=0.2)
    assert a["codec_name"] == "aac" and int(a["sample_rate"]) == 48000


def test_legacy_settings_upgraded_to_high_quality(env):
    db = env["db"]
    for k, v in {"export_crf": 20, "export_preset": "medium", "export_max_height": 1080, "use_gpu_encoder": True}.items():
        db.execute("UPDATE settings SET value_json=? WHERE key=?", (json.dumps(v), k))
    db.execute("DELETE FROM settings WHERE key='quality_profile_version'")
    db.ensure_default_settings()
    st = db.get_settings()
    assert st["export_crf"] == 16 and st["export_preset"] == "slow"
    assert st["export_max_height"] == 0 and st["use_gpu_encoder"] is False

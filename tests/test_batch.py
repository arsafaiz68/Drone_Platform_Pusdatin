"""Batch processing — uji #1, #2, #3, #10, #11, #12, #13, #14, #23, #24, #25."""
import threading
import time

import pytest

from app.services import ai_service, batch_service as B, hardware_service, timeline_service as T
from app.services.timeline_service import ValidationError
from conftest import wait_batch


def test_upload_single_video(project, assets, worker):
    b = B.create_batch(project["id"], None, 30, "round_trip", 2)
    with open(assets["roundtrip"], "rb") as fh:
        vids = B.add_uploaded_videos(b["id"], [("DJI_0001.MP4", fh)])
    assert vids[0]["filename"] == "DJI_0001.MP4" and vids[0]["duration"] == pytest.approx(40, abs=0.1)
    assert vids[0]["is_uploaded"] == 1
    B.start_batch(b["id"])
    done = wait_batch(b["id"])
    assert done["stats"]["completed"] == 1
    assert len(T.list_candidates(vids[0]["id"])) > 0


def test_upload_24_and_reject_25(project, assets):
    b = B.create_batch(project["id"], None, 30, "outbound", 1)
    handles = [open(assets["tiny"], "rb") for _ in range(24)]
    try:
        vids = B.add_uploaded_videos(b["id"], [(f"v{i:02d}.mp4", h) for i, h in enumerate(handles)])
    finally:
        for h in handles:
            h.close()
    assert len(vids) == 24
    with pytest.raises(ValidationError, match="Maksimal 24"):
        B.add_local_paths(b["id"], [str(assets["tiny"])])
    # batch baru dengan 25 sekaligus ditolak tanpa satu file pun ditambahkan
    b2 = B.create_batch(project["id"], None, 30, "outbound", 1)
    with pytest.raises(ValidationError):
        B.add_local_paths(b2["id"], [str(assets["tiny"])] * 25)
    assert B.get_batch(b2["id"])["stats"]["total"] == 0


@pytest.mark.parametrize("conc", [1, 2, 4])
def test_concurrency_limit(project, assets, worker, monkeypatch, conc):
    monkeypatch.setattr(hardware_service, "detect", lambda force=False: {
        "mode": "cpu", "max_concurrency": 4, "recommended_concurrency": 2, "nvenc_available": False,
        "device_name": "CPU"})
    active, peak, lock = [0], [0], threading.Lock()
    real = ai_service.analyze_video

    def slow(*a, **k):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        try:
            time.sleep(0.4)
            return real(*a, **k)
        finally:
            with lock:
                active[0] -= 1
    monkeypatch.setattr(ai_service, "analyze_video", slow)
    b = B.create_batch(project["id"], None, 30, "outbound", conc)
    B.add_local_paths(b["id"], [str(assets["tiny"])] * 8)
    B.start_batch(b["id"])
    done = wait_batch(b["id"])
    assert done["stats"]["completed"] == 8
    assert peak[0] <= conc
    if conc > 1:
        assert peak[0] >= 2  # benar-benar paralel


def test_failure_isolation(project, assets, worker):
    b = B.create_batch(project["id"], None, 30, "round_trip", 2)
    B.add_local_paths(b["id"], [str(assets["roundtrip"]), str(assets["broken"]), str(assets["tiny"])])
    B.start_batch(b["id"])
    done = wait_batch(b["id"])
    items = {i["filename"]: i for i in B.list_items(b["id"])}
    assert items["broken.mp4"]["status"] == "failed" and items["broken.mp4"]["error"]
    assert items["roundtrip.mp4"]["status"] == "review"
    assert items["tiny.mp4"]["status"] == "review"
    assert done["status"] == "review"


def test_pause_and_resume(project, assets, worker, monkeypatch):
    real = ai_service.analyze_video
    monkeypatch.setattr(ai_service, "analyze_video", lambda *a, **k: (time.sleep(0.3), real(*a, **k))[1])
    b = B.create_batch(project["id"], None, 30, "outbound", 1)
    B.add_local_paths(b["id"], [str(assets["tiny"])] * 5)
    B.start_batch(b["id"])
    time.sleep(0.5)
    B.pause_batch(b["id"])
    time.sleep(1.5)  # item yang sedang berjalan diselesaikan
    st1 = B.get_batch(b["id"])["stats"]
    assert st1["waiting"] >= 1 and st1["processing"] == 0
    time.sleep(1.0)
    assert B.get_batch(b["id"])["stats"]["waiting"] == st1["waiting"]  # tidak ada yang dimulai saat dijeda
    B.resume_batch(b["id"])
    done = wait_batch(b["id"])
    assert done["stats"]["completed"] == 5


def test_cancel_batch(project, assets, worker, monkeypatch):
    real = ai_service.analyze_video

    def slow(inp, det, progress=None, should_stop=None):
        for _ in range(50):
            if should_stop and should_stop():
                raise InterruptedError()
            time.sleep(0.05)
        return real(inp, det, progress, should_stop)
    monkeypatch.setattr(ai_service, "analyze_video", slow)
    b = B.create_batch(project["id"], None, 30, "outbound", 2)
    B.add_local_paths(b["id"], [str(assets["tiny"])] * 6)
    B.start_batch(b["id"])
    time.sleep(0.6)
    B.cancel_batch(b["id"])
    time.sleep(1.5)
    st = B.get_batch(b["id"])
    assert st["status"] == "cancelled"
    assert st["stats"]["by_status"]["cancelled"] >= 4
    assert st["stats"]["processing"] == 0


def test_recovery_after_restart(project, assets, env):
    db = env["db"]
    b = B.create_batch(project["id"], None, 30, "outbound", 2)
    vids = B.add_local_paths(b["id"], [str(assets["tiny"])] * 3)
    B.start_batch(b["id"])
    # simulasi crash: item terhenti di tengah analisis, ekspor terputus
    db.execute("UPDATE batch_items SET status='analyzing', progress=0.4 WHERE video_id=?", (vids[0]["id"],))
    db.execute("UPDATE batch_items SET status='review' WHERE video_id=?", (vids[1]["id"],))
    rec = B.recover_on_startup()
    assert rec["items_requeued"] == 1 and rec["batches_paused"] == 1
    bb = B.get_batch(b["id"])
    assert bb["status"] == "paused" and bb["recovered"] == 1
    items = {i["video_id"]: i for i in B.list_items(b["id"])}
    assert items[vids[0]["id"]]["status"] == "waiting"
    assert items[vids[1]["id"]]["status"] == "review"  # hasil yang sudah tersimpan tetap ada


def test_cpu_fallback_and_cuda_detection(monkeypatch):
    info = hardware_service.detect(force=True)
    assert info["mode"] in ("cpu", "cuda")
    # tanpa nvidia-smi -> CPU, aplikasi tetap jalan
    monkeypatch.setattr(hardware_service, "_nvidia_smi", lambda: [])
    info = hardware_service.detect(force=True)
    assert info["mode"] == "cpu" and not info["nvenc_available"]
    from app.services import export_service
    monkeypatch.setattr(hardware_service, "detect", lambda force=False: info)
    assert export_service.choose_encoder({"use_gpu_encoder": True}) == "libx264"
    # GPU NVIDIA + runtime CUDA -> mode cuda
    monkeypatch.undo()
    monkeypatch.setattr(hardware_service, "_nvidia_smi", lambda: [{"name": "NVIDIA RTX 3060", "memory_total_mb": 12288,
                                                                    "memory_used_mb": 100, "utilization_pct": 1, "driver": "560"}])
    monkeypatch.setattr(hardware_service, "_opencv_cuda", lambda: 1)
    monkeypatch.setattr(hardware_service, "_ffmpeg_encoders", lambda: {"h264_nvenc", "libx264"})
    info = hardware_service.detect(force=True)
    assert info["mode"] == "cuda" and info["cuda_available"] and info["nvenc_available"]
    assert info["device_name"] == "NVIDIA RTX 3060"
    hardware_service.detect(force=True)


def test_location_grouping_not_mixed(project, assets, worker):
    b = B.create_batch(project["id"], None, 30, "round_trip", 2)
    g1 = b["groups"][0]
    B.update_group(g1["id"], {"location_name": "Terminal Pulogebang", "traffic_condition": "Padat",
                              "event_date": "2026-11-18", "event_time": "07:30"})
    g2 = B.create_group(b["id"], "Lokasi 2", "Terminal Kampung Rambutan", "Ramai", "2026-11-18", "09:00")
    v1, v2 = B.add_local_paths(b["id"], [str(assets["roundtrip"]), str(assets["long"])])
    B.update_video(v2["id"], {"location_group_id": g2["id"]})
    B.start_batch(b["id"])
    wait_batch(b["id"], 240)
    f1 = T.create_final_video(project["id"], [g1["id"]], 30, "round_trip", batch_id=b["id"])
    f2 = T.create_final_video(project["id"], [g2["id"]], 30, "round_trip", batch_id=b["id"])
    assert {s["video_id"] for s in f1["segments"]} == {v1["id"]}
    assert {s["video_id"] for s in f2["segments"]} == {v2["id"]}
    assert f1["output_filename"] == "Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4"
    assert f2["output_filename"] == "Clipped_18.11_09.00_TerminalKampungRambutan_Ramai.mp4"
    with pytest.raises(ValidationError, match="tidak digabung otomatis"):
        T.create_final_video(project["id"], [g1["id"], g2["id"]], 30, "round_trip", batch_id=b["id"])
    fx = T.create_final_video(project["id"], [g1["id"], g2["id"]], 60, "round_trip", batch_id=b["id"],
                              cross_location=True, location_name="Pantauan Transportasi Nasional")
    assert {s["video_id"] for s in fx["segments"]} == {v1["id"], v2["id"]}
    assert "_PantauanTransportasiNasional_" in fx["output_filename"]

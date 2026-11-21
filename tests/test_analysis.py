"""Analisis video lokal — uji #4, #5, #6, #21, #22, #23 (CPU)."""
from app.core.config import DEFAULT_SETTINGS
from app.core.templates_config import get_template, resolve_route
from app.services import ai_service as A
from app.services import video_service as V


def run(path, code="terminal", mode="round_trip", mapping=None, direction=None):
    t = get_template(code)
    meta = V.probe(path)
    inp = A.AnalysisInput(1, str(path), meta["duration"], t, resolve_route(t), mode, mapping, direction,
                          dict(DEFAULT_SETTINGS))
    return A.analyze_video(inp, A.Detector())


def test_probe_metadata(assets):
    m = V.probe(assets["short720"])
    assert (m["width"], m["height"]) == (1280, 720)
    assert abs(m["fps"] - 25) < 0.01
    assert m["audio_codec"] == "aac"
    assert m["creation_time"].startswith("2026-11-18T00:30")
    m2 = V.probe(assets["roundtrip"])
    assert m2["audio_codec"] is None and m2["creation_time"] is None


def test_round_trip_turnaround_detected(assets):
    res = run(assets["roundtrip"])
    tr = res["turnaround"]
    assert tr["found"] and abs(tr["time"] - 20.0) < 2.0, tr
    assert res["is_heuristic"]  # tanpa model -> ditandai heuristik
    dirs = {c["direction"] for c in res["candidates"]}
    assert dirs == {"outbound", "return"}
    # segmen pergi dan kembali tidak tercampur
    for c in res["candidates"]:
        if c["direction"] == "outbound":
            assert c["end"] <= tr["time"] + 0.01
        else:
            assert c["start"] >= tr["time"] - 0.01
    assert all(c["needs_verification"] for c in res["candidates"])
    assert all(c["confidence"] < 0.5 for c in res["candidates"])  # tidak mengklaim akurasi tinggi
    assert all(c["traffic_suggestion"] is None for c in res["candidates"])  # tanpa model: tidak ada klaim lalin


def test_outbound_only_mode(assets):
    res = run(assets["roundtrip"], mode="outbound")
    assert all(c["direction"] == "outbound" for c in res["candidates"])
    assert max(c["end"] for c in res["candidates"]) <= 22.5
    res2 = run(assets["oneway"], mode="outbound")
    pts = {c["point_code"] for c in res2["candidates"]}
    assert pts == {"1", "2", "3"}


def test_short_video(assets):
    res = run(assets["tiny"], mode="round_trip")
    assert res["duration"] >= 2.9
    assert res["candidates"] is not None  # tidak crash meskipun sangat pendek
    assert res["turnaround"]["found"] is False


def test_long_video(assets):
    res = run(assets["long"], code="jalan_tol")
    assert abs(res["turnaround"]["time"] - 120) < 8, res["turnaround"]
    assert {c["point_code"] for c in res["candidates"]} == {"1", "2"}


def test_different_resolution_video(assets):
    res = run(assets["short720"], code="stasiun", mode="outbound")
    assert res["samples"] >= 20
    assert len(res["candidates"]) >= 1


def test_manual_point_mapping(assets):
    res = run(assets["oneway"], code="gerbang_tol", mode="round_trip", mapping=["4"], direction="return")
    assert {c["point_code"] for c in res["candidates"]} == {"4"}
    assert {c["direction"] for c in res["candidates"]} == {"return"}
    assert all(not c["needs_verification"] and c["confidence"] == 1.0 for c in res["candidates"])
    assert res["point_identification"] == "manual"


def test_gerbang_tol_round_trip_zones(assets):
    res = run(assets["roundtrip"], code="gerbang_tol")
    out_codes = [z["point_code"] for z in res["zones"] if z["direction"] == "outbound"]
    ret_codes = [z["point_code"] for z in res["zones"] if z["direction"] == "return"]
    assert out_codes == ["H", "1", "2", "3", "4", "5"]
    assert ret_codes == ["5", "4", "3", "2", "1", "H"]

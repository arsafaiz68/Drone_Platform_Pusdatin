"""Seleksi momen & alokasi durasi — uji #7, #8, #9."""
import random

import pytest

from app.core.config import DEFAULT_SETTINGS
from app.core.templates_config import get_template, resolve_route
from app.services.selection_service import is_duplicate, select_segments


def make_cands(template, n_per=3, seed=1, length=(8, 18)):
    rnd = random.Random(seed)
    out, i = [], 0
    for d in ("outbound", "return"):
        for p in template["points"]:
            if p["code"] == "H":
                continue
            for _ in range(n_per):
                i += 1
                st = rnd.uniform(0, 20)
                out.append(dict(id=i, video_id=i, point_code=p["code"], direction=d, start=st,
                                end=st + rnd.uniform(*length), quality_score=rnd.random(),
                                relevance_score=rnd.random(), confidence=0.35, features={}))
    return out


@pytest.mark.parametrize("code", ["pelabuhan", "terminal", "stasiun", "gerbang_tol", "jalan_tol", "jalan_arteri", "rest_area"])
@pytest.mark.parametrize("target", [30, 60])
@pytest.mark.parametrize("mode", ["outbound", "round_trip"])
def test_total_duration_matches_target(code, target, mode):
    t = get_template(code)
    res = select_segments(make_cands(t), t, resolve_route(t), mode, target, DEFAULT_SETTINGS)
    segs = res["segments"]
    total = sum(s["allocated"] for s in segs)
    assert abs(total - target) < 0.05, res["report"]
    assert res["report"]["meets_target"]
    # durasi 30/60 berlaku untuk total, BUKAN untuk tiap potongan
    assert all(s["allocated"] < target for s in segs)
    # seluruh titik terwakili
    dirs = ["outbound"] + (["return"] if mode == "round_trip" else [])
    needed = {(p["code"], d) for p in t["points"] if p["code"] != "H" for d in dirs}
    got = {(s["point_code"], s["direction"]) for s in segs}
    assert needed <= got
    # tidak ada arah kembali pada mode pergi saja
    if mode == "outbound":
        assert all(s["direction"] == "outbound" for s in segs)
    # tidak ada adegan duplikat / tumpang tindih
    for a in range(len(segs)):
        for b in range(a + 1, len(segs)):
            sa, sb = segs[a], segs[b]
            if sa["video_id"] == sb["video_id"]:
                assert min(sa["end"], sb["end"]) - max(sa["start"], sb["start"]) <= 0.25


def test_template_order_preserved():
    t = get_template("terminal")
    res = select_segments(make_cands(t), t, resolve_route(t), "round_trip", 60, DEFAULT_SETTINGS)
    order = [(s["direction"], s["point_code"]) for s in res["segments"] if s["role"] == "point"]
    assert order == [("outbound", "1"), ("outbound", "2"), ("outbound", "3"),
                     ("return", "3"), ("return", "2"), ("return", "1")]


def test_allocation_not_uniform_and_weighted():
    t = get_template("terminal")
    cands = []
    for i, p in enumerate(["1", "2", "3"]):
        cands.append(dict(id=i + 1, video_id=i + 1, point_code=p, direction="outbound", start=0, end=30,
                          quality_score=0.6, relevance_score=0.6, confidence=0.35, features={}))
    res = select_segments(cands, t, resolve_route(t), "outbound", 30, DEFAULT_SETTINGS)
    alloc = {s["point_code"]: s["allocated"] for s in res["segments"]}
    assert alloc["2"] > alloc["3"] > alloc["1"]  # bobot kepentingan 1.6 > 1.2 > 1.0
    assert abs(sum(alloc.values()) - 30) < 0.05


def test_insufficient_footage_warns_and_no_duplicates():
    t = get_template("terminal")
    cands = [dict(id=1, video_id=1, point_code="1", direction="outbound", start=0, end=5, quality_score=.5,
                  relevance_score=.5, confidence=.3, features={}),
             dict(id=2, video_id=1, point_code="2", direction="outbound", start=10, end=16, quality_score=.5,
                  relevance_score=.5, confidence=.3, features={})]
    res = select_segments(cands, t, resolve_route(t), "outbound", 60, DEFAULT_SETTINGS)
    total = res["report"]["total"]
    assert total == pytest.approx(11, abs=0.05)
    assert not res["report"]["meets_target"]
    assert any("tidak memiliki footage" in w for w in res["report"]["warnings"])  # titik 3
    assert any("Durasi aktual" in w for w in res["report"]["warnings"])
    assert len(res["segments"]) == 2


def test_duplicate_detection_by_histogram():
    h = [0.1] * 128
    a = dict(video_id=1, start=0, end=5, point_code="1", direction="outbound", features={"hist": h})
    b = dict(video_id=2, start=0, end=5, point_code="1", direction="outbound", features={"hist": h})
    assert is_duplicate(a, b)
    c = dict(video_id=1, start=10, end=15, point_code="1", direction="outbound", features={})
    assert not is_duplicate(a, c)


def test_many_points_short_target_still_representative():
    t = get_template("gerbang_tol")
    res = select_segments(make_cands(t, n_per=1, length=(3, 4)), t, resolve_route(t), "round_trip", 30, DEFAULT_SETTINGS)
    assert len({(s["point_code"], s["direction"]) for s in res["segments"]}) == 10

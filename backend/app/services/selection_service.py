"""Seleksi momen terbaik dan alokasi durasi video hasil (10–60 detik, kelipatan 5).

Skema platform: SATU video sumber menghasilkan SATU video hasil. Durasi target
(10–60 dtk, kelipatan 5) berlaku untuk setiap video hasil, yaitu total potongan yang diambil
dari video sumber tersebut. Setiap potongan mendapat alokasi proporsional menurut
bobot kepentingan titik, relevansi (aktivitas/kepadatan), kualitas visual, dan
keterwakilan titik yang terekam. Bila kandidat AI tidak cukup, sisa durasi diisi
dari bagian lain video yang sama (``fill_from_source``) tanpa adegan berulang.
"""
from __future__ import annotations

import math

import numpy as np

from ..core.templates_config import point_map

EPS = 1e-6


def candidate_score(c: dict) -> float:
    q = c.get("quality_score") or 0
    r = c.get("relevance_score") or 0
    conf = c.get("confidence") or 0.3
    s = 0.45 * q + 0.40 * r + 0.15 * conf
    if c.get("verified"):
        s += 0.15  # footage yang sudah diverifikasi operator diprioritaskan
    blur = ((c.get("features") or {}).get("blur_fraction") or 0)
    return s - 0.3 * blur


def _hist(c: dict):
    h = (c.get("features") or {}).get("hist")
    if not h:
        return None
    v = np.asarray(h, float)
    n = np.linalg.norm(v)
    return v / n if n > 0 else None


def is_duplicate(a: dict, b: dict, sim_threshold: float = 0.985) -> bool:
    if a["video_id"] == b["video_id"]:
        overlap = min(a["end"], b["end"]) - max(a["start"], b["start"])
        if overlap > 0.25:
            return True
    ha, hb = _hist(a), _hist(b)
    if ha is not None and hb is not None and float(ha @ hb) > sim_threshold \
            and a.get("point_code") == b.get("point_code") and a.get("direction") == b.get("direction"):
        return True
    return False


def water_fill(budget: float, weights: list[float], mins: list[float], caps: list[float]) -> list[float]:
    """Bagi ``budget`` proporsional ``weights`` dengan batas bawah dan batas atas."""
    n = len(weights)
    alloc = [0.0] * n
    active = [i for i in range(n) if caps[i] > EPS]
    # pastikan batas minimum bila anggaran cukup
    need_min = sum(min(mins[i], caps[i]) for i in active)
    if need_min > budget + EPS:
        # anggaran tidak cukup untuk semua minimum: utamakan bobot tertinggi
        order = sorted(active, key=lambda i: -weights[i])
        rem = budget
        for i in order:
            a = min(mins[i], caps[i], rem)
            if a >= min(mins[i], caps[i]) - EPS:
                alloc[i] = a
                rem -= a
        return alloc
    for i in active:
        alloc[i] = min(mins[i], caps[i])
    rem = budget - sum(alloc)
    free = [i for i in active if alloc[i] < caps[i] - EPS]
    while rem > EPS and free:
        wsum = sum(weights[i] for i in free) or len(free)
        give = {i: rem * (weights[i] / wsum if wsum else 1 / len(free)) for i in free}
        rem = 0.0
        nxt = []
        for i in free:
            room = caps[i] - alloc[i]
            g = give[i]
            if g >= room - EPS:
                alloc[i] = caps[i]
                rem += g - room
            else:
                alloc[i] += g
                nxt.append(i)
        free = nxt
    return alloc


def _sub_window(c: dict, length: float) -> tuple[float, float]:
    span = c["end"] - c["start"]
    if length >= span - EPS:
        return c["start"], c["end"]
    mid = c["start"] + span / 2
    a = max(c["start"], mid - length / 2)
    return round(a, 3), round(a + length, 3)


def build_slots(template: dict, route: dict, trip_mode: str, include_home: bool) -> list[dict]:
    pmap = point_map(template)
    slots = []
    seqs = [("outbound", route["outbound"])]
    if trip_mode == "round_trip":
        seqs.append(("return", route["return"]))
    for direction, seq in seqs:
        seen = set()
        for code in seq:
            if code == "H" and not include_home:
                continue
            if code in seen:
                continue
            seen.add(code)
            p = pmap[code]
            slots.append({"key": f"{direction}:{code}", "direction": direction, "point_code": code,
                          "point_name": p["name"], "importance": p.get("importance", 1.0)})
    return slots


def select_segments(candidates: list[dict], template: dict, route: dict, trip_mode: str,
                    target: float, settings: dict, available_only: bool = False) -> dict:
    """Pilih dan alokasikan potongan. ``candidates`` wajib memuat ``video_id``.

    ``available_only``: hanya titik yang memiliki kandidat yang dijadikan slot (dipakai untuk
    video hasil per video sumber, karena satu rekaman belum tentu mencakup seluruh titik).
    """
    min_len = float(settings.get("min_segment_seconds", 3.0))
    max_len = float(settings.get("max_segment_seconds", 20.0))
    support_share = float(settings.get("support_share", 0.2))
    include_home = bool(settings.get("include_home_point", False))
    slots = build_slots(template, route, trip_mode, include_home)
    warnings: list[str] = []

    by_slot: dict[str, list[dict]] = {s["key"]: [] for s in slots}
    for c in candidates:
        if c.get("deleted"):
            continue
        key = f"{c['direction']}:{c['point_code']}"
        if key in by_slot:
            by_slot[key].append(c)
    for key in by_slot:
        by_slot[key].sort(key=candidate_score, reverse=True)
    if available_only:
        slots = [s for s in slots if by_slot[s["key"]]]

    # ---------------- footage utama per titik (satu terbaik, bebas duplikat)
    chosen: list[dict] = []
    primary: dict[str, dict] = {}
    for s in slots:
        for c in by_slot[s["key"]]:
            if not any(is_duplicate(c, o) for o in chosen):
                primary[s["key"]] = c
                chosen.append(c)
                break
    missing = [s for s in slots if s["key"] not in primary]
    for s in missing:
        warnings.append(f"Titik {s['point_code']} ({'pergi' if s['direction'] == 'outbound' else 'kembali'}) "
                        "tidak memiliki footage yang memadai.")

    # ---------------- kandidat pendukung (cadangan, tidak duplikat)
    support_pool: list[tuple[dict, dict]] = []
    for s in slots:
        for c in by_slot[s["key"]]:
            if c is primary.get(s["key"]):
                continue
            support_pool.append((s, c))
    support_pool.sort(key=lambda sc: candidate_score(sc[1]), reverse=True)

    def length(c):
        return min(max_len, c["end"] - c["start"])

    present = [s for s in slots if s["key"] in primary]
    weights = []
    for s in present:
        c = primary[s["key"]]
        rel = c.get("relevance_score") or 0.5
        q = c.get("quality_score") or 0.5
        weights.append(s["importance"] * (0.6 + 0.4 * rel) * (0.7 + 0.3 * q))
    caps = [length(primary[s["key"]]) for s in present]
    mins = [min_len] * len(present)

    support_budget = target * support_share if support_pool else 0.0
    need = sum(min(m, cp) for m, cp in zip(mins, caps))
    if need > target - support_budget:
        # keterwakilan seluruh titik lebih penting daripada momen pendukung
        support_budget = max(0.0, target - need)
        if support_budget < min_len:
            support_budget = 0.0
    if need > target and present:
        # terlalu banyak titik untuk durasi minimum: perkecil batas minimum
        per = max(1.5, target / len(present))
        mins = [per] * len(present)
        warnings.append(f"Jumlah titik banyak untuk durasi {target:.0f} dtk; setiap potongan dipersingkat "
                        f"menjadi ±{per:.1f} dtk agar semua titik terwakili.")
    main_budget = target - support_budget
    alloc = water_fill(main_budget, weights, mins, caps)
    leftover = target - sum(alloc)

    # ---------------- isi momen pendukung
    support_sel: list[tuple[dict, dict, float]] = []
    for s, c in support_pool:
        if leftover < min_len - EPS:
            break
        if any(is_duplicate(c, o) for o in chosen):
            continue
        a = min(length(c), leftover)
        if a < min_len - EPS:
            continue
        # jangan biarkan satu momen pendukung mengambil seluruh sisa
        a = min(a, max(min_len, target * support_share / 2 + min_len))
        support_sel.append((s, c, a))
        chosen.append(c)
        leftover -= a
    # sisa anggaran -> perpanjang footage utama sampai batas panjangnya
    if leftover > EPS and present:
        room = [caps[i] - alloc[i] for i in range(len(present))]
        extra = water_fill(leftover, weights, [0.0] * len(present), room)
        alloc = [a + e for a, e in zip(alloc, extra)]
        leftover = target - sum(alloc) - sum(a for _, _, a in support_sel)
    if leftover > EPS and support_sel:
        # perpanjang momen pendukung
        for i, (s, c, a) in enumerate(support_sel):
            g = min(length(c) - a, leftover)
            if g > EPS:
                support_sel[i] = (s, c, a + g)
                leftover -= g
    # sisa kecil (< durasi minimum): pakai kandidat lain yang belum terpakai, minimal 1,5 dtk
    for s, c in support_pool:
        if leftover < 1.5:
            break
        if any(is_duplicate(c, o) for o in chosen):
            continue
        a = min(length(c), leftover)
        if a < 1.5:
            continue
        support_sel.append((s, c, a))
        chosen.append(c)
        leftover -= a

    # ---------------- susun timeline berdasarkan urutan template
    slot_order = {s["key"]: i for i, s in enumerate(slots)}
    items = []
    for s, a in zip(present, alloc):
        if a < 0.5:
            continue
        c = primary[s["key"]]
        items.append((slot_order[s["key"]], 0, c["start"], s, c, a, "point"))
    for s, c, a in support_sel:
        items.append((slot_order[s["key"]], 1, c["start"], s, c, a, "support"))
    items.sort(key=lambda x: (x[0], x[1], x[2]))

    # pembulatan 0.1 dtk dan koreksi agar total tepat
    segs = []
    for _, _, _, s, c, a, role in items:
        segs.append({"slot": s, "cand": c, "alloc": math.floor(a * 10 + 1e-6) / 10, "role": role})
    total = sum(x["alloc"] for x in segs)
    diff = round(target - total, 3)
    if segs and abs(diff) > EPS:
        for x in sorted(segs, key=lambda x: -(length(x["cand"]) - x["alloc"])):
            room = length(x["cand"]) - x["alloc"]
            if diff > 0 and room >= diff - EPS:
                x["alloc"] = round(x["alloc"] + diff, 3)
                diff = 0
                break
    total = round(sum(x["alloc"] for x in segs), 3)

    out = []
    for i, x in enumerate(segs):
        c = x["cand"]
        a, b = _sub_window(c, x["alloc"])
        out.append({
            "order_index": i,
            "candidate_id": c.get("id"),
            "video_id": c["video_id"],
            "point_code": c["point_code"],
            "direction": c["direction"],
            "role": x["role"],
            "start": a,
            "end": b,
            "allocated": round(b - a, 3),
        })
    meets = abs(total - target) < 0.05
    if not meets:
        warnings.append(f"Footage tidak cukup untuk mencapai {target:.0f} dtk tanpa adegan duplikat. "
                        f"Durasi aktual {total:.1f} dtk (tetap dapat diekspor).")
    report = {
        "target": target,
        "total": total,
        "meets_target": meets,
        "slots": [{
            "key": s["key"], "point_code": s["point_code"], "direction": s["direction"],
            "point_name": s["point_name"], "candidates_available": len(by_slot[s["key"]]),
            "allocated": round(sum(o["allocated"] for o in out
                                   if o["point_code"] == s["point_code"] and o["direction"] == s["direction"]), 2),
            "missing": s["key"] not in primary,
        } for s in slots],
        "warnings": warnings,
    }
    return {"segments": out, "report": report}


def _free_intervals(used: list[tuple[float, float]], duration: float) -> list[list[float]]:
    free, cur = [], 0.0
    for a, b in sorted(used):
        if a - cur > EPS:
            free.append([cur, a])
        cur = max(cur, b)
    if duration - cur > EPS:
        free.append([cur, duration])
    return free


def fill_from_source(segments: list[dict], video_id: int, duration: float, target: float,
                     settings: dict, exclude: list[tuple[float, float]] | None = None) -> tuple[list[dict], list[str]]:
    """Lengkapi potongan satu video sumber sampai durasi target.

    * Video sumber <= target: seluruh video dipakai (satu potongan), durasi hasil = durasi sumber.
    * Kandidat AI kurang: sisa durasi diambil dari bagian video yang belum terpakai, di tengah
      celah terpanjang terlebih dahulu sehingga potongan tambahan tersebar merata, tanpa tumpang
      tindih dengan potongan lain (tidak ada adegan berulang).
    * ``exclude``: rentang yang ditolak operator (kandidat dihapus) tidak dipakai sebagai pengisi.
    Hasil diurutkan menurut waktu rekaman (kronologis = urutan terbang drone).
    """
    warnings: list[str] = []
    min_len = float(settings.get("min_segment_seconds", 3.0))
    max_len = float(settings.get("max_segment_seconds", 20.0))
    duration = float(duration or 0)
    segs = [dict(s) for s in segments]
    if duration <= 0:
        return segs, warnings
    if duration <= target + 0.05:
        warnings.append(f"Durasi video sumber ({duration:.1f} dtk) tidak lebih panjang dari target "
                        f"{target:.0f} dtk; seluruh video dipakai.")
        segs = [{"candidate_id": None, "video_id": video_id, "point_code": None, "direction": None,
                 "role": "support", "start": 0.0, "end": round(duration, 3), "allocated": round(duration, 3)}]
    else:
        total = sum(s["end"] - s["start"] for s in segs)
        remaining = round(target - total, 3)
        free = _free_intervals([(s["start"], s["end"]) for s in segs] + list(exclude or []), duration)
        added = 0
        while remaining > 0.05 and free:
            free.sort(key=lambda iv: iv[1] - iv[0], reverse=True)
            a, b = free.pop(0)
            span = b - a
            piece = min(remaining, max_len, span)
            if piece < min(min_len, remaining) - EPS:
                if span < 0.5:
                    continue
                piece = min(span, remaining)  # sisa kecil: pakai yang tersedia
            mid = a + span / 2
            s0 = max(a, mid - piece / 2)
            s1 = min(b, s0 + piece)
            segs.append({"candidate_id": None, "video_id": video_id, "point_code": None, "direction": None,
                         "role": "support", "start": round(s0, 3), "end": round(s1, 3),
                         "allocated": round(s1 - s0, 3)})
            remaining = round(remaining - (s1 - s0), 3)
            added += 1
            if s0 - a > 0.5:
                free.append([a, s0])
            if b - s1 > 0.5:
                free.append([s1, b])
        if added:
            warnings.append(f"{added} potongan tambahan diambil dari bagian lain video sumber untuk "
                            f"mencapai {target:.0f} dtk.")
    segs.sort(key=lambda s: s["start"])
    for i, s in enumerate(segs):
        s["order_index"] = i
    return segs, warnings


def recommend_additional(candidates: list[dict], used: list[dict], remaining: float,
                         settings: dict, limit: int = 5) -> list[dict]:
    """Rekomendasi kandidat tambahan bila total durasi kurang dari target."""
    if remaining <= EPS:
        return []
    min_len = float(settings.get("min_segment_seconds", 3.0))
    pool = [c for c in candidates if not c.get("deleted")
            and not any(is_duplicate(c, u) for u in used)
            and (c["end"] - c["start"]) >= min(min_len, remaining)]
    pool.sort(key=candidate_score, reverse=True)
    return pool[:limit]

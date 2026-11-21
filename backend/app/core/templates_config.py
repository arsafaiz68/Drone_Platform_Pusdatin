"""Konfigurasi terpusat tujuh template pemantauan (pelabuhan, terminal, stasiun, gerbang tol,
jalan tol, jalan arteri, tempat istirahat/rest area).

Struktur setiap template:
  code            : kode unik (dipakai di database dan API)
  name            : nama tampilan
  location_type   : jenis lokasi (masuk ke metadata video final)
  points          : daftar titik. ``importance`` = bobot alokasi durasi,
                    ``zone_weight`` = bobot panjang zona temporal saat estimasi
                    tanpa GPS (Home Point lebih pendek).
  route_outbound  : urutan perjalanan pergi
  route_return    : urutan perjalanan kembali
  turnarounds     : titik tempat drone melakukan putar balik (berurutan)

Untuk menambah template baru cukup tambahkan entri ke ``TEMPLATES``; database
akan disinkronkan otomatis saat aplikasi dijalankan.
"""
from __future__ import annotations

import copy
import re

HOME = {"code": "H", "number": 0, "name": "Home Point",
        "description": "Titik awal penerbangan (Home Point).",
        "importance": 0.3, "zone_weight": 0.5}


def _pts(*items):
    pts = [dict(HOME)]
    for i, (name, desc, importance) in enumerate(items, start=1):
        pts.append({"code": str(i), "number": i, "name": name, "description": desc,
                    "importance": importance, "zone_weight": 1.0})
    return pts


TEMPLATES = [
    {
        "code": "pelabuhan",
        "name": "Pelabuhan",
        "location_type": "Pelabuhan",
        "description": ("Pemantauan pelabuhan penyeberangan: jalan akses & antrean menuju pelabuhan, gerbang/loket "
                        "tiket, area parkir/kantong penyangga kendaraan, dermaga dan area muat kapal."),
        "points": _pts(
            ("Jalan akses / antrean menuju pelabuhan", "Memantau antrean kendaraan di jalan akses pelabuhan.", 1.2),
            ("Gerbang masuk / loket tiket", "Memantau antrean pada gerbang dan loket tiket.", 1.3),
            ("Area parkir / kantong penyangga", "Memantau kepadatan kendaraan yang menunggu kapal.", 1.6),
            ("Dermaga / area muat kapal", "Memantau proses muat kendaraan dan penumpang ke kapal.", 1.4),
        ),
        "route_outbound": ["H", "1", "2", "3", "4"],
        "route_return": ["4", "3", "2", "1", "H"],
        "turnarounds": ["4"],
    },
    {
        "code": "terminal",
        "name": "Terminal",
        "location_type": "Terminal",
        "description": "Pemantauan terminal bus: jalan akses, area penyangga/halaman, jalan keluar.",
        "points": _pts(
            ("Jalan akses terminal", "Memantau kendaraan yang bergerak menuju terminal.", 1.0),
            ("Area penyangga / halaman terminal", "Memantau bus, kendaraan, dan kepadatan penumpang.", 1.6),
            ("Jalan keluar terminal", "Memantau arus kendaraan yang meninggalkan terminal.", 1.2),
        ),
        "route_outbound": ["H", "1", "2", "3"],
        "route_return": ["3", "2", "1", "H"],
        "turnarounds": ["3"],
    },
    {
        "code": "stasiun",
        "name": "Stasiun",
        "location_type": "Stasiun",
        "description": "Pemantauan stasiun: jalan akses, area drop-off/halaman, jalan keluar.",
        "points": _pts(
            ("Jalan akses stasiun", "Memantau kendaraan menuju stasiun.", 1.0),
            ("Area drop-off dan halaman stasiun", "Memantau aktivitas penumpang dan kendaraan.", 1.6),
            ("Jalan keluar stasiun", "Memantau arus kendaraan keluar stasiun.", 1.2),
        ),
        "route_outbound": ["H", "1", "2", "3"],
        "route_return": ["3", "2", "1", "H"],
        "turnarounds": ["3"],
    },
    {
        "code": "gerbang_tol",
        "name": "Gerbang Tol",
        "location_type": "Gerbang Tol",
        "description": ("Pemantauan gerbang tol: persimpangan, gerbang, simpang susun, "
                        "jalan simpang kiri dan kanan (±500 m). Putar balik di titik 4 dan titik 5."),
        "points": _pts(
            ("Persimpangan menuju gerbang tol", "Memantau arus menuju gerbang tol.", 1.0),
            ("Area gerbang tol", "Memantau antrean pada gardu tol.", 1.6),
            ("Simpang susun / interchange", "Memantau pergerakan pada interchange.", 1.2),
            ("Jalan simpang kiri (±500 m)", "Cakupan sekitar 500 meter jalan simpang sebelah kiri. Titik putar balik.", 1.0),
            ("Jalan simpang kanan (±500 m)", "Cakupan sekitar 500 meter jalan simpang sebelah kanan. Titik putar balik.", 1.0),
        ),
        "route_outbound": ["H", "1", "2", "3", "4", "5"],
        "route_return": ["5", "4", "3", "2", "1", "H"],
        # Dua instruksi putar balik wajib dipertahankan: titik 4 dan titik 5.
        "turnarounds": ["4", "5"],
    },
    {
        "code": "jalan_tol",
        "name": "Jalan Tol",
        "location_type": "Jalan Tol",
        "description": "Pemantauan antrean di jalan tol: ekor dan kepala kemacetan/bottleneck.",
        "points": _pts(
            ("Ekor antrean / kemacetan", "Titik awal antrean atau ekor kemacetan.", 1.2),
            ("Kepala antrean / bottleneck", "Titik akhir antrean, termasuk lokasi bottleneck.", 1.5),
        ),
        "route_outbound": ["H", "1", "2"],
        "route_return": ["2", "1", "H"],
        "turnarounds": ["2"],
    },
    {
        "code": "jalan_arteri",
        "name": "Jalan Arteri",
        "location_type": "Jalan Arteri",
        "description": "Pemantauan jalan arteri: ekor kemacetan dan kepala kemacetan/persimpangan/pasar.",
        "points": _pts(
            ("Ekor kemacetan", "Titik ekor kemacetan.", 1.2),
            ("Kepala kemacetan / persimpangan / pasar", "Titik kepala kemacetan, persimpangan, atau kawasan pasar.", 1.5),
        ),
        "route_outbound": ["H", "1", "2"],
        "route_return": ["2", "1", "H"],
        "turnarounds": ["2"],
    },
    {
        "code": "rest_area",
        "name": "Tempat Istirahat Jalan Tol",
        "location_type": "Rest Area",
        "description": "Pemantauan tempat istirahat: antrean masuk, okupansi area, arus keluar.",
        "points": _pts(
            ("±500 m sebelum pintu masuk", "Memantau antrean kendaraan menuju tempat istirahat.", 1.1),
            ("Area tempat istirahat", "Memantau okupansi parkir dan fasilitas.", 1.6),
            ("±500 m dari akses keluar", "Memantau arus kendaraan kembali ke jalan tol.", 1.1),
        ),
        "route_outbound": ["H", "1", "2", "3"],
        "route_return": ["3", "2", "1", "H"],
        "turnarounds": ["3"],
    },
]

_BY_CODE = {t["code"]: t for t in TEMPLATES}


def get_template(code: str) -> dict | None:
    t = _BY_CODE.get(code)
    return copy.deepcopy(t) if t else None


def all_templates() -> list[dict]:
    return copy.deepcopy(TEMPLATES)


def point_map(template: dict) -> dict[str, dict]:
    return {p["code"]: p for p in template["points"]}


def resolve_route(template: dict, custom_route: dict | None = None) -> dict:
    """Gabungkan rute default template dengan konfigurasi lintasan operator."""
    route = {
        "outbound": list(template["route_outbound"]),
        "return": list(template["route_return"]),
        "turnarounds": list(template["turnarounds"]),
    }
    if custom_route:
        valid = set(point_map(template))
        for key in ("outbound", "return", "turnarounds"):
            seq = custom_route.get(key)
            if seq:
                seq = [str(s) for s in seq]
                bad = [s for s in seq if s not in valid]
                if bad:
                    raise ValueError(f"Titik tidak dikenal pada lintasan '{key}': {bad}")
                route[key] = seq
    return route


# Deteksi jenis lokasi dari nama lokasi laporan (urutan penting: yang paling spesifik dulu).
_DETECT_RULES = [
    ("pelabuhan", r"\bpel(abuhan)?\b|\bport\b|dermaga|penyeberangan|\basdp\b|\bbakauheni\b|\bmerak\b|\bketapang\b|\bgilimanuk\b"),
    ("rest_area", r"\brest\s*area\b|\bra\b|tempat istirahat|\btip\b|\btipl?\b"),
    ("gerbang_tol", r"\bgt\b|gerbang\s*tol|\bgerbang\b|\bgardu\b"),
    ("terminal", r"\bterminal\b|\bterm\b"),
    ("stasiun", r"\bstasiun\b|\bst\b|\bstation\b"),
    ("jalan_tol", r"\btol\b|\bkm\s*\d|\bjalan bebas hambatan\b"),
    ("jalan_arteri", r"\bjalan\b|\bjl\b|\barteri\b|\bsimpang\b|\bpasar\b|\bjalur\b|\bpantura\b|\bbundaran\b"),
]


def detect_template(location_name: str | None) -> str | None:
    """Tebak kode template dari nama lokasi, mis. "Pel. Merak" -> pelabuhan, "GT Cikatama" -> gerbang_tol,
    "RA KM 57 Tol Jakarta-Cikampek" -> rest_area. None bila tidak dikenali."""
    if not location_name:
        return None
    text = re.sub(r"[._/-]+", " ", str(location_name).lower())
    for code, pattern in _DETECT_RULES:
        if re.search(pattern, text):
            return code
    return None


def route_text(seq: list[str]) -> str:
    return " → ".join(seq)

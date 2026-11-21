"""Template (6) dan standar penamaan file — uji #26, #27, #28, #29, #30."""
from datetime import datetime

import pytest

from app.core.templates_config import all_templates, get_template, resolve_route
from app.services import naming_service as N


def test_six_templates_and_routes():
    ts = {t["code"]: t for t in all_templates()}
    assert list(ts) == ["pelabuhan", "terminal", "stasiun", "gerbang_tol", "jalan_tol", "jalan_arteri", "rest_area"]
    assert ts["terminal"]["route_outbound"] == ["H", "1", "2", "3"]
    assert ts["terminal"]["route_return"] == ["3", "2", "1", "H"]
    assert ts["stasiun"]["route_outbound"] == ["H", "1", "2", "3"]
    assert ts["gerbang_tol"]["route_outbound"] == ["H", "1", "2", "3", "4", "5"]
    assert ts["gerbang_tol"]["route_return"] == ["5", "4", "3", "2", "1", "H"]
    # dua instruksi putar balik dipertahankan
    assert ts["gerbang_tol"]["turnarounds"] == ["4", "5"]
    for code in ("jalan_tol", "jalan_arteri"):
        assert ts[code]["route_outbound"] == ["H", "1", "2"]
        assert ts[code]["route_return"] == ["2", "1", "H"]
    assert ts["rest_area"]["route_outbound"] == ["H", "1", "2", "3"]
    for t in ts.values():
        codes = [p["code"] for p in t["points"]]
        assert codes[0] == "H"
        assert set(t["route_outbound"]) <= set(codes)


def test_templates_synced_to_db(env):
    db = env["db"]
    assert db.scalar("SELECT COUNT(*) FROM templates") == 7
    assert db.scalar("SELECT COUNT(*) FROM template_points WHERE template_code='gerbang_tol'") == 6


def test_custom_route_validation():
    t = get_template("gerbang_tol")
    r = resolve_route(t, {"outbound": ["H", "1", "2", "3", "4", "3", "5"]})
    assert r["outbound"][-1] == "5" and r["turnarounds"] == ["4", "5"]
    with pytest.raises(ValueError):
        resolve_route(t, {"outbound": ["H", "9"]})


def test_filename_format():
    dt = datetime(2026, 11, 18, 7, 30)
    assert N.build_filename(dt, "Terminal Pulogebang", "Padat") == "Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4"
    assert N.build_filename(datetime(2026, 11, 18, 8, 15), "GT Cikampek", "Lancar") == "Clipped_18.11_08.15_GTCikampek_Lancar.mp4"
    assert N.build_filename(datetime(2026, 11, 18, 10, 20), "Tol Cipularang", "Padat Merayap") == \
        "Clipped_18.11_10.20_TolCipularang_PadatMerayap.mp4"
    assert N.build_filename(datetime(2026, 11, 18, 11, 0), "Rest Area KM 57", "Padat") == \
        "Clipped_18.11_11.00_RestAreaKM57_Padat.mp4"
    assert N.build_filename(dt, "Stasiun Bandung", None).endswith("_StasiunBandung_TidakTeridentifikasi.mp4")
    assert N.is_valid_standard("Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4")


def test_invalid_characters_removed():
    name = N.build_filename(datetime(2026, 1, 2, 3, 4), 'Term:inal <Pulo>/Gebang|"?*', "Ramai\\Lancar")
    assert name == "Clipped_02.01_03.04_TermInalPuloGebang_RamaiLancar.mp4"
    for ch in '<>:"/\\|?*':
        assert ch not in name
    # nama cadangan bila hanya karakter tidak valid / nama terlarang Windows
    assert "_Lokasi_" in N.build_filename(datetime(2026, 1, 2, 3, 4), "///", "Padat")
    assert "_Lokasi_" in N.build_filename(datetime(2026, 1, 2, 3, 4), "CON", "Padat")


def test_duplicate_suffix(tmp_path):
    fn = "Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4"
    p1 = N.unique_path(tmp_path, fn)
    assert p1.name == fn
    p1.touch()
    p2 = N.unique_path(tmp_path, fn)
    assert p2.name == "Clipped_18.11_07.30_TerminalPulogebang_Padat_01.mp4"
    p2.touch()
    assert N.unique_path(tmp_path, fn).name.endswith("_02.mp4")
    assert N.unique_path(tmp_path, "Clipped_18.11_07.30_X_Y.mp4", reserved={"Clipped_18.11_07.30_X_Y.mp4"}).name == \
        "Clipped_18.11_07.30_X_Y_01.mp4"


def test_event_time_resolution():
    # metadata tidak tersedia -> tidak ada waktu; nama file tidak boleh memakai waktu ekspor
    dt, src = N.resolve_event_datetime(None, None, None)
    assert dt is None and src == "unknown"
    with pytest.raises(ValueError):
        N.build_filename(None, "Lokasi", "Padat")
    # metadata UTC dikonversi ke WIB
    dt, src = N.resolve_event_datetime(None, None, "2026-11-18T00:30:00+00:00", True, 7)
    assert src == "metadata" and dt.strftime("%d.%m %H.%M") == "18.11 07.30"
    # input operator diprioritaskan
    dt, src = N.resolve_event_datetime("2026-11-19", "16:05", "2026-11-18T00:30:00+00:00")
    assert src == "operator" and dt == datetime(2026, 11, 19, 16, 5)


def test_custom_filename_validation():
    assert N.sanitize_custom("Clipped_18.11_07.30_TerminalA_Padat") == "Clipped_18.11_07.30_TerminalA_Padat.mp4"
    with pytest.raises(ValueError):
        N.sanitize_custom("video_saya.mp4")
    with pytest.raises(ValueError):
        N.sanitize_custom("Clipped_1811_0730_Terminal.mp4")
    assert N.sanitize_custom('Clipped_18.11_07.30_Termi:nal_Pa?dat.mp4') == "Clipped_18.11_07.30_Terminal_Padat.mp4"


def test_parse_creation_time_rejects_bogus():
    from app.services.video_service import parse_creation_time
    assert parse_creation_time("1970-01-01T00:00:00Z") is None
    assert parse_creation_time("2099-01-01T00:00:00Z") is None
    assert parse_creation_time("2026-11-18T00:30:00.000000Z").hour == 0

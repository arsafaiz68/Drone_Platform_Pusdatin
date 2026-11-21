from app.downloader.parser import parse_report

from .conftest import SAMPLE_REPORT, make_report


def test_parse_six_urls():
    r = parse_report(SAMPLE_REPORT)
    assert len(r.entries) == 6
    assert all(e.url_valid for e in r.entries)
    assert r.report_date == "2026-04-01"
    names = [e.filename for e in r.entries]
    assert names == [
        "01.04_14.10_Pel Ketapang_Padat",
        "01.04_15.20_Pel Gilimanuk_Ramai Lancar",
        "01.04_16.00_Pel Merak_Ramai",
        "01.04_16.30_Pel Bakauheni_Lancar",
        "01.04_17.10_Pel Ketapang_Padat",
        "01.04_18.10_Pel Gilimanuk_Ramai Lancar",
    ]
    first = r.entries[0]
    assert first.location == "Pel. Ketapang"
    assert first.time == "14:10" and first.timezone == "WIB"
    assert first.weather == "Cerah"
    assert first.wave_height == "0.2 - 0.5 m" and first.wave_direction == "Selatan"
    assert first.traffic == "Padat" and first.traffic_engineering == "-"
    # Parameter pelacakan dibuang
    assert first.url == "https://www.youtube.com/watch?v=tqvej7BovSQ"
    assert r.entries[3].url == "https://www.youtube.com/watch?v=9bZkp7q19f0"
    assert r.entries[4].url == "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


def test_metadata_not_mixed_between_blocks():
    r = parse_report(SAMPLE_REPORT)
    merak = r.entries[2]
    bakauheni = r.entries[3]
    assert merak.traffic_engineering == "Delaying system"
    assert bakauheni.traffic_engineering == "-"
    assert bakauheni.weather == "Hujan Ringan"
    assert bakauheni.wave_height is None  # tidak mewarisi gelombang Merak
    assert r.entries[1].timezone == "WITA"


def test_parse_dozens_of_urls():
    r = parse_report(make_report(75))
    assert len(r.entries) == 75
    assert all(e.url_valid for e in r.entries)
    assert len({e.filename.lower() for e in r.entries}) == 75
    assert r.entries[10].time == "00:10"
    assert r.entries[10].location == "Pel. Lokasi 3"


def test_whitespace_and_blank_line_variations():
    text = "\n\n   *Pel.   Ketapang*   \n\n\n *1 Apr 2026 , 14.10 WIB*\nCuaca:Cerah\n  Lalin :   Padat  \n\n" \
           "https://youtu.be/tqvej7BovSQ\n"
    r = parse_report(text)
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.location == "Pel. Ketapang"
    assert e.time == "14:10"
    assert e.traffic == "Padat"
    assert e.filename == "01.04_14.10_Pel Ketapang_Padat"


def test_invalid_url_flagged():
    text = """*Pel. Ketapang*
*1 Apr 2026, 14:10 WIB*
Lalin : Padat
https://evil.example.com/watch?v=tqvej7BovSQ

*Pel. Gilimanuk*
*1 Apr 2026, 15:20 WITA*
Lalin : Ramai
https://www.youtube.com/watch?v=short
"""
    r = parse_report(text)
    assert len(r.entries) == 2
    assert not r.entries[0].url_valid
    assert "bukan domain YouTube" in r.entries[0].url_error
    assert not r.entries[1].url_valid
    assert any("URL tidak valid" in w for w in r.entries[1].warnings)


def test_incomplete_metadata_warnings():
    text = """*Pel. Ketapang*
https://www.youtube.com/watch?v=tqvej7BovSQ
"""
    r = parse_report(text)
    assert len(r.entries) == 1
    w = " ".join(r.entries[0].warnings)
    assert "Tanggal tidak ditemukan" in w
    assert "Waktu pengamatan tidak ditemukan" in w
    assert "Lalin" in w
    assert r.entries[0].filename == "00.00_00.00_Pel Ketapang_TanpaKeterangan"


def test_uses_report_date_when_entry_date_missing():
    text = """Hari/Tanggal : *Kamis, 2 April 2026*
*Pel. Merak*
Jam 09:30 WIB
Lalin : Lancar
https://youtu.be/tqvej7BovSQ
"""
    r = parse_report(text)
    e = r.entries[0]
    assert e.date == "2026-04-02"
    assert any("tanggal laporan" in w for w in e.warnings)


def test_no_urls():
    r = parse_report("Laporan tanpa tautan apa pun")
    assert r.entries == []
    assert any("Tidak ada URL" in w for w in r.warnings)


def test_duplicate_url_warning():
    text = SAMPLE_REPORT + "\n*Pel. Ulang*\n*1 Apr 2026, 19:00 WIB*\nLalin : Padat\nhttps://youtu.be/tqvej7BovSQ\n"
    r = parse_report(text)
    assert any("URL sama dengan entri No. 1" in w for w in r.entries[-1].warnings)

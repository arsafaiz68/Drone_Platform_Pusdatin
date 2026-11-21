import pytest

from app.downloader.naming import build_base_name, make_unique, sanitize_filename, with_extension
from app.downloader.parser import ParsedEntry, apply_filenames
from app.downloader.urls import check_youtube_url


# ------------------------------------------------------------------ naming
def test_basic_format():
    assert build_base_name("2026-04-01", "14:10", "Pel. Ketapang", "Padat") == "01.04_14.10_Pel Ketapang_Padat"
    assert with_extension("01.04_14.10_Pel Ketapang_Padat", "mp4").endswith(".mp4")
    assert with_extension("x", ".MKV") == "x.mkv"


def test_illegal_characters_removed():
    name = build_base_name("2026-04-01", "9:05", 'Pel. <Ketapang>: "Dermaga/1"|*?', "Padat\\Merayap")
    for ch in '<>:"/\\|?*':
        assert ch not in name
    assert name == "01.04_09.05_Pel Ketapang Dermaga 1_Padat Merayap"


def test_sanitize_manual_and_reserved():
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("  nama. ") == "nama"
    assert sanitize_filename('a:b*c') == "a b c"
    assert sanitize_filename("") == "video"
    assert len(sanitize_filename("x" * 400)) <= 150


def test_duplicate_names_numbered():
    names = make_unique(["A", "a", "A", "B"])
    assert names == ["A", "a_2", "A_3", "B"]


def test_duplicate_names_from_entries():
    entries = [
        ParsedEntry(id=str(i), index=i, location="Pel. Ketapang", date="2026-04-01", time="14:10", traffic="Padat")
        for i in range(3)
    ]
    apply_filenames(entries)
    assert [e.filename for e in entries] == [
        "01.04_14.10_Pel Ketapang_Padat",
        "01.04_14.10_Pel Ketapang_Padat_2",
        "01.04_14.10_Pel Ketapang_Padat_3",
    ]


def test_manual_filename_kept():
    e = ParsedEntry(id="1", index=1, location="X", date="2026-04-01", time="10:00", traffic="Padat",
                    filename="Nama Khusus?.mp4", filename_manual=True)
    apply_filenames([e])
    assert e.filename == "Nama Khusus"


# ------------------------------------------------------------------ URL
@pytest.mark.parametrize("url,vid,kind", [
    ("https://www.youtube.com/watch?v=tqvej7BovSQ&si=abc", "tqvej7BovSQ", "watch"),
    ("https://www.youtube.com/live/tqvej7BovSQ?si=QzF8UrG-LvXbNFCL", "tqvej7BovSQ", "live"),
    ("https://youtube.com/live/MwXlB-RPNXY?feature=share", "MwXlB-RPNXY", "live"),
    ("https://www.youtube.com/shorts/aqz-KE-bpKQ", "aqz-KE-bpKQ", "shorts"),
    ("https://youtu.be/9bZkp7q19f0?si=xyz", "9bZkp7q19f0", "youtu.be"),
    ("youtu.be/9bZkp7q19f0", "9bZkp7q19f0", "youtu.be"),
    ("https://m.youtube.com/watch?v=jNQXAC9IVRw", "jNQXAC9IVRw", "watch"),
])
def test_valid_youtube_urls(url, vid, kind):
    c = check_youtube_url(url)
    assert c.valid, c.error
    assert c.video_id == vid
    assert c.kind == kind
    assert c.normalized == f"https://www.youtube.com/watch?v={vid}"


@pytest.mark.parametrize("url", [
    "https://evil.com/watch?v=tqvej7BovSQ",
    "https://youtube.com.evil.com/watch?v=tqvej7BovSQ",
    "http://127.0.0.1:8000/api/health",
    "http://169.254.169.254/latest/meta-data",
    "file:///C:/Windows/win.ini",
    "https://user:pass@www.youtube.com/watch?v=tqvej7BovSQ",
    "https://www.youtube.com:8443/watch?v=tqvej7BovSQ",
    "https://www.youtube.com/watch?v=bad",
    "https://www.youtube.com/channel/UC123",
    "",
])
def test_invalid_urls_rejected(url):
    assert not check_youtube_url(url).valid

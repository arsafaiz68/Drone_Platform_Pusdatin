import pytest

from app.downloader import localfs
from app.downloader.localfs import FolderError


def test_list_folder_shows_subfolders_only(tmp_path):
    (tmp_path / "April").mkdir()
    (tmp_path / "maret").mkdir()
    (tmp_path / ".tersembunyi").mkdir()
    (tmp_path / "video.mp4").write_bytes(b"x")
    r = localfs.list_folder(str(tmp_path))
    assert [c["name"] for c in r["children"]] == ["April", "maret"]
    assert r["writable"] is True
    assert r["video_count"] == 1
    assert r["parent"] == str(tmp_path.parent)


def test_navigate_into_subfolder_and_back(tmp_path):
    sub = tmp_path / "Angkutan Lebaran" / "2026"
    sub.mkdir(parents=True)
    root = localfs.list_folder(str(tmp_path))
    child = localfs.list_folder(root["children"][0]["path"])
    assert child["children"][0]["name"] == "2026"
    back = localfs.list_folder(child["parent"])
    assert back["path"] == str(tmp_path)


def test_create_folder_sanitizes_name(tmp_path):
    r = localfs.create_folder(str(tmp_path), 'Video: April/2026?')
    assert r["name"] == "Video April 2026"
    assert (tmp_path / "Video April 2026").is_dir()
    with pytest.raises(FolderError) as ei:
        localfs.create_folder(str(tmp_path), "Video April 2026")
    assert ei.value.status == 409


def test_validate_output_dir(tmp_path):
    assert localfs.validate_output_dir(str(tmp_path)) == tmp_path.resolve()
    with pytest.raises(FolderError):
        localfs.validate_output_dir("")
    with pytest.raises(FolderError):
        localfs.validate_output_dir("folder/relatif")
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(FolderError):
        localfs.validate_output_dir(str(f))
    with pytest.raises(FolderError) as ei:
        localfs.validate_output_dir(str(tmp_path / "x"))
    assert ei.value.status == 404
    assert localfs.validate_output_dir(str(tmp_path / "x" / "y"), create=True).is_dir()


def test_roots_include_home():
    roots = localfs.list_roots()
    assert any(r["kind"] == "home" for r in roots)
    assert any(r["kind"] == "drive" for r in roots)

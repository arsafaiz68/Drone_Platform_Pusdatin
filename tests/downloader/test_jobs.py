import asyncio
from pathlib import Path

import pytest

from app.downloader.jobs import BatchError, BatchManager, JobStatus
from app.downloader.localfs import STAGING_DIRNAME
from app.downloader.parser import parse_report

from .conftest import SAMPLE_REPORT, FakeDownloader


def entries():
    return [e.to_dict() for e in parse_report(SAMPLE_REPORT).entries]


def make_manager(tmp_dirs, downloader, **kw):
    _, h = tmp_dirs
    events = []

    async def notifier(batch_id, msg):
        events.append(msg)

    m = BatchManager(downloader, h, retry_base_delay=0.01, notifier=notifier, **kw)
    m.events = events
    return m


def run_batch(m, out, ents, **kw):
    async def go():
        b = m.create_batch(ents, output_dir=str(out), **kw)
        m.start(b)
        await m.wait(b.id)
        return b

    return asyncio.run(go())


def test_full_success_saved_to_chosen_folder(tmp_dirs):
    out, _ = tmp_dirs
    m = make_manager(tmp_dirs, FakeDownloader())
    b = run_batch(m, out, entries())
    s = b.summary()
    assert s["total"] == 6 and s["success"] == 6
    assert b.status == "completed"
    assert (out / "01.04_14.10_Pel Ketapang_Padat.mp4").exists()
    assert (out / "01.04_15.20_Pel Gilimanuk_Ramai Lancar.mp4").exists()
    assert all(Path(j.output_path).parent == out for j in b.jobs)
    assert not (out / STAGING_DIRNAME).exists(), "folder sementara dibersihkan setelah selesai"
    assert any(e.get("job", {}).get("status") == "processing" for e in m.events)


def test_download_failure_does_not_stop_batch(tmp_dirs):
    out, _ = tmp_dirs
    m = make_manager(tmp_dirs, FakeDownloader({"MwXlB-RPNXY": "fail"}))
    b = run_batch(m, out, entries())
    failed = [j for j in b.jobs if j.status == JobStatus.FAILED]
    assert len(failed) == 1 and "privat" in failed[0].error
    assert b.summary()["success"] == 5
    assert b.status == "partial"


def test_retryable_download_error_auto_retried(tmp_dirs):
    out, _ = tmp_dirs
    m = make_manager(tmp_dirs, FakeDownloader({"tqvej7BovSQ": "flaky"}))
    b = run_batch(m, out, entries()[:1])
    assert b.jobs[0].status == JobStatus.SUCCESS
    assert b.jobs[0].attempts == 2


def test_conflict_rename_keeps_existing_file(tmp_dirs):
    out, _ = tmp_dirs
    old = out / "01.04_14.10_Pel Ketapang_Padat.mp4"
    old.write_bytes(b"lama")
    m = make_manager(tmp_dirs, FakeDownloader())
    b = run_batch(m, out, entries()[:1], conflict_behavior="rename")
    j = b.jobs[0]
    assert j.status == JobStatus.SUCCESS
    assert j.final_filename == "01.04_14.10_Pel Ketapang_Padat_2.mp4"
    assert old.read_bytes() == b"lama"
    assert "disimpan sebagai" in j.note


def test_conflict_skip(tmp_dirs):
    out, _ = tmp_dirs
    (out / "01.04_14.10_Pel Ketapang_Padat.mp4").write_bytes(b"lama")
    dl = FakeDownloader()
    m = make_manager(tmp_dirs, dl)
    b = run_batch(m, out, entries()[:2], conflict_behavior="skip")
    assert b.jobs[0].status == JobStatus.SKIPPED
    assert b.jobs[1].status == JobStatus.SUCCESS
    assert dl.calls == ["MwXlB-RPNXY"], "video yang sudah ada tidak diunduh lagi"
    assert b.status == "completed"


def test_conflict_replace(tmp_dirs):
    out, _ = tmp_dirs
    old = out / "01.04_14.10_Pel Ketapang_Padat.mp4"
    old.write_bytes(b"lama")
    m = make_manager(tmp_dirs, FakeDownloader(size=2048))
    b = run_batch(m, out, entries()[:1], conflict_behavior="replace")
    assert b.jobs[0].final_filename == old.name
    assert old.stat().st_size == 2048


def test_cancel_batch(tmp_dirs):
    out, _ = tmp_dirs
    dl = FakeDownloader({e["video_id"]: "block" for e in entries()})
    m = make_manager(tmp_dirs, dl)

    async def go():
        b = m.create_batch(entries(), output_dir=str(out), parallel=2)
        m.start(b)
        for _ in range(200):
            if sum(j.status == JobStatus.DOWNLOADING for j in b.jobs) == 2:
                break
            await asyncio.sleep(0.01)
        await m.cancel_batch(b.id)
        await m.wait(b.id)
        return b

    b = asyncio.run(go())
    assert all(j.status == JobStatus.CANCELLED for j in b.jobs)
    assert b.status == "cancelled"
    assert len(dl.calls) == 2, "pekerjaan yang masih menunggu tidak boleh mulai setelah dibatalkan"


def test_retry_failed_jobs(tmp_dirs):
    out, _ = tmp_dirs
    dl = FakeDownloader({"MwXlB-RPNXY": "fail"})
    m = make_manager(tmp_dirs, dl)

    async def go():
        b = m.create_batch(entries(), output_dir=str(out))
        m.start(b)
        await m.wait(b.id)
        assert b.summary()["failed"] == 1
        dl.behaviors.clear()
        assert len(await m.retry(b.id)) == 1
        await m.wait(b.id)
        return b

    b = asyncio.run(go())
    assert b.summary()["success"] == 6 and b.status == "completed"
    # retry tidak membuat duplikat untuk video yang sudah berhasil
    assert len(list(out.glob("*.mp4"))) == 6


def test_history_persisted_and_interrupted_jobs_marked(tmp_dirs):
    out, _ = tmp_dirs
    m = make_manager(tmp_dirs, FakeDownloader())
    b = m.create_batch(entries()[:2], output_dir=str(out))
    b.jobs[0].status = JobStatus.DOWNLOADING  # simulasi aplikasi mati saat mengunduh
    m.save(b)

    m2 = make_manager(tmp_dirs, FakeDownloader())
    assert m2.load_history() == 1
    loaded = m2.get(b.id)
    assert loaded.jobs[0].status == JobStatus.FAILED
    assert "aplikasi ditutup" in loaded.jobs[0].error
    assert loaded.output_dir == str(out)


def test_create_batch_validation(tmp_dirs, tmp_path):
    out, _ = tmp_dirs
    m = make_manager(tmp_dirs, FakeDownloader())
    with pytest.raises(BatchError) as ei:
        m.create_batch(entries(), output_dir=str(tmp_path / "tidak-ada"))
    assert ei.value.status == 404
    with pytest.raises(BatchError):
        m.create_batch(entries(), output_dir="relatif/folder")
    b = m.create_batch(entries()[:1], output_dir=str(tmp_path / "baru" / "sub"), create_dir=True)
    assert Path(b.output_dir).is_dir()
    bad = entries()[:1]
    bad[0]["url"] = bad[0]["url_original"] = "https://evil.com/watch?v=tqvej7BovSQ"
    with pytest.raises(BatchError) as ei:
        m.create_batch(bad, output_dir=str(out))
    assert ei.value.status == 422
    with pytest.raises(BatchError):
        m.create_batch(entries(), output_dir=str(out), quality=2160)
    with pytest.raises(BatchError):
        m.create_batch(entries(), output_dir=str(out), conflict_behavior="hapus")

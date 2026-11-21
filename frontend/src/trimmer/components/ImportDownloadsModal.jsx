import { useEffect, useMemo, useState } from "react";
import { api, fmtBytes, fmtDate } from "../services/api.js";
import { Empty, Field, Loading, Modal, Notice, Segmented, useAction } from "./ui.jsx";

const MAX = 24;

/** Ringkasan informasi video hasil parsing laporan (lokasi · tanggal waktu · lalin). */
export function InfoSummary({ fields }) {
  const f = fields || {};
  if (!f.location_name && !f.event_date && !f.traffic_condition) return <span className="muted small">tidak ada informasi</span>;
  return (
    <span className="small">
      <b>{f.location_name || "?"}</b> · {f.event_date || "?"} {f.event_time || ""}
      {f.traffic_condition && <div className="muted err-clamp" title={f.traffic_condition}>Lalin: {f.traffic_condition}</div>}
    </span>
  );
}

/**
 * Pilih video hasil Drone Video Downloader (riwayat unduhan atau folder) untuk dimasukkan ke batch.
 * Informasi video (lokasi, tanggal, waktu, kondisi lalin) ikut terbawa sehingga tidak perlu diisi manual.
 *
 * onSubmit(body) menerima {downloader_batch_id, job_ids} atau {items:[{path, info}]}.
 */
export default function ImportDownloadsModal({ open, onClose, onSubmit, existing = 0, initialBatchId = null,
  title = "Impor dari Drone Video Downloader", submitLabel = "Impor", extra = null, submitDisabled = false }) {
  const [mode, setMode] = useState("history");
  const [batches, setBatches] = useState(null);
  const [dlId, setDlId] = useState(initialBatchId);
  const [folder, setFolder] = useState("");
  const [scan, setScan] = useState(null);
  const [sel, setSel] = useState({});
  const [run, busy] = useAction();

  useEffect(() => {
    if (!open) return;
    setSel({});
    api.downloads().then((bs) => {
      setBatches(bs);
      const first = initialBatchId || (bs.find((b) => b.available) || {}).id || null;
      setDlId(first);
    }).catch(() => setBatches([]));
  }, [open, initialBatchId]);

  const current = useMemo(() => (batches || []).find((b) => b.id === dlId) || null, [batches, dlId]);
  const videos = mode === "history" ? (current?.videos || []) : (scan?.videos || []);
  const keyOf = (v) => v.job_id || v.path;

  // default: semua video yang masih ada di disk terpilih
  useEffect(() => {
    const next = {};
    videos.forEach((v) => { if (v.exists) next[keyOf(v)] = true; });
    setSel(next);
  }, [mode, dlId, scan, batches]); // eslint-disable-line react-hooks/exhaustive-deps

  const chosen = videos.filter((v) => sel[keyOf(v)] && v.exists);
  const total = existing + chosen.length;
  const over = total > MAX;

  const doScan = async () => {
    const r = await run(() => api.scanFolder(folder));
    if (r) setScan(r);
  };
  const pick = async () => {
    const r = await run(() => api.pickFolder(folder));
    if (r && r.path) { setFolder(r.path); const s = await run(() => api.scanFolder(r.path)); if (s) setScan(s); }
  };
  const submit = () => {
    if (mode === "history" && current) {
      const all = current.videos.filter((v) => v.exists).length === chosen.length;
      onSubmit({ downloader_batch_id: current.id, job_ids: all ? null : chosen.map((v) => v.job_id) });
    } else {
      onSubmit({ items: chosen.map((v) => ({ path: v.path, info: v.info && Object.keys(v.info).length ? v.info : null })) });
    }
  };

  return (
    <Modal open={open} wide title={title} onClose={onClose} footer={<>
      <span className="small muted" style={{ marginRight: "auto" }}>{chosen.length} video dipilih · batch akan berisi {total} / {MAX}</span>
      <button className="btn" onClick={onClose}>Batal</button>
      <button className="btn btn-primary" disabled={busy || submitDisabled || !chosen.length || over} onClick={submit}>{submitLabel}</button>
    </>}>
      <Notice tone="info">Informasi tiap video (lokasi, tanggal, waktu, kondisi lalin) diambil otomatis dari hasil parsing laporan di
        Drone Video Downloader. Video tidak disalin — Trimmer membaca file langsung dari folder unduhan.</Notice>
      {extra}
      <Field label="Sumber">
        <Segmented value={mode} onChange={setMode} options={[{ value: "history", label: "Riwayat unduhan" }, { value: "folder", label: "Folder video" }]} />
      </Field>
      {mode === "history" ? (
        batches == null ? <Loading /> : !batches.length ? <Empty>Belum ada riwayat unduhan. Unduh video lewat <a href="/downloader/">Drone Video Downloader</a> terlebih dahulu.</Empty> : (
          <Field label="Batch unduhan">
            <select value={dlId || ""} onChange={(e) => setDlId(e.target.value)}>
              {batches.map((b) => <option key={b.id} value={b.id}>
                {fmtDate(b.created_at)} · laporan {b.report_date || "–"} · {b.available}/{b.videos.length} video tersedia · {b.output_dir}
              </option>)}
            </select>
          </Field>
        )
      ) : (
        <Field label="Folder video" hint="Folder tujuan unduhan. Informasi dibaca dari file _info_video_drone.json; bila tidak ada, ditebak dari nama file (DD.MM_HH.MM_Lokasi_Lalin.mp4).">
          <div className="row">
            <input value={folder} placeholder="mis. D:\Arsip Video\Maret 2026" onChange={(e) => setFolder(e.target.value)} style={{ flex: 1 }} />
            <button className="btn" onClick={pick} disabled={busy}>Pilih folder…</button>
            <button className="btn" onClick={doScan} disabled={busy || !folder.trim()}>Baca folder</button>
          </div>
        </Field>
      )}
      {over && <Notice tone="err" title="Melebihi batas batch">Maksimal {MAX} video per batch. Kurangi pilihan atau buat batch lain.</Notice>}
      {videos.length > 0 ? (
        <div className="table-wrap">
          <table className="table table-compact">
            <thead><tr>
              <th><input type="checkbox" checked={chosen.length > 0 && chosen.length === videos.filter((v) => v.exists).length}
                onChange={(e) => { const n = {}; if (e.target.checked) videos.forEach((v) => { if (v.exists) n[keyOf(v)] = true; }); setSel(n); }} /></th>
              <th>Nama file</th><th>Informasi video</th><th>Ukuran</th><th>Status</th></tr></thead>
            <tbody>{videos.map((v) => (
              <tr key={keyOf(v)}>
                <td><input type="checkbox" disabled={!v.exists} checked={!!sel[keyOf(v)]} onChange={(e) => setSel({ ...sel, [keyOf(v)]: e.target.checked })} /></td>
                <td className="wrap-any small">{v.filename}</td>
                <td><InfoSummary fields={v.fields} />
                  {v.info_source === "filename" && <div className="small muted">dari nama file</div>}</td>
                <td className="nowrap small">{fmtBytes(v.size_bytes)}</td>
                <td className="small">{v.exists ? "tersedia" : <span className="text-err">file tidak ditemukan</span>}</td>
              </tr>))}</tbody>
          </table>
        </div>
      ) : (mode === "folder" && scan ? <Empty>Tidak ada file video di folder ini.</Empty> : null)}
    </Modal>
  );
}

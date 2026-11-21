import { useEffect, useState } from "react";
import { api, fmtBytes } from "../services/api.js";
import { Modal, Notice, useAction } from "./ui.jsx";

/** Dialog hapus batch. File video sumber tidak pernah dihapus; hasil ekspor opsional. */
export function DeleteBatchModal({ batch, onClose, onDeleted }) {
  const [withExports, setWithExports] = useState(false);
  const [run, busy] = useAction();
  if (!batch) return null;
  const running = ["running", "queued"].includes(batch.status);
  const submit = async () => {
    const r = await run(() => api.deleteBatch(batch.id, withExports), `Batch "${batch.name}" dihapus`);
    if (r) { onClose(); onDeleted && onDeleted(r); }
  };
  return (
    <Modal open title={`Hapus batch "${batch.name}"?`} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Batal</button>
      <button className="btn btn-danger" disabled={busy || running} onClick={submit}>Hapus batch</button>
    </>}>
      {running ? <Notice tone="warn">Batch sedang berjalan. Jeda atau batalkan batch terlebih dahulu.</Notice> : null}
      <p>Data batch akan dihapus dari aplikasi: daftar video, hasil analisis, kandidat, video hasil, serta file
        sementara (salinan unggahan, preview, thumbnail).</p>
      <p className="small muted">File video sumber di folder Anda (mis. folder unduhan Downloader) <b>tidak</b> dihapus.</p>
      <label className="check"><input type="checkbox" checked={withExports} onChange={(e) => setWithExports(e.target.checked)} />
        Hapus juga file video hasil ekspor (.mp4 &amp; .json) dari disk</label>
    </Modal>
  );
}

/** Tombol unduh ZIP seluruh video hasil yang sudah diekspor (batch atau proyek). */
export function ZipButton({ batchId, projectId, className = "btn", label = "Unduh ZIP hasil" }) {
  const [sum, setSum] = useState(null);
  useEffect(() => {
    const f = batchId ? api.batchZipSummary(batchId) : api.projectZipSummary(projectId);
    f.then(setSum).catch(() => setSum(null));
  }, [batchId, projectId]);
  const url = batchId ? api.batchZipUrl(batchId) : api.projectZipUrl(projectId);
  const ready = sum?.ready || 0;
  const title = ready
    ? `${ready} dari ${sum.total_finals} video hasil sudah diekspor · ±${fmtBytes(sum.size_bytes)} · berisi mp4, json, dan daftar_video_hasil.csv`
    : "Belum ada video hasil yang diekspor. Klik Ekspor Semua terlebih dahulu.";
  return ready
    ? <a className={className} href={url} title={title} download onClick={(e) => e.stopPropagation()}>{label} ({ready})</a>
    : <button className={className} disabled title={title}>{label}</button>;
}

/** Dialog hapus proyek (beserta seluruh batch). File video sumber tidak pernah dihapus. */
export function DeleteProjectModal({ project, onClose, onDeleted }) {
  const [withExports, setWithExports] = useState(false);
  const [confirmName, setConfirmName] = useState("");
  const [run, busy] = useAction();
  if (!project) return null;
  const submit = async () => {
    const r = await run(() => api.deleteProject(project.id, withExports), `Proyek "${project.name}" dihapus`);
    if (r) { onClose(); onDeleted && onDeleted(r); }
  };
  return (
    <Modal open title={`Hapus proyek "${project.name}"?`} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Batal</button>
      <button className="btn btn-danger" disabled={busy || confirmName.trim() !== project.name.trim()} onClick={submit}>Hapus proyek</button>
    </>}>
      <p>Proyek beserta <b>{project.batch_count ?? "seluruh"} batch</b>, {project.video_count ?? 0} video terdaftar, hasil analisis,
        dan video hasilnya akan dihapus dari aplikasi.</p>
      <p className="small muted">File video sumber di folder Anda <b>tidak</b> dihapus. Riwayat koreksi operator (data pelatihan AI) tetap disimpan.</p>
      <label className="check"><input type="checkbox" checked={withExports} onChange={(e) => setWithExports(e.target.checked)} />
        Hapus juga file video hasil ekspor (.mp4 &amp; .json) dari disk</label>
      <div className="field" style={{ marginTop: 10 }}>
        <span className="field-label">Ketik nama proyek untuk konfirmasi: <b>{project.name}</b></span>
        <input value={confirmName} onChange={(e) => setConfirmName(e.target.value)} placeholder={project.name} />
      </div>
    </Modal>
  );
}

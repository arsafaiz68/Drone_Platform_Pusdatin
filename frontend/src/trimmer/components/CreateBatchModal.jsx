import { useEffect, useState } from "react";
import { api } from "../services/api.js";
import DurationSlider from "./DurationSlider.jsx";
import { Field, Modal, Notice, Segmented, useAction } from "./ui.jsx";

export default function CreateBatchModal({ open, onClose, projectId, onCreated }) {
  const [projects, setProjects] = useState([]);
  const [hw, setHw] = useState(null);
  const [form, setForm] = useState({ project_id: projectId || "", name: "", final_duration: 30,
    trip_mode: "round_trip", concurrency: 2, metadata_mode: "shared" });
  const [run, busy] = useAction();
  useEffect(() => {
    if (!open) return;
    api.projects().then(setProjects).catch(() => {});
    api.hardware().then((h) => {
      setHw(h);
      setForm((f) => ({ ...f, concurrency: Math.min(f.concurrency, h.max_concurrency || 4) }));
    }).catch(() => {});
    if (projectId) setForm((f) => ({ ...f, project_id: projectId }));
  }, [open, projectId]);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const submit = async () => {
    const b = await run(() => api.createBatch({ ...form, project_id: Number(form.project_id),
      name: form.name || null }), "Batch dibuat");
    if (b) { onCreated && onCreated(b); onClose(); }
  };
  const maxC = hw ? hw.max_concurrency : 4;
  return (
    <Modal open={open} onClose={onClose} title="Batch baru" footer={<>
      <button className="btn" onClick={onClose}>Batal</button>
      <button className="btn btn-primary" disabled={busy || !form.project_id} onClick={submit}>Buat batch</button>
    </>}>
      <div className="form">
        <Field label="Proyek">
          <select value={form.project_id} onChange={(e) => set("project_id")(e.target.value)}>
            <option value="">— pilih proyek —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.template_name})</option>)}
          </select>
        </Field>
        <Field label="Nama batch" hint="Kosongkan untuk nama otomatis">
          <input value={form.name} onChange={(e) => set("name")(e.target.value)} placeholder="mis. Pantauan pagi 18 Nov" />
        </Field>
        <Field label="Durasi tiap video hasil" hint="Setiap video sumber (maks. 24) menjadi SATU video hasil sendiri berdurasi ini — video tidak digabung.">
          <DurationSlider value={form.final_duration} onChange={set("final_duration")} live />
        </Field>
        <Field label="Mode perjalanan">
          <Segmented value={form.trip_mode} onChange={set("trip_mode")}
            options={[{ value: "outbound", label: "Pergi saja" }, { value: "round_trip", label: "Pergi dan kembali" }]} />
        </Field>
        <Field label="Proses bersamaan (concurrency)" hint={hw ? `Rekomendasi perangkat: ${hw.recommended_concurrency}, maksimum ${hw.max_concurrency}` : ""}>
          <Segmented value={form.concurrency} onChange={set("concurrency")}
            options={[1, 2, 4].map((c) => ({ value: c, label: `${c} video` }))} />
        </Field>
        {form.concurrency > maxC && <Notice tone="warn">Concurrency {form.concurrency} melebihi kemampuan perangkat dan akan dibatasi menjadi {maxC}.</Notice>}
        <Field label="Informasi video" hint="Lokasi, tanggal, waktu, dan kondisi lalin dibaca otomatis per video dari Drone Video Downloader (manifest atau nama file). Kelompok lokasi hanya menjadi cadangan untuk video tanpa informasi.">
          <Segmented value={form.metadata_mode} onChange={set("metadata_mode")}
            options={[{ value: "shared", label: "Cadangan dari kelompok lokasi" }, { value: "per_final", label: "Isi manual per video" }]} />
        </Field>
      </div>
    </Modal>
  );
}

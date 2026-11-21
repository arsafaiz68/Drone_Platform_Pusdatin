import { useEffect, useState } from "react";
import { api } from "../services/api.js";
import DurationSlider from "./DurationSlider.jsx";
import ImportDownloadsModal from "./ImportDownloadsModal.jsx";
import { Field, Segmented, useAction } from "./ui.jsx";

/** Buat batch Trimmer baru langsung dari hasil Drone Video Downloader. */
export default function BatchFromDownloadModal({ open, onClose, onCreated, initialBatchId = null }) {
  const [projects, setProjects] = useState([]);
  const [form, setForm] = useState({ project_id: "", final_duration: 30, trip_mode: "round_trip", concurrency: 2, start: true });
  const [newProject, setNewProject] = useState("Pemantauan Video Drone");
  const [run] = useAction();
  useEffect(() => {
    if (!open) return;
    api.projects().then((ps) => {
      setProjects(ps);
      setForm((f) => ({ ...f, project_id: f.project_id || (ps[0] ? ps[0].id : "") }));
    }).catch(() => {});
    api.settings().then((s) => setForm((f) => ({ ...f, final_duration: s.values?.default_final_duration || f.final_duration }))).catch(() => {});
  }, [open]);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const submit = async (body) => {
    let pid = form.project_id;
    if (!pid) {
      // belum ada proyek (mis. PC baru): buat proyek otomatis; jenis lokasi tetap ditentukan per video
      const p = await run(() => api.createProject({ name: newProject.trim() || "Pemantauan Video Drone", template_code: "terminal" }));
      if (!p) return;
      pid = p.id;
    }
    const b = await run(() => api.batchFromDownload({ ...form, ...body, project_id: Number(pid) }),
      form.start ? "Batch dibuat dan analisis dimulai" : "Batch dibuat");
    if (b) { onClose(); onCreated && onCreated(b); }
  };
  const extra = (
    <div className="form">
      <div className="grid-3">
        <Field label="Proyek">
          {projects.length > 0 && <select value={form.project_id} onChange={(e) => set("project_id")(e.target.value)}>
            <option value="">— pilih proyek —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.template_name})</option>)}
          </select>}
          {!projects.length && <>
            <input value={newProject} onChange={(e) => setNewProject(e.target.value)} placeholder="Nama proyek baru" />
            <div className="small muted">Belum ada proyek — proyek baru dibuat otomatis dengan nama ini.</div>
          </>}
        </Field>
        <Field label="Durasi tiap video hasil" hint="Setiap video sumber menjadi satu video hasil berdurasi ini.">
          <DurationSlider value={form.final_duration} onChange={set("final_duration")} live />
        </Field>
        <Field label="Mode perjalanan">
          <Segmented value={form.trip_mode} onChange={set("trip_mode")}
            options={[{ value: "outbound", label: "Pergi saja" }, { value: "round_trip", label: "Pergi & kembali" }]} />
        </Field>
      </div>
      <label className="check"><input type="checkbox" checked={form.start} onChange={(e) => set("start")(e.target.checked)} /> Langsung mulai analisis setelah batch dibuat</label>
    </div>
  );
  return (
    <ImportDownloadsModal open={open} onClose={onClose} onSubmit={submit} initialBatchId={initialBatchId}
      title="Batch baru dari hasil unduhan" submitLabel="Buat batch" extra={extra}
      submitDisabled={!form.project_id && !(projects.length === 0 && newProject.trim())} />
  );
}

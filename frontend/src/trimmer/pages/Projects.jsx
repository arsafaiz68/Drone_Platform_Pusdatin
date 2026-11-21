import { DeleteProjectModal, ZipButton } from "../components/BatchActions.jsx";
import { useState } from "react";
import CreateBatchModal from "../components/CreateBatchModal.jsx";
import RouteDiagram from "../components/RouteDiagram.jsx";
import { Card, Empty, ErrorBox, Field, Loading, Modal, ProgressBar, StatusBadge, useAction } from "../components/ui.jsx";
import { navigate, useLoad } from "../hooks/useApi.js";
import { api, fmtDate, tripLabel } from "../services/api.js";

function CreateProjectModal({ open, onClose, onCreated }) {
  const tmpl = useLoad(api.templates, []);
  const [form, setForm] = useState({ name: "", template_code: "terminal", location_name: "", description: "" });
  const [run, busy] = useAction();
  const t = (tmpl.data || []).find((x) => x.code === form.template_code);
  const submit = async () => {
    const p = await run(() => api.createProject(form), "Proyek dibuat");
    if (p) { onCreated(p); onClose(); setForm({ ...form, name: "", location_name: "", description: "" }); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Proyek baru" footer={<>
      <button className="btn" onClick={onClose}>Batal</button>
      <button className="btn btn-primary" disabled={busy || !form.name.trim()} onClick={submit}>Buat proyek</button>
    </>}>
      <div className="form">
        <Field label="Nama proyek"><input autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="mis. Angkutan Nataru 2026" /></Field>
        <Field label="Template pemantauan">
          <select value={form.template_code} onChange={(e) => setForm({ ...form, template_code: e.target.value })}>
            {(tmpl.data || []).map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}
          </select>
        </Field>
        {t && <div className="tmpl-mini"><p className="small muted">{t.description}</p>
          <RouteDiagram outbound={t.route_outbound} ret={t.route_return} turnarounds={t.turnarounds} /></div>}
        <Field label="Nama lokasi default" hint="Dipakai pada nama file, dapat diubah per kelompok lokasi">
          <input value={form.location_name} onChange={(e) => setForm({ ...form, location_name: e.target.value })} placeholder="mis. Terminal Pulogebang" />
        </Field>
        <Field label="Deskripsi"><textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}

function ProjectDetail({ id }) {
  const { data: p, error, loading, reload } = useLoad(() => api.project(id), [id]);
  const [batchOpen, setBatchOpen] = useState(false);
  const [delOpen, setDelOpen] = useState(false);
  if (loading && !p) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <a href="#/projects" className="small">← Semua proyek</a>
          <h1>{p.name}</h1>
          <p className="muted">{p.template_name} · Lokasi: {p.location_name || "–"} · dibuat {fmtDate(p.created_at)}</p>
        </div>
        <div className="row">
          <ZipButton projectId={id} label="Unduh ZIP semua hasil proyek" />
          <button className="btn btn-primary" onClick={() => setBatchOpen(true)}>Batch baru</button>
          <button className="btn btn-danger-ghost" onClick={() => setDelOpen(true)}>Hapus proyek</button>
        </div>
      </header>
      {delOpen && <DeleteProjectModal project={p} onClose={() => setDelOpen(false)} onDeleted={() => navigate("/projects")} />}
      {p.description && <p>{p.description}</p>}
      <Card title={`Batch (${p.batches.length})`}>
        {p.batches.length ? (
          <table className="table">
            <thead><tr><th>Batch</th><th>Video</th><th>Kelompok lokasi</th><th>Durasi / video</th><th>Mode</th><th>Status</th><th style={{ width: 150 }}>Progres</th></tr></thead>
            <tbody>
              {p.batches.map((b) => (
                <tr key={b.id} className="clickable" onClick={() => navigate(`/batches/${b.id}`)}>
                  <td><strong>{b.name}</strong></td><td>{b.stats.total}</td><td>{b.group_count}</td>
                  <td>{b.final_duration} dtk</td><td>{tripLabel(b.trip_mode)}</td>
                  <td><StatusBadge status={b.status} label={b.status_label} /></td>
                  <td><ProgressBar value={b.stats.progress} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty>Belum ada batch.</Empty>}
      </Card>
      <CreateBatchModal open={batchOpen} onClose={() => setBatchOpen(false)} projectId={id}
        onCreated={(b) => navigate(`/batches/${b.id}`)} />
    </div>
  );
}

export default function Projects({ projectId }) {
  const { data, error, loading, reload } = useLoad(api.projects, []);
  const [open, setOpen] = useState(false);
  const [delProject, setDelProject] = useState(null);
  if (projectId) return <ProjectDetail id={projectId} />;
  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Proyek</h1><p className="muted">Setiap proyek memakai satu template pemantauan.</p></div>
        <button className="btn btn-primary" onClick={() => setOpen(true)}>Proyek baru</button>
      </header>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Loading /> : (data && data.length ? (
        <div className="cards">
          {data.map((p) => (
            <a key={p.id} className="project-card" href={`#/projects/${p.id}`}>
              <div className="project-card-head"><strong>{p.name}</strong><span className="badge badge-info">{p.template_name}</span></div>
              <div className="small muted">{p.location_name || "Lokasi belum diisi"}</div>
              <div className="project-card-stats">
                <span><b>{p.batch_count}</b> batch</span><span><b>{p.video_count}</b> video</span>
                <span><b>{p.final_count}</b> video hasil</span><span><b>{p.export_count}</b> ekspor</span>
              </div>
              <div className="project-card-actions">
                <button className="btn btn-sm btn-danger-ghost" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setDelProject(p); }}>Hapus proyek</button>
              </div>
            </a>
          ))}
        </div>
      ) : <Card><Empty>Belum ada proyek. Klik “Proyek baru” untuk memulai.</Empty></Card>)}
      {delProject && <DeleteProjectModal project={delProject} onClose={() => setDelProject(null)} onDeleted={reload} />}
      <CreateProjectModal open={open} onClose={() => setOpen(false)} onCreated={(p) => { reload(); navigate(`/projects/${p.id}`); }} />
    </div>
  );
}

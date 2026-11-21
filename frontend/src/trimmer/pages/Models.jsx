import { useState } from "react";
import { Card, ErrorBox, Field, Loading, Notice, Tag, useAction } from "../components/ui.jsx";
import { useLoad } from "../hooks/useApi.js";
import { api } from "../services/api.js";

export default function Models() {
  const { data, error, loading, reload } = useLoad(api.models, []);
  const [form, setForm] = useState({ name: "YOLOv8n COCO", path: "", conf: 0.3, validated: false });
  const [run] = useAction();
  if (loading && !data) return <div className="page"><Loading /></div>;
  const d = data || {};
  return (
    <div className="page">
      <header className="page-head"><div><h1>Model AI</h1><p className="muted">Seluruh inferensi berjalan lokal. Tidak ada video yang dikirim ke layanan cloud.</p></div></header>
      <ErrorBox error={error} onRetry={reload} />
      {d.heuristic_mode && <Notice tone="warn" title="Mode heuristik aktif">
        Belum ada model deteksi objek. Analisis tetap berjalan memakai fitur visual OpenCV (kualitas, kestabilan, gerak, kemiripan adegan),
        tetapi hasil berupa kandidat awal yang wajib diverifikasi operator. Letakkan file model <span className="mono">.onnx</span> di <span className="mono">{d.models_dir}</span>.
      </Notice>}
      <div className="grid-2">
        <Card title="Kemampuan analisis">
          <table className="table table-compact"><thead><tr><th>Fitur</th><th>Status</th><th>Catatan</th></tr></thead>
            <tbody>{(d.capabilities || []).map((c) => (
              <tr key={c.name}><td>{c.name}</td>
                <td><Tag tone={c.status === "aktif" ? "ok" : c.status.startsWith("saran") ? "warn" : "muted"}>{c.status}</Tag></td>
                <td className="small muted">{c.note || ""}</td></tr>))}</tbody></table>
        </Card>
        <Card title="Detektor aktif">
          <dl className="kv">
            <dt>Nama</dt><dd>{d.active_detector?.available ? d.active_detector.name : "Tidak ada (heuristik)"}</dd>
            <dt>Perangkat</dt><dd>{d.active_detector?.device || "–"}</dd>
            <dt>Tervalidasi</dt><dd>{d.active_detector?.validated ? "Ya" : "Belum"}</dd>
            <dt>Folder model</dt><dd className="mono small wrap-any">{d.models_dir}</dd>
          </dl>
          <h4>File model terdeteksi</h4>
          {d.model_files?.length ? <ul className="small mono">{d.model_files.map((f) => <li key={f.path}>{f.name} ({f.size_mb} MB)</li>)}</ul> : <p className="small muted">Tidak ada file .onnx.</p>}
        </Card>
      </div>
      <div className="grid-2">
        <Card title="Daftarkan model detektor (ONNX)">
          <div className="form">
            <Field label="Nama"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Path file .onnx" hint="Format keluaran YOLOv8/YOLO11 (kelas COCO: person, car, motorcycle, bus, truck)">
              <input className="mono" value={form.path} onChange={(e) => setForm({ ...form, path: e.target.value })} placeholder="C:\AI_Drone_Trimmer\data\models\yolov8n.onnx" /></Field>
            <Field label="Ambang keyakinan"><input type="number" step="0.05" min="0.05" max="0.95" value={form.conf} onChange={(e) => setForm({ ...form, conf: Number(e.target.value) })} /></Field>
            <label className="check"><input type="checkbox" checked={form.validated} onChange={(e) => setForm({ ...form, validated: e.target.checked })} /> Model sudah divalidasi dengan data drone berlabel</label>
            <button className="btn btn-primary" disabled={!form.path} onClick={() => run(() => api.addModel({ kind: "detector", name: form.name, path: form.path, enabled: true, validated: form.validated, params: { conf: form.conf } }), "Model didaftarkan").then(reload)}>Daftarkan & aktifkan</button>
          </div>
          {d.configurations?.length > 0 && <table className="table table-compact" style={{ marginTop: 12 }}><thead><tr><th>Nama</th><th>Path</th><th>Aktif</th><th>Validasi</th><th /></tr></thead>
            <tbody>{d.configurations.map((m) => <tr key={m.id}><td>{m.name}</td><td className="mono small wrap-any">{m.path}</td><td>{m.enabled ? "Ya" : "–"}</td><td>{m.validated ? "Ya" : "Belum"}</td>
              <td><button className="btn btn-sm" onClick={() => run(() => api.updateModel(m.id, { enabled: !m.enabled }), "Diperbarui").then(reload)}>{m.enabled ? "Nonaktifkan" : "Aktifkan"}</button></td></tr>)}</tbody></table>}
        </Card>
        <Card title="Dataset dari koreksi operator">
          <p className="small">Setiap verifikasi, koreksi timestamp/titik/arah, penolakan kandidat, dan penetapan kondisi lalu lintas disimpan sebagai data berlabel
            (template, titik, arah, timestamp, putar balik, fitur visual, video sumber, label kualitas, label lalu lintas).</p>
          <div className="stat-inline"><b>{d.dataset?.feedback_records ?? 0}</b> rekaman koreksi</div>
          <button className="btn" onClick={async () => { const r = await run(() => api.exportDataset()); if (r) run(async () => r, `Dataset diekspor: ${r.records} rekaman → ${r.file}`); }}>Ekspor dataset (JSONL)</button>
          <p className="small muted">Folder: <span className="mono">{d.dataset?.dataset_dir}</span>. Lihat docs/MODEL_AI.md untuk alur pelatihan.</p>
        </Card>
      </div>
    </div>
  );
}

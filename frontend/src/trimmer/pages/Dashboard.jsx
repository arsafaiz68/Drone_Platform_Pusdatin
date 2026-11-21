import { Card, Empty, ErrorBox, Loading, ProgressBar, Stat, StatusBadge } from "../components/ui.jsx";
import { useLoad, usePolling } from "../hooks/useApi.js";
import { api, fmtDate, tripLabel } from "../services/api.js";

export default function Dashboard() {
  const { data, error, loading, reload } = useLoad(api.dashboard);
  usePolling(reload, 4000);
  if (loading && !data) return <div className="page"><Loading /></div>;
  const d = data || {};
  const hw = d.hardware || {};
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Ringkasan proyek, batch, dan perangkat pemrosesan lokal.</p>
        </div>
        <div className="row">
          <a className="btn" href="#/projects">Proyek baru</a>
          <a className="btn btn-primary" href="#/batches">Batch processing</a>
        </div>
      </header>
      <ErrorBox error={error} onRetry={reload} />
      <div className="stats">
        <Stat label="Proyek" value={d.projects ?? 0} />
        <Stat label="Batch" value={d.batches ?? 0} hint={`${d.batches_running ?? 0} berjalan`} />
        <Stat label="Video sumber" value={d.videos ?? 0} />
        <Stat label="Menunggu review" value={d.videos_review ?? 0} tone="warn" />
        <Stat label="Video gagal" value={d.videos_failed ?? 0} tone={d.videos_failed ? "err" : undefined} />
        <Stat label="Video hasil diekspor" value={d.exports_done ?? 0} tone="ok" />
      </div>
      <div className="grid-2">
        <Card title="Batch terbaru" actions={<a href="#/batches" className="btn btn-sm">Semua batch</a>}>
          {d.recent_batches && d.recent_batches.length ? (
            <table className="table">
              <thead><tr><th>Batch</th><th>Proyek</th><th>Template</th><th>Status</th><th style={{ width: 160 }}>Progres</th></tr></thead>
              <tbody>
                {d.recent_batches.map((b) => (
                  <tr key={b.id} className="clickable" onClick={() => { window.location.hash = `/batches/${b.id}`; }}>
                    <td><strong>{b.name}</strong><div className="small muted">{b.stats.total} video · {b.final_duration} dtk · {tripLabel(b.trip_mode)}</div></td>
                    <td>{b.project_name}</td>
                    <td>{b.template_name}</td>
                    <td><StatusBadge status={b.status} label={b.status_label} /></td>
                    <td><ProgressBar value={b.stats.progress} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty>Belum ada batch. Buat proyek lalu tambahkan batch video.</Empty>}
        </Card>
        <Card title="Perangkat aktif" actions={<a href="#/settings" className="btn btn-sm">Detail</a>}>
          <dl className="kv">
            <dt>Mode pemrosesan</dt><dd><StatusBadge status={hw.mode === "cuda" ? "done" : "paused"} label={hw.mode === "cuda" ? "GPU / CUDA" : "CPU"} /></dd>
            <dt>Nama perangkat</dt><dd>{hw.device_name || "–"}</dd>
            <dt>Status CUDA</dt><dd>{hw.cuda_status || "–"}</dd>
            <dt>Encoder GPU (NVENC)</dt><dd>{hw.nvenc_available ? "Tersedia" : "Tidak tersedia (libx264)"}</dd>
            <dt>RAM</dt><dd>{hw.ram_total_gb ? `${hw.ram_available_gb} / ${hw.ram_total_gb} GB tersedia` : "–"}</dd>
            <dt>CPU</dt><dd>{hw.cpu_cores} core</dd>
            <dt>Concurrency</dt><dd>rekomendasi {hw.recommended_concurrency}, maks {hw.max_concurrency}</dd>
          </dl>
        </Card>
      </div>
      <Card title="Ekspor terbaru" actions={<a href="#/exports" className="btn btn-sm">Riwayat ekspor</a>}>
        {d.recent_exports && d.recent_exports.length ? (
          <table className="table">
            <thead><tr><th>File</th><th>Jenis</th><th>Status</th><th>Waktu</th></tr></thead>
            <tbody>
              {d.recent_exports.map((e) => (
                <tr key={e.id}>
                  <td className="mono small">{e.output_path ? e.output_path.split(/[\\/]/).pop() : "–"}</td>
                  <td>{e.kind === "final" ? "Video hasil" : "Potongan individual"}</td>
                  <td><StatusBadge status={e.status === "done" ? "done" : e.status === "failed" ? "failed" : "running"} label={e.status} /></td>
                  <td className="small">{fmtDate(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty>Belum ada ekspor.</Empty>}
      </Card>
    </div>
  );
}

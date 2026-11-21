import { useEffect, useState } from "react";
import { DeleteBatchModal, ZipButton } from "../components/BatchActions.jsx";
import BatchFromDownloadModal from "../components/BatchFromDownloadModal.jsx";
import CreateBatchModal from "../components/CreateBatchModal.jsx";
import { Card, Empty, ErrorBox, Loading, ProgressBar, StatusBadge } from "../components/ui.jsx";
import { navigate, useLoad, usePolling } from "../hooks/useApi.js";
import { api, fmtDate, tripLabel } from "../services/api.js";

export default function Batches({ query = {} }) {
  const { data, error, loading, reload } = useLoad(() => api.batches(), []);
  const [open, setOpen] = useState(false);
  const [dlOpen, setDlOpen] = useState(!!query.import);
  const [delBatch, setDelBatch] = useState(null);
  useEffect(() => { if (query.import) setDlOpen(true); }, [query.import]);
  usePolling(reload, 4000);
  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Batch Processing</h1><p className="muted">Maksimal 24 video per batch. Setiap video dianalisis terpisah dan
          menghasilkan satu video hasil sendiri (24 video masuk → 24 video hasil, masing-masing 10–60 detik (kelipatan 5)).</p></div>
        <div className="row">
          <button className="btn" onClick={() => setDlOpen(true)}>Batch dari hasil unduhan</button>
          <button className="btn btn-primary" onClick={() => setOpen(true)}>Batch baru</button>
        </div>
      </header>
      <ErrorBox error={error} onRetry={reload} />
      <Card>
        {loading && !data ? <Loading /> : data && data.length ? (
          <table className="table">
            <thead><tr><th>Batch</th><th>Proyek</th><th>Template</th><th>Video</th><th>Durasi / video</th><th>Mode</th><th>Bersamaan</th><th>Status</th><th style={{ width: 160 }}>Progres</th><th>Aksi</th></tr></thead>
            <tbody>
              {data.map((b) => (
                <tr key={b.id} className="clickable" onClick={() => navigate(`/batches/${b.id}`)}>
                  <td><strong>{b.name}</strong><div className="small muted">{fmtDate(b.created_at)}</div></td>
                  <td>{b.project_name}</td><td>{b.template_name}</td>
                  <td>{b.stats.total} <span className="small muted">({b.stats.completed} selesai{b.stats.failed ? `, ${b.stats.failed} gagal` : ""})</span></td>
                  <td>{b.final_duration} dtk</td><td>{tripLabel(b.trip_mode)}</td><td>{b.concurrency}</td>
                  <td><StatusBadge status={b.status} label={b.status_label} />{b.recovered ? <div className="small muted">dipulihkan</div> : null}</td>
                  <td><ProgressBar value={b.stats.progress} /></td>
                  <td className="nowrap" onClick={(e) => e.stopPropagation()}>
                    <ZipButton batchId={b.id} className="btn btn-sm" label="ZIP" />{" "}
                    <button className="btn btn-sm btn-danger-ghost" title="Hapus batch" onClick={() => setDelBatch(b)}>Hapus</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty>Belum ada batch.</Empty>}
      </Card>
      {delBatch && <DeleteBatchModal batch={delBatch} onClose={() => setDelBatch(null)} onDeleted={reload} />}
      <CreateBatchModal open={open} onClose={() => setOpen(false)} onCreated={(b) => navigate(`/batches/${b.id}`)} />
      <BatchFromDownloadModal open={dlOpen} initialBatchId={query.import || null}
        onClose={() => { setDlOpen(false); if (query.import) navigate("/batches"); }}
        onCreated={(b) => navigate(`/batches/${b.id}`)} />
    </div>
  );
}

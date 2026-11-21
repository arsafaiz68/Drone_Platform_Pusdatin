import { Card, Empty, ErrorBox, Loading, ProgressBar, StatusBadge, useAction } from "../components/ui.jsx";
import { useLoad, usePolling } from "../hooks/useApi.js";
import { api, fmtDate, fmtSec } from "../services/api.js";

export default function Exports() {
  const { data, error, loading, reload } = useLoad(api.exports, []);
  const [run] = useAction();
  usePolling(reload, 3000);
  return (
    <div className="page">
      <header className="page-head"><div><h1>Riwayat Ekspor</h1><p className="muted">Semua hasil ekspor video final dan potongan individual.</p></div>
        <button className="btn" onClick={() => run(() => api.openFolder(null))}>Buka folder output</button></header>
      <ErrorBox error={error} onRetry={reload} />
      <Card>
        {loading && !data ? <Loading /> : data && data.length ? (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>#</th><th>File</th><th>Proyek</th><th>Jenis</th><th>Lokasi</th><th>Kondisi</th><th>Durasi</th><th>Mode</th><th>Status</th><th>Waktu</th><th /></tr></thead>
            <tbody>{data.map((e) => (
              <tr key={e.id}>
                <td>{e.id}</td>
                <td className="mono small wrap-any">{e.output_path ? e.output_path.split(/[\\/]/).pop() : "–"}{e.error && <div className="text-err">{e.error}</div>}</td>
                <td>{e.project_name}</td>
                <td>{e.kind === "final" ? "Video final" : "Potongan individual"}</td>
                <td>{e.location_name}</td><td>{e.traffic_condition}</td>
                <td className="mono">{e.duration ? fmtSec(e.duration) : "–"}</td>
                <td className="small">{e.mode || "–"} {e.encoder ? `· ${e.encoder}` : ""}</td>
                <td>{["queued", "running"].includes(e.status) ? <ProgressBar small value={e.progress} /> :
                  <StatusBadge status={e.status === "done" ? "done" : "failed"} label={e.status === "done" ? "Berhasil" : "Gagal"} />}</td>
                <td className="small">{fmtDate(e.created_at)}</td>
                <td className="nowrap">
                  {e.status === "done" && e.kind === "final" && <a className="btn btn-sm" href={api.downloadUrl(e.id)}>Unduh</a>}
                  {e.status === "done" && <button className="btn btn-sm btn-ghost" onClick={() => run(() => api.openFolder(e.output_path))}>Folder</button>}
                  <button className="btn btn-sm btn-ghost" onClick={() => run(() => api.final(e.final_video_id)).then((f) => { if (f) window.location.hash = `/review/${f.batch_id}?final=${f.id}&tab=final`; })}>Buka</button>
                </td>
              </tr>))}</tbody></table></div>
        ) : <Empty>Belum ada ekspor.</Empty>}
      </Card>
    </div>
  );
}

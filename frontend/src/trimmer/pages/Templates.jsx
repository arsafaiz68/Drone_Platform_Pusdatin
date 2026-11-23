import RouteDiagram from "../components/RouteDiagram.jsx";
import { Card, ErrorBox, Loading } from "../components/ui.jsx";
import { useLoad } from "../hooks/useApi.js";
import { api } from "../services/api.js";

export default function Templates() {
  const { data, error, loading, reload } = useLoad(api.templates, []);
  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Template Pemantauan</h1>
          <p className="muted">Tujuh template terpusat (backend/app/core/templates_config.py). Bobot kepentingan menentukan alokasi durasi pada video final.</p></div>
      </header>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Loading /> : (
        <div className="tmpl-grid">
          {(data || []).map((t, i) => (
            <Card key={t.code} title={`Template ${i + 1} — ${t.name}`}>
              <p className="small muted">{t.description}</p>
              <RouteDiagram outbound={t.route_outbound} ret={t.route_return} turnarounds={t.turnarounds} />
              {t.turnarounds.length > 1 && <p className="small"><b>Putar balik:</b> titik {t.turnarounds.join(" dan titik ")} (dipertahankan sebagai dua instruksi terpisah).</p>}
              <table className="table table-compact">
                <thead><tr><th>Titik</th><th>Nama</th><th>Keterangan</th><th title="Bobot alokasi durasi">Bobot</th></tr></thead>
                <tbody>
                  {t.points.map((p) => (
                    <tr key={p.code}><td><span className={`route-pt ${p.code === "H" ? "route-home" : ""}`}>{p.code}</span></td>
                      <td>{p.name}</td><td className="small">{p.description}</td><td className="mono">{p.importance}</td></tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

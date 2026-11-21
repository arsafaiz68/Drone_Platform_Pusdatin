import { useState } from "react";
import { dirLabel, pointLabel } from "../services/api.js";

/**
 * Timeline video hasil (satu video sumber). Lebar blok proporsional terhadap durasi.
 * Warna: biru = pergi, ungu = kembali; garis putus = dikoreksi operator.
 */
export default function Timeline({ segments, target, selectedId, onSelect, onReorder }) {
  const [dragId, setDragId] = useState(null);
  const total = segments.reduce((a, s) => a + s.duration, 0);
  const scale = Math.max(target, total) || 1;
  const drop = (overId) => {
    if (dragId == null || dragId === overId) return;
    const ids = segments.map((s) => s.id);
    const from = ids.indexOf(dragId);
    const to = ids.indexOf(overId);
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    onReorder && onReorder(ids);
    setDragId(null);
  };
  return (
    <div className="timeline">
      <div className="timeline-row">
        {segments.map((s, i) => (
          <div key={s.id} draggable onDragStart={() => setDragId(s.id)} onDragOver={(e) => e.preventDefault()}
            onDrop={() => drop(s.id)} onClick={() => onSelect && onSelect(s)}
            className={`tl-block dir-${s.direction} ${s.edited ? "tl-edited" : "tl-ai"} ${s.role === "support" ? "tl-support" : ""} ${selectedId === s.id ? "tl-selected" : ""}`}
            style={{ width: `${(s.duration / scale) * 100}%` }}
            title={`#${i + 1} ${s.point_code ? `Titik ${s.point_code} · ${dirLabel(s.direction)}` : "Potongan pengisi"} · ${s.duration.toFixed(1)} dtk · ${s.video_filename}${s.edited ? " · dikoreksi operator" : " · hasil AI"}`}>
            <span className="tl-num">{i + 1}</span>
            <span className="tl-label">{pointLabel(s)}</span>
            <span className="tl-dur">{s.duration.toFixed(1)}s</span>
          </div>
        ))}
        {total < target && (
          <div className="tl-gap" style={{ width: `${((target - total) / scale) * 100}%` }}>
            sisa {(target - total).toFixed(1)}s
          </div>
        )}
      </div>
      <div className="timeline-scale">
        <span>0s</span>
        <span className="tl-target" style={{ left: `${(target / scale) * 100}%` }}>target {target}s</span>
        {scale > target + 0.5 ? <span>{scale.toFixed(1)}s</span> : <span />}
      </div>
      <div className="timeline-legend small muted">
        <span><i className="lg lg-out" /> Pergi</span>
        <span><i className="lg lg-ret" /> Kembali</span>
        <span><i className="lg lg-ai" /> Hasil AI</span>
        <span><i className="lg lg-edit" /> Dikoreksi operator</span>
        <span><i className="lg lg-sup" /> Momen pendukung / pengisi</span>
        <span>Seret blok untuk mengubah urutan</span>
      </div>
    </div>
  );
}

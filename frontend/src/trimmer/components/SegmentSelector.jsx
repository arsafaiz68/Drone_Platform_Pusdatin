import { useEffect, useRef, useState } from "react";
import { fmtSec } from "../services/api.js";

/**
 * Pemilih segmen di video: geser pegangan AWAL/AKHIR atau seret area di lintasan untuk memilih
 * rentang. Saat pegangan digeser, pemutar ikut pindah ke frame tersebut sehingga titik potong
 * bisa dipilih secara visual.
 *
 * props: duration, value {start, end}, onChange({start, end}), playerRef, markers, label, actions
 */
export default function SegmentSelector({ duration, value, onChange, playerRef, markers = [], label, actions }) {
  const track = useRef(null);
  const drag = useRef(null);
  const [hover, setHover] = useState(null);
  const total = Number(duration) || 0;
  const a = Math.max(0, Math.min(value?.start ?? 0, total));
  const b = Math.max(a, Math.min(value?.end ?? 0, total));
  const pct = (t) => (total ? `${(t / total) * 100}%` : "0%");
  const round = (t) => Math.round(t * 10) / 10;

  const timeAt = (clientX) => {
    const r = track.current.getBoundingClientRect();
    return Math.max(0, Math.min(total, ((clientX - r.left) / r.width) * total));
  };
  const seek = (t) => playerRef?.current?.seek(t);

  useEffect(() => {
    const move = (e) => {
      if (!drag.current) return;
      const t = round(timeAt(e.clientX));
      const d = drag.current;
      let next;
      if (d.mode === "start") next = { start: Math.min(t, b - 0.5), end: b };
      else if (d.mode === "end") next = { start: a, end: Math.max(t, a + 0.5) };
      else if (d.mode === "new") next = t >= d.origin ? { start: d.origin, end: Math.max(t, d.origin + 0.5) } : { start: t, end: d.origin };
      else { // geser seluruh rentang
        const len = d.b - d.a;
        const s = Math.max(0, Math.min(total - len, d.a + (t - d.origin)));
        next = { start: round(s), end: round(s + len) };
      }
      next = { start: round(Math.max(0, next.start)), end: round(Math.min(total, next.end)) };
      onChange(next);
      seek(d.mode === "end" ? next.end : next.start);
    };
    const up = () => { drag.current = null; document.body.classList.remove("is-dragging"); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  });

  const start = (mode, e) => {
    e.preventDefault();
    e.stopPropagation();
    const t = round(timeAt(e.clientX));
    drag.current = { mode, origin: t, a, b };
    document.body.classList.add("is-dragging");
    if (mode === "new") { onChange({ start: t, end: Math.min(total, t + 0.5) }); seek(t); }
  };
  const nudge = (which, delta) => {
    const next = which === "start"
      ? { start: round(Math.max(0, Math.min(a + delta, b - 0.5))), end: b }
      : { start: a, end: round(Math.min(total, Math.max(b + delta, a + 0.5))) };
    onChange(next);
    seek(which === "start" ? next.start : next.end);
  };
  const fromPlayer = (which) => {
    const t = round(playerRef?.current?.currentTime() ?? 0);
    if (which === "start") onChange({ start: t, end: b > t + 0.5 ? b : round(Math.min(total, t + 3)) });
    else onChange({ start: a < t - 0.5 ? a : round(Math.max(0, t - 3)), end: t });
  };

  if (!total) return null;
  return (
    <div className="seg-select">
      <div className="seg-select-head">
        <strong className="small">{label || "Pilih segmen di video"}</strong>
        <span className="small muted">Seret area kosong untuk memilih rentang baru · geser pegangan untuk mengubah awal/akhir · seret pilihan untuk menggeser</span>
      </div>
      <div ref={track} className="seg-track" onPointerDown={(e) => start("new", e)}
        onPointerMove={(e) => setHover(timeAt(e.clientX))} onPointerLeave={() => setHover(null)}>
        {markers.map((m, i) => (
          <div key={i} className={`seg-mark ${m.className || ""}`} title={m.title}
            style={{ left: pct(m.start), width: `max(2px, ${pct(m.end - m.start)})` }} />
        ))}
        <div className="seg-range" style={{ left: pct(a), width: pct(b - a) }} onPointerDown={(e) => start("move", e)}
          title={`${fmtSec(a)} – ${fmtSec(b)} (${(b - a).toFixed(1)} dtk)`} />
        <div className="seg-handle seg-handle-start" style={{ left: pct(a) }} onPointerDown={(e) => start("start", e)} title="Geser untuk mengubah AWAL" />
        <div className="seg-handle seg-handle-end" style={{ left: pct(b) }} onPointerDown={(e) => start("end", e)} title="Geser untuk mengubah AKHIR" />
        {hover != null && !drag.current && <div className="seg-hover" style={{ left: pct(hover) }}><span>{fmtSec(hover)}</span></div>}
      </div>
      <div className="seg-select-foot">
        <div className="seg-time">
          <span className="small muted">Awal</span>
          <button className="btn btn-sm btn-ghost" onClick={() => nudge("start", -0.5)} title="-0,5 dtk">−</button>
          <b className="mono">{fmtSec(a)}</b>
          <button className="btn btn-sm btn-ghost" onClick={() => nudge("start", 0.5)} title="+0,5 dtk">+</button>
          <button className="btn btn-sm" onClick={() => fromPlayer("start")} title="Ambil posisi pemutar sebagai awal">⌖ posisi</button>
        </div>
        <div className="seg-time">
          <span className="small muted">Akhir</span>
          <button className="btn btn-sm btn-ghost" onClick={() => nudge("end", -0.5)} title="-0,5 dtk">−</button>
          <b className="mono">{fmtSec(b)}</b>
          <button className="btn btn-sm btn-ghost" onClick={() => nudge("end", 0.5)} title="+0,5 dtk">+</button>
          <button className="btn btn-sm" onClick={() => fromPlayer("end")} title="Ambil posisi pemutar sebagai akhir">⌖ posisi</button>
        </div>
        <span className="mono small">Durasi {(b - a).toFixed(1)} dtk</span>
        <button className="btn btn-sm" onClick={() => playerRef?.current?.playRange(a, b)}>▶ Putar pilihan</button>
        <span className="seg-actions">{actions}</span>
      </div>
    </div>
  );
}

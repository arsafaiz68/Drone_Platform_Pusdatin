// Dialog Export / Render: pengaturan kualitas, perkiraan ukuran, progres, batal, unduh hasil.
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { fmtBytes, fmtTime, outputSize, projectDuration } from "../lib/model.js";
import { textToPNG } from "../lib/textDraw.js";
import Icon from "./Icon.jsx";

const RES = [["1080", "Full HD (1080p)"], ["1440", "2K (1440p)"], ["2160", "4K (2160p)"], ["source", "Ikuti resolusi asli"]];
const FPS = [["source", "Ikuti sumber"], [24, "24 fps"], [25, "25 fps"], [30, "30 fps"], [50, "50 fps"], [60, "60 fps"]];
const QUAL = [["high", "High Quality", "CRF 18 · preset slow"], ["very_high", "Very High Quality", "CRF 16 · preset slow"],
  ["max", "Maximum Quality", "CRF 14 · preset veryslow (lama)"]];

const fmtEta = (s) => (s == null ? "menghitung…" : s < 60 ? `${Math.round(s)} dtk` : `${Math.floor(s / 60)} mnt ${Math.round(s % 60)} dtk`);

export default function ExportDialog({ project, mm, system, onClose, ensureSaved, onExportSettings, notify }) {
  const [exp, setExp] = useState({ filename: "", ...project.export });
  const [est, setEst] = useState(null);
  const [job, setJob] = useState(null);
  const [history, setHistory] = useState([]);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef(null);
  const size = outputSize(project, mm, exp);
  const dur = projectDuration(project);

  useEffect(() => { api.renders(project.id).then((r) => { setHistory(r); const run = r.find((j) => ["queued", "running"].includes(j.status)); if (run) setJob(run); }).catch(() => {}); }, [project.id]);
  useEffect(() => {
    let alive = true;
    const t = setTimeout(async () => {
      try { const saved = await ensureSaved(); const e = await api.estimate(saved.id, exp); if (alive) setEst(e); } catch (e) { if (alive) setEst({ error: e.message }); }
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [exp.resolution, exp.fps, exp.codec, exp.quality]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    clearInterval(pollRef.current);
    if (job && ["queued", "running"].includes(job.status)) {
      pollRef.current = setInterval(async () => {
        try {
          const j = await api.renderJob(job.id);
          setJob(j);
          if (!["queued", "running"].includes(j.status)) api.renders(project.id).then(setHistory).catch(() => {});
        } catch { /* */ }
      }, 700);
    }
    return () => clearInterval(pollRef.current);
  }, [job?.id, job?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    setStarting(true);
    try {
      onExportSettings({ resolution: exp.resolution, fps: exp.fps, codec: exp.codec, quality: exp.quality });
      const saved = await ensureSaved({ ...project, export: { ...project.export, resolution: exp.resolution, fps: exp.fps, codec: exp.codec, quality: exp.quality } });
      const e = await api.estimate(saved.id, exp);
      const hidden = new Set(saved.tracks.filter((t) => t.hidden).map((t) => t.id));
      const texts = {};
      for (const c of saved.clips) {
        const tr = saved.tracks.find((t) => t.id === c.track);
        if (tr?.kind === "text" && !hidden.has(c.track) && c.text) texts[c.id] = textToPNG(c, e.width, e.height);
      }
      const j = await api.render(saved.id, exp, texts);
      setJob(j);
    } catch (err) { notify(err.message); } finally { setStarting(false); }
  };

  const running = job && ["queued", "running"].includes(job.status);
  const pct = Math.round((job?.progress || 0) * 100);
  const warnings = est?.warnings || [];
  return (
    <div className="modal-bg" onPointerDown={(e) => { if (e.target === e.currentTarget && !running) onClose(); }}>
      <div className="modal">
        <div className="modal-head"><span><Icon n="export" /> Export / Render video</span><button className="ib" onClick={onClose} title="Tutup"><Icon n="x" /></button></div>
        <div className="modal-body ex-grid">
          <div>
            <div className="field"><label>Resolusi</label>
              <select value={exp.resolution} disabled={running} onChange={(e) => setExp({ ...exp, resolution: e.target.value })}>
                {RES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
            <div className="field"><label>Frame rate</label>
              <select value={exp.fps} disabled={running} onChange={(e) => setExp({ ...exp, fps: e.target.value === "source" ? "source" : Number(e.target.value) })}>
                {FPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
            <div className="field"><label>Format</label>
              <select value={exp.codec} disabled={running} onChange={(e) => setExp({ ...exp, codec: e.target.value })}>
                <option value="h264">MP4 · H.264 (paling kompatibel)</option>
                <option value="hevc" disabled={system && !system.hevc}>MP4 · H.265 / HEVC{system && !system.hevc ? " (tidak tersedia)" : " (file lebih kecil)"}</option>
              </select></div>
            <div className="field"><label>Preset kualitas</label>
              <div className="qual">{QUAL.map(([v, l, d]) => (
                <button key={v} disabled={running} className={exp.quality === v ? "on" : ""} onClick={() => setExp({ ...exp, quality: v })}><b>{l}</b><span>{d}</span></button>))}</div></div>
            <div className="field"><label>Nama file (opsional)</label>
              <input value={exp.filename || ""} disabled={running} placeholder={`${project.name.replace(/\s+/g, "_")}_YYYYMMDD_HHMMSS.mp4`} onChange={(e) => setExp({ ...exp, filename: e.target.value })} /></div>
          </div>
          <div className="ex-side">
            <dl className="ex-info">
              <dt>Resolusi output</dt><dd className="mono">{(est?.width || size.width)} × {(est?.height || size.height)}</dd>
              <dt>Frame rate</dt><dd className="mono">{est?.fps || size.fps} fps</dd>
              <dt>Durasi</dt><dd className="mono">{fmtTime(dur)}</dd>
              <dt>Encoding</dt><dd>{exp.codec === "hevc" ? "H.265" : "H.264"} · CRF {est?.crf ?? "–"} · {est?.preset || "–"} · yuv420p</dd>
              <dt>Audio</dt><dd>AAC 320 kbps · 48 kHz stereo</dd>
              <dt>Perkiraan ukuran</dt><dd className="mono">≈ {fmtBytes(est?.estimated_size_bytes)}</dd>
            </dl>
            {est?.error && <div className="note err">{est.error}</div>}
            {warnings.map((w, i) => <div key={i} className="note warn">{w}</div>)}
            {system && <p className="muted xs">Perangkat: {system.cpu_cores} core CPU · RAM {system.ram_total_gb} GB · render memakai FFmpeg lokal, video tidak diunggah ke mana pun.</p>}
          </div>
        </div>
        {job && (
          <div className="ex-job">
            <div className="row-between"><b>{job.message}</b><span className="mono">{job.status === "done" ? "100%" : `${pct}%`}</span></div>
            <div className={`bar ${job.status}`}><i style={{ width: `${job.status === "done" ? 100 : pct}%` }} /></div>
            <div className="row-between xs muted">
              <span>Status: {({ queued: "antre", running: "merender", done: "selesai", failed: "gagal", cancelled: "dibatalkan" })[job.status]} · {job.settings.width}×{job.settings.height} · {job.settings.fps} fps · {job.settings.codec}</span>
              {running && <span>Sisa waktu: {fmtEta(job.eta_seconds)} · berjalan {fmtEta(job.elapsed_seconds)}</span>}
            </div>
            {job.status === "failed" && <div className="note err">{job.error}</div>}
            {job.status === "done" && job.result && (
              <div className="ex-result">
                <video src={api.streamUrl(job.id)} controls preload="metadata" />
                <dl className="ex-info">
                  <dt>File</dt><dd className="mono wrap">{job.filename}</dd>
                  <dt>Resolusi</dt><dd className="mono">{job.result.width} × {job.result.height}</dd>
                  <dt>Durasi</dt><dd className="mono">{fmtTime(job.result.duration)}</dd>
                  <dt>Format</dt><dd>{job.result.format} · {job.result.vcodec?.toUpperCase()} + {job.result.acodec?.toUpperCase()} · {job.result.fps} fps</dd>
                  <dt>Ukuran</dt><dd className="mono">{fmtBytes(job.result.size_bytes)}</dd>
                </dl>
              </div>)}
          </div>)}
        {history.filter((h) => h.status === "done" && h.id !== job?.id).length > 0 && (
          <div className="ex-hist"><div className="sec-title">Render sebelumnya (sesi ini)</div>
            {history.filter((h) => h.status === "done" && h.id !== job?.id).map((h) => (
              <div key={h.id} className="row-between xs"><span className="mono">{h.filename}</span><span>{fmtBytes(h.result?.size_bytes)} · <a href={api.downloadUrl(h.id)}>Unduh</a></span></div>))}
          </div>)}
        <div className="modal-foot">
          {job?.status === "done" && <>
            <a className="btn primary" href={api.downloadUrl(job.id)}><Icon n="import" size={14} /> Download hasil</a>
            <button className="btn" onClick={() => api.openFolder(job.output_path)}><Icon n="folder" size={14} /> Buka folder</button>
          </>}
          <span className="grow" />
          {running ? <button className="btn danger" onClick={async () => setJob(await api.cancelRender(job.id))}><Icon n="stop" size={14} /> Cancel render</button>
            : <button className="btn primary" disabled={starting || !project.clips.length || est?.error} onClick={start}>
              <Icon n="export" size={14} /> {starting ? "Menyiapkan…" : job ? "Render ulang" : "Mulai render"}</button>}
          {!running && <button className="btn ghost" onClick={onClose}>Tutup</button>}
        </div>
      </div>
    </div>
  );
}

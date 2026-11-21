// Preview Monitor: komposisi timeline digambar ke <canvas> setiap frame, dengan elemen
// <video>/<audio> tersembunyi yang disinkronkan ke jam playhead. Aturan tata letak, opacity,
// fade, dan amplop volume memakai fungsi yang sama dengan render backend.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { aspectRatio, clamp, clipBox, clipEnd, envelope, fmtTime, projectDuration, visualAlpha } from "../lib/model.js";
import { drawText, textLayout } from "../lib/textDraw.js";
import Icon from "./Icon.jsx";

const PRELOAD_BEFORE = 2.0;
const PRELOAD_AFTER = 0.5;

export default function Preview({ project, mm, time, playing, onPlayingChange, onTime, selectedId, onSelect,
  onLivePatch, onCommitFrom }) {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const holderRef = useRef(null);
  const pool = useRef(new Map());          // clipId -> { el, mid }
  const images = useRef(new Map());        // mediaId -> HTMLImageElement
  const st = useRef({ project, mm, time, playing, selectedId, t0: time, p0: 0, lastEmit: 0 });
  const [box, setBox] = useState({ w: 640, h: 360 });
  const dragRef = useRef(null);

  st.current.project = project;
  st.current.mm = mm;
  st.current.selectedId = selectedId;
  st.current.onTime = onTime;
  st.current.onPlayingChange = onPlayingChange;
  const ratio = aspectRatio(project, mm);
  const duration = projectDuration(project);

  // ------------------------------------------------------------- ukuran kanvas mengikuti panel
  useEffect(() => {
    const el = wrapRef.current;
    const ro = new ResizeObserver(() => {
      const W = el.clientWidth, H = el.clientHeight;
      let w = W, h = W / ratio;
      if (h > H) { h = H; w = H * ratio; }
      setBox({ w: Math.max(40, Math.floor(w)), h: Math.max(40, Math.floor(h)) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ratio]);

  // ------------------------------------------------------------- jam playhead
  useEffect(() => {
    const s = st.current;
    if (playing && !s.playing) { s.t0 = s.time; s.p0 = performance.now(); }
    s.playing = playing;
  }, [playing]);
  useEffect(() => {
    const s = st.current;
    if (!s.playing) s.time = time;
    else if (Math.abs(time - currentT()) > 0.25) { s.t0 = time; s.p0 = performance.now(); s.time = time; }
  }, [time]); // eslint-disable-line react-hooks/exhaustive-deps

  const currentT = () => {
    const s = st.current;
    return s.playing ? s.t0 + (performance.now() - s.p0) / 1000 : s.time;
  };

  // ------------------------------------------------------------- elemen media
  const getEl = (c, m, asAudio) => {
    let rec = pool.current.get(c.id);
    if (rec && (rec.mid !== m.id || rec.path !== m.path)) { disposeRec(rec); pool.current.delete(c.id); rec = null; }
    if (!rec) {
      const el = document.createElement(asAudio ? "audio" : "video");
      el.preload = "auto";
      el.playsInline = true;
      el.src = `${api.fileUrl(m.id)}?v=${encodeURIComponent(m.path || "")}`;
      holderRef.current?.appendChild(el);
      rec = { el, mid: m.id, proxy: m.proxy, path: m.path };
      pool.current.set(c.id, rec);
    } else if (rec.proxy !== m.proxy && m.proxy === "ready") {
      rec.el.src = `${api.fileUrl(m.id)}?p=1&v=${encodeURIComponent(m.path || "")}`; rec.proxy = m.proxy; // proxy preview baru siap
    }
    return rec.el;
  };
  const disposeRec = (rec) => { try { rec.el.pause(); rec.el.removeAttribute("src"); rec.el.load(); rec.el.remove(); } catch { /* */ } };
  const getImg = (m) => {
    const key = `${m.id}|${m.path}`;
    let img = images.current.get(key);
    if (!img) { img = new Image(); img.src = `${api.fileUrl(m.id)}?v=${encodeURIComponent(m.path || "")}`; images.current.set(key, img); }
    return img;
  };

  // ------------------------------------------------------------- loop gambar
  useEffect(() => {
    let raf;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      const s = st.current;
      const p = s.project;
      const cv = canvasRef.current;
      if (!p || !cv) return;
      let t = currentT();
      const D = projectDuration(p);
      if (s.playing && t >= D) {
        t = D; s.playing = false; s.time = D;
        s.onPlayingChange(false); s.onTime(D);
      }
      if (s.playing && performance.now() - s.lastEmit > 66) { s.lastEmit = performance.now(); s.time = t; s.onTime(t); }
      const ctx = cv.getContext("2d");
      const W = cv.width, H = cv.height;
      ctx.globalAlpha = 1;
      ctx.fillStyle = p.settings?.background || "#000";
      ctx.fillRect(0, 0, W, H);
      const tracks = {};
      p.tracks.forEach((tr) => { tracks[tr.id] = tr; });
      const keep = new Set();
      const sel = [];
      // sinkronisasi semua klip ber-media (video/audio) di sekitar playhead
      for (const c of p.clips) {
        const m = c.media_id && s.mm[c.media_id];
        const tr = tracks[c.track];
        if (!m || !tr || m.kind === "image" || m.missing) continue;
        if (t < c.start - PRELOAD_BEFORE || t > clipEnd(c) + PRELOAD_AFTER) continue;
        const asAudio = tr.kind === "audio";
        const el = getEl(c, m, asAudio);
        keep.add(c.id);
        const active = t >= c.start && t < clipEnd(c);
        const want = (c.in || 0) + (active ? t - c.start : 0);
        const audible = m.has_audio && !tr.muted;
        el.muted = !audible;
        if (audible) el.volume = clamp((c.volume ?? 1) * (tr.volume ?? 1) * envelope(c, t - c.start), 0, 1);
        if (active && s.playing) {
          if (el.paused) {
            if (Math.abs(el.currentTime - want) > 0.05) el.currentTime = want;
            el.play().catch(() => {});
          } else if (Math.abs(el.currentTime - want) > 0.3) el.currentTime = want;
        } else {
          if (!el.paused) el.pause();
          if (!el.seeking && Math.abs(el.currentTime - want) > (active ? 0.02 : 0.1)) el.currentTime = want;
        }
      }
      for (const [id, rec] of pool.current) if (!keep.has(id)) { disposeRec(rec); pool.current.delete(id); }
      // gambar lapisan visual dari bawah ke atas
      const visual = p.tracks.filter((tr) => tr.kind !== "audio").slice().reverse();
      for (const tr of visual) {
        if (tr.hidden) continue;
        const clips = p.clips.filter((c) => c.track === tr.id && t >= c.start && t < clipEnd(c)).sort((a, b) => a.start - b.start);
        for (const c of clips) {
          const local = t - c.start;
          const a = visualAlpha(c, local);
          if (tr.kind === "text") {
            const b = drawText(ctx, c, W, H, a);
            if (c.id === s.selectedId && b) sel.push(b);
            continue;
          }
          const m = s.mm[c.media_id];
          if (!m || m.missing) continue;
          const b = clipBox(c, m, W, H);
          ctx.globalAlpha = a;
          if (m.kind === "image") {
            const img = getImg(m);
            if (img.complete && img.naturalWidth) ctx.drawImage(img, b.x, b.y, b.w, b.h);
          } else {
            const el = pool.current.get(c.id)?.el;
            if (el && el.readyState >= 2) ctx.drawImage(el, b.x, b.y, b.w, b.h);
          }
          ctx.globalAlpha = 1;
          if (c.id === s.selectedId) sel.push(b);
        }
      }
      for (const b of sel) {
        ctx.save(); ctx.strokeStyle = "#0a84ff"; ctx.lineWidth = Math.max(2, W / 400);
        ctx.setLineDash([W / 80, W / 160]); ctx.strokeRect(b.x, b.y, b.w, b.h); ctx.restore();
      }
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { for (const rec of pool.current.values()) disposeRec(rec); pool.current.clear(); }, []);

  // ------------------------------------------------------------- drag posisi di monitor
  const toCanvas = (e) => {
    const r = canvasRef.current.getBoundingClientRect();
    const cv = canvasRef.current;
    return { x: (e.clientX - r.left) * (cv.width / r.width), y: (e.clientY - r.top) * (cv.height / r.height) };
  };
  const hitTest = useCallback((pt) => {
    const s = st.current, p = s.project, cv = canvasRef.current;
    const t = currentT();
    const W = cv.width, H = cv.height;
    const ctx = cv.getContext("2d");
    const order = p.tracks.filter((tr) => tr.kind !== "audio" && !tr.hidden && !tr.locked); // atas -> bawah
    const cands = [];
    for (const tr of order) {
      const clips = p.clips.filter((c) => c.track === tr.id && t >= c.start && t < clipEnd(c)).sort((a, b) => b.start - a.start);
      for (const c of clips) {
        const b = tr.kind === "text" ? textLayout(ctx, c, W, H).box : clipBox(c, s.mm[c.media_id], W, H);
        if (pt.x >= b.x && pt.x <= b.x + b.w && pt.y >= b.y && pt.y <= b.y + b.h) cands.push({ c, tr });
      }
    }
    return cands.find((x) => x.c.id === s.selectedId) || cands[0] || null;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onPointerDown = (e) => {
    const pt = toCanvas(e);
    const hit = hitTest(pt);
    if (!hit) { onSelect(null); return; }
    onSelect(hit.c.id);
    const isText = hit.tr.kind === "text";
    dragRef.current = { id: hit.c.id, start: pt, isText, x0: isText ? hit.c.offset_x || 0 : hit.c.x ?? 0.5,
      y0: isText ? hit.c.offset_y || 0 : hit.c.y ?? 0.5, snapshot: st.current.project, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    const d = dragRef.current;
    if (!d) return;
    const pt = toCanvas(e), cv = canvasRef.current;
    let nx = d.x0 + (pt.x - d.start.x) / cv.width, ny = d.y0 + (pt.y - d.start.y) / cv.height;
    if (!d.isText) { // magnet ke tengah
      if (Math.abs(nx - 0.5) < 0.01) nx = 0.5;
      if (Math.abs(ny - 0.5) < 0.01) ny = 0.5;
    }
    d.moved = true;
    onLivePatch(d.id, d.isText ? { offset_x: round4(nx), offset_y: round4(ny) } : { x: round4(nx), y: round4(ny) });
  };
  const onPointerUp = () => {
    const d = dragRef.current;
    dragRef.current = null;
    if (d?.moved) onCommitFrom(d.snapshot);
  };

  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const cw = Math.min(1920, Math.round(box.w * dpr)), ch = Math.round(cw / ratio);
  const step = (d) => { onPlayingChange(false); onTime(clamp(currentT() + d, 0, duration)); };

  return (
    <div className="pv">
      <div className="pv-stage" ref={wrapRef}>
        <canvas ref={canvasRef} width={cw} height={ch} style={{ width: box.w, height: box.h }}
          onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} />
        <div ref={holderRef} className="pv-holder" aria-hidden="true" />
        {!project.clips.length && <div className="pv-empty">Seret media dari Media Bin ke timeline untuk mulai menyusun video.</div>}
      </div>
      <div className="pv-bar">
        <span className="pv-time mono">{fmtTime(time)}</span>
        <div className="pv-ctrls">
          <button className="ib" title="Ke awal (Home)" onClick={() => { onPlayingChange(false); onTime(0); }}><Icon n="prev" /></button>
          <button className="ib" title="Mundur 1 frame (←)" onClick={() => step(-1 / (project.settings?.fps || 30))}><Icon n="stepb" /></button>
          <button className="ib ib-play" title="Putar / jeda (Spasi)" onClick={() => onPlayingChange(!playing)}><Icon n={playing ? "pause" : "play"} size={18} fill /></button>
          <button className="ib" title="Stop — kembali ke awal" onClick={() => { onPlayingChange(false); onTime(0); }}><Icon n="stop" fill /></button>
          <button className="ib" title="Maju 1 frame (→)" onClick={() => step(1 / (project.settings?.fps || 30))}><Icon n="stepf" /></button>
          <button className="ib" title="Ke akhir (End)" onClick={() => { onPlayingChange(false); onTime(duration); }}><Icon n="next" /></button>
        </div>
        <span className="pv-time mono muted">{fmtTime(duration)}</span>
      </div>
    </div>
  );
}

const round4 = (v) => Math.round(v * 10000) / 10000;

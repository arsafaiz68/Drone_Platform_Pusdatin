// Timeline multi-track: ruler, playhead, klip yang dapat digeser/di-trim/dipindah track,
// drop media dari Media Bin, zoom, snapping, dan kontrol track (visibility/mute/lock/volume/urutan layer).
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { ACCEPT, MIN_CLIP, canAccept, clamp, clipEnd, contentEnd, envelope, fmtTime, mediaMaxDuration,
  projectDuration, round3, snap, snapPoints } from "../lib/model.js";
import Icon from "./Icon.jsx";

const HEAD = 200;
const RULER_H = 30;
const ROW_H = { video: 66, image: 50, text: 44, audio: 62 };
const STEPS = [0.04, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
export const ZOOM_MIN = 2, ZOOM_MAX = 400;

export function clipKind(c, mm) { return c.media_id ? mm[c.media_id]?.kind : "text"; }

export default function Timeline({ project, mm, zoom, setZoom, time, onSeek, selectedId, onSelect, live, commit,
  onDropMedia, onDropText, notify, snapOn, setSnapOn }) {
  const scrollRef = useRef(null);
  const [dropHint, setDropHint] = useState(null); // {track, t}
  const [vw, setVw] = useState(1000);
  const dur = projectDuration(project);
  const end = Math.max(dur, contentEnd(project));
  const laneW = Math.max(vw - HEAD, (end + 30) * zoom);
  const p = project;

  useEffect(() => {
    const el = scrollRef.current;
    const ro = new ResizeObserver(() => setVw(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ctrl + scroll = zoom di posisi kursor
  useEffect(() => {
    const el = scrollRef.current;
    const onWheel = (e) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const x = e.clientX - r.left - HEAD + el.scrollLeft;
      const tAt = x / zoom;
      const nz = clamp(zoom * (e.deltaY < 0 ? 1.2 : 1 / 1.2), ZOOM_MIN, ZOOM_MAX);
      setZoom(nz);
      requestAnimationFrame(() => { el.scrollLeft = tAt * nz - (e.clientX - r.left - HEAD); });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoom, setZoom]);

  // playhead tetap terlihat saat diputar
  useEffect(() => {
    const el = scrollRef.current;
    const x = time * zoom;
    if (x < el.scrollLeft || x > el.scrollLeft + el.clientWidth - HEAD - 40) el.scrollLeft = Math.max(0, x - 80);
  }, [Math.floor(time * zoom / 200)]); // eslint-disable-line react-hooks/exhaustive-deps

  const tFromClient = (clientX) => {
    const el = scrollRef.current;
    const r = el.getBoundingClientRect();
    return Math.max(0, (clientX - r.left - HEAD + el.scrollLeft) / zoom);
  };

  // ------------------------------------------------------------------ ruler
  const ticks = useMemo(() => {
    const major = STEPS.find((s) => s * zoom >= 80) || 600;
    const minor = major / 5;
    const out = [];
    const n = Math.ceil(laneW / zoom / minor) + 1;
    for (let i = 0; i <= n; i++) {
      const t = i * minor;
      const isMajor = Math.abs(t / major - Math.round(t / major)) < 1e-6;
      out.push({ t, isMajor });
    }
    return { out, major };
  }, [zoom, laneW]);

  const onRulerDown = (e) => {
    onSeek(tFromClient(e.clientX));
    const move = (ev) => onSeek(tFromClient(ev.clientX));
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  // ------------------------------------------------------------------ drag klip
  const startDrag = (e, c, mode) => {
    e.stopPropagation();
    if (e.button !== 0) return;
    const tr = p.tracks.find((t) => t.id === c.track);
    onSelect(c.id);
    if (tr?.locked) { notify?.("Track terkunci — buka kunci untuk mengedit."); return; }
    const snapshot = p;
    const kind = clipKind(c, mm);
    const m = mm[c.media_id];
    const maxDur = mediaMaxDuration(m);
    const x0 = e.clientX;
    const pts = snapPoints(p, c.id, time);
    const tol = 8 / zoom;
    let moved = false;
    const move = (ev) => {
      const dt = (ev.clientX - x0) / zoom;
      if (!moved && Math.abs(ev.clientX - x0) < 3) return;
      moved = true;
      let patch;
      if (mode === "move") {
        let ns = Math.max(0, c.start + dt);
        if (snapOn) {
          const a = snap(ns, pts, tol), b = snap(ns + c.duration, pts, tol) - c.duration;
          ns = Math.abs(a - ns) <= Math.abs(b - ns) ? a : b;
          ns = Math.max(0, ns);
        }
        patch = { start: round3(ns) };
        const row = document.elementFromPoint(ev.clientX, ev.clientY)?.closest?.("[data-track]");
        const tid = row?.dataset.track;
        if (tid && tid !== c.track) {
          const t2 = p.tracks.find((t) => t.id === tid);
          if (canAccept(t2, kind) && !t2.locked) patch.track = tid;
        }
      } else if (mode === "left") {
        const minStart = m && isFinite(maxDur) ? Math.max(0, c.start - (c.in || 0)) : 0;
        let ns = clamp(c.start + dt, minStart, clipEnd(c) - MIN_CLIP);
        if (snapOn) ns = clamp(snap(ns, pts, tol), minStart, clipEnd(c) - MIN_CLIP);
        const d = ns - c.start;
        patch = { start: round3(ns), duration: round3(c.duration - d), in: isFinite(maxDur) ? round3((c.in || 0) + d) : c.in || 0 };
      } else {
        let ne = clipEnd(c) + dt;
        if (snapOn) ne = snap(ne, pts, tol);
        patch = { duration: round3(clamp(ne - c.start, MIN_CLIP, maxDur - (c.in || 0))) };
      }
      live((cur) => ({ ...cur, clips: cur.clips.map((x) => (x.id === c.id ? { ...x, ...patch } : x)) }));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.classList.remove("dragging");
      if (moved) commit((cur) => cur, snapshot);
    };
    document.body.classList.add("dragging");
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  // ------------------------------------------------------------------ drop dari Media Bin
  const dragKind = (e) => {
    const ty = Array.from(e.dataTransfer.types || []);
    const k = ty.find((x) => x.startsWith("application/x-dvc-kind-"));
    return k ? k.replace("application/x-dvc-kind-", "") : null;
  };
  const onLaneDragOver = (e, tr) => {
    const k = dragKind(e);
    if (!k) return;
    if (canAccept(tr, k) && !tr.locked) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      setDropHint({ track: tr.id, t: tFromClient(e.clientX) });
    } else setDropHint({ track: tr.id, bad: true, t: tFromClient(e.clientX) });
  };
  const onLaneDrop = (e, tr) => {
    e.preventDefault();
    setDropHint(null);
    const k = dragKind(e);
    if (!k) return;
    if (!canAccept(tr, k)) { notify?.(`Track ${tr.id} hanya menerima ${ACCEPT[tr.kind].join("/")}.`); return; }
    let t = tFromClient(e.clientX);
    if (snapOn) t = snap(t, snapPoints(p, null, time), 10 / zoom);
    if (k === "text") onDropText(tr.id, t);
    else onDropMedia(e.dataTransfer.getData("application/x-dvc-media"), tr.id, t);
  };

  // ------------------------------------------------------------------ kontrol track
  const setTrack = (id, patch) => commit((cur) => ({ ...cur, tracks: cur.tracks.map((t) => (t.id === id ? { ...t, ...patch } : t)) }));
  const moveLayer = (id, dir) => commit((cur) => {
    const vis = cur.tracks.filter((t) => t.kind !== "audio").map((t) => t.id);
    const i = vis.indexOf(id), j = i + dir;
    if (j < 0 || j >= vis.length) return cur;
    [vis[i], vis[j]] = [vis[j], vis[i]];
    const byId = Object.fromEntries(cur.tracks.map((t) => [t.id, t]));
    return { ...cur, tracks: [...vis.map((x) => byId[x]), ...cur.tracks.filter((t) => t.kind === "audio")] };
  });
  const visualIds = p.tracks.filter((t) => t.kind !== "audio").map((t) => t.id);

  const fitZoom = () => setZoom(clamp((vw - HEAD - 60) / Math.max(10, end), ZOOM_MIN, ZOOM_MAX));

  return (
    <div className="tl">
      <div className="tl-top">
        <div className="tl-tools">
          <button className="ib" title="Perkecil (Ctrl + scroll)" onClick={() => setZoom(clamp(zoom / 1.4, ZOOM_MIN, ZOOM_MAX))}><Icon n="zoomout" /></button>
          <input type="range" min={Math.log(ZOOM_MIN)} max={Math.log(ZOOM_MAX)} step="0.01" value={Math.log(zoom)}
            onChange={(e) => setZoom(Math.exp(Number(e.target.value)))} title="Zoom timeline" />
          <button className="ib" title="Perbesar (Ctrl + scroll)" onClick={() => setZoom(clamp(zoom * 1.4, ZOOM_MIN, ZOOM_MAX))}><Icon n="zoomin" /></button>
          <button className="ib" title="Muat seluruh timeline" onClick={fitZoom}><Icon n="fit" /></button>
          <button className={`ib ${snapOn ? "on" : ""}`} title="Snapping ke tepi klip & playhead" onClick={() => setSnapOn(!snapOn)}><Icon n="magnet" /></button>
        </div>
        <div className="tl-info">
          <span>Durasi proyek <b className="mono">{fmtTime(dur)}</b></span>
          {p.settings?.length ? <span className="tag">panjang manual</span> : <span className="muted">panjang otomatis</span>}
          <span className="muted">{p.clips.length} klip</span>
        </div>
      </div>
      <div className="tl-scroll" ref={scrollRef}>
        <div className="tl-inner" style={{ width: HEAD + laneW }}>
          <div className="tl-row tl-ruler-row" style={{ height: RULER_H }}>
            <div className="tl-head tl-head-ruler mono">{fmtTime(time)}</div>
            <div className="tl-ruler" style={{ width: laneW }} onPointerDown={onRulerDown}>
              {ticks.out.map(({ t, isMajor }) => (
                <div key={t} className={`tk ${isMajor ? "tk-major" : ""}`} style={{ left: t * zoom }}>
                  {isMajor && <span>{fmtTime(t, ticks.major < 1)}</span>}
                </div>))}
            </div>
          </div>
          {p.tracks.map((tr) => {
            const h = ROW_H[tr.kind];
            const clips = p.clips.filter((c) => c.track === tr.id);
            const vi = visualIds.indexOf(tr.id);
            return (
              <div key={tr.id} className={`tl-row kind-${tr.kind} ${tr.hidden ? "is-hidden" : ""} ${tr.muted ? "is-muted" : ""}`} style={{ height: h }} data-track={tr.id}>
                <div className="tl-head">
                  <div className="th-top">
                  <div className="th-name"><b>{tr.id}</b><span>{tr.name.split("·")[1]?.trim()}</span></div>
                  <div className="th-btns">
                    {tr.kind !== "audio" && <button className={`ib sm ${tr.hidden ? "off" : ""}`} title={tr.hidden ? "Tampilkan track" : "Sembunyikan track"} onClick={() => setTrack(tr.id, { hidden: !tr.hidden })}><Icon n={tr.hidden ? "eyeoff" : "eye"} size={14} /></button>}
                    {(tr.kind === "audio" || tr.kind === "video") && <button className={`ib sm ${tr.muted ? "off" : ""}`} title={tr.muted ? "Bunyikan" : "Bisukan"} onClick={() => setTrack(tr.id, { muted: !tr.muted })}><Icon n={tr.muted ? "mute" : "vol"} size={14} /></button>}
                    <button className={`ib sm ${tr.locked ? "off" : ""}`} title={tr.locked ? "Buka kunci" : "Kunci track"} onClick={() => setTrack(tr.id, { locked: !tr.locked })}><Icon n={tr.locked ? "lock" : "unlock"} size={14} /></button>
                    {tr.kind !== "audio" && <>
                      <button className="ib sm" disabled={vi <= 0} title="Naikkan layer (tampil di atas)" onClick={() => moveLayer(tr.id, -1)}><Icon n="up" size={12} fill /></button>
                      <button className="ib sm" disabled={vi >= visualIds.length - 1} title="Turunkan layer" onClick={() => moveLayer(tr.id, 1)}><Icon n="down" size={12} fill /></button>
                    </>}
                  </div>
                  </div>
                  {(tr.kind === "audio" || tr.kind === "video") && (
                    <label className="th-vol" title={`Volume track ${Math.round((tr.volume ?? 1) * 100)}%`}>
                      <input type="range" min="0" max="2" step="0.05" value={tr.volume ?? 1}
                        onChange={(e) => live((cur) => ({ ...cur, tracks: cur.tracks.map((t) => (t.id === tr.id ? { ...t, volume: Number(e.target.value) } : t)) }))}
                        onPointerDown={() => { trackVolSnap.current = p; }}
                        onPointerUp={() => trackVolSnap.current && commit((cur) => cur, trackVolSnap.current)} />
                      <span className="mono">{Math.round((tr.volume ?? 1) * 100)}%</span>
                    </label>)}
                </div>
                <div className="tl-lane" style={{ width: laneW }} onDragOver={(e) => onLaneDragOver(e, tr)} onDragLeave={() => setDropHint(null)}
                  onDrop={(e) => onLaneDrop(e, tr)} onPointerDown={(e) => { if (e.target === e.currentTarget) { onSelect(null); onSeek(tFromClient(e.clientX)); } }}>
                  {clips.map((c) => <Clip key={c.id} c={c} m={mm[c.media_id]} zoom={zoom} tr={tr} selected={c.id === selectedId} startDrag={startDrag} />)}
                  {dropHint?.track === tr.id && <div className={`drop-hint ${dropHint.bad ? "bad" : ""}`} style={{ left: dropHint.t * zoom }} />}
                </div>
              </div>
            );
          })}
          {p.settings?.length ? <div className="tl-endmark" style={{ left: HEAD + p.settings.length * zoom }} title="Akhir timeline (panjang manual)" /> : null}
          <div className="tl-playhead" style={{ left: HEAD + time * zoom }}><i /></div>
        </div>
      </div>
    </div>
  );
}

const trackVolSnap = { current: null };

function Clip({ c, m, zoom, tr, selected, startDrag }) {
  const w = Math.max(4, c.duration * zoom);
  const kind = c.media_id ? m?.kind : "text";
  const style = { left: c.start * zoom, width: w };
  const bg = {};
  if (m?.wave && (tr.kind === "audio" || kind === "audio")) {
    bg.backgroundImage = `url(${api.waveUrl(m.id)})`;
    bg.backgroundSize = `${(m.duration || c.duration) * zoom}px 100%`;
    bg.backgroundPosition = `${-(c.in || 0) * zoom}px 0`;
  } else if (m?.thumb && (kind === "video" || kind === "image")) {
    bg.backgroundImage = `url(${api.thumbUrl(m.id)})`;
  }
  const hasAudioEnv = tr.kind === "audio" || (tr.kind === "video" && m?.has_audio);
  const showAudioEnv = hasAudioEnv && (c.fade_in > 0 || c.fade_out > 0 || (c.volume ?? 1) !== 1);
  const label = kind === "text" ? (c.text || "Teks").split("\n")[0] : m ? `${m.missing ? "⚠ " : ""}${m.name}` : "Media hilang";
  const vfi = Math.max(Number(c.video_fade_in || 0), c.transition === "crossfade" ? Number(c.transition_duration || 0) : 0);
  const vfo = Number(c.video_fade_out || 0);
  return (
    <div className={`clip clip-${kind || "missing"} ${selected ? "sel" : ""} ${m?.missing ? "missing" : ""}`} style={style}
      onPointerDown={(e) => startDrag(e, c, "move")} title={`${label}\n${fmtTime(c.start)} → ${fmtTime(clipEnd(c))} (${c.duration.toFixed(2)} dtk)`}>
      <div className={`clip-bg ${bg.backgroundImage && kind !== "audio" && tr.kind !== "audio" ? "thumbs" : ""}`} style={bg} />
      <div className="clip-label">
        {c.transition === "crossfade" && <span className="xf" title="Crossfade">⨯ {Number(c.transition_duration).toFixed(1)}s</span>}
        <span>{label}</span>
      </div>
      {tr.kind !== "audio" && (vfi > 0 || vfo > 0) && (
        <svg className="clip-vfade" viewBox={`0 0 ${w} 10`} preserveAspectRatio="none">
          {vfi > 0 && <polygon points={`0,10 0,0 ${Math.min(w, vfi * zoom)},0`} />}
          {vfo > 0 && <polygon points={`${w},10 ${w},0 ${Math.max(0, w - vfo * zoom)},0`} />}
        </svg>)}
      {showAudioEnv && <Envelope c={c} w={w} />}
      <div className="clip-h left" onPointerDown={(e) => startDrag(e, c, "left")} />
      <div className="clip-h right" onPointerDown={(e) => startDrag(e, c, "right")} />
    </div>
  );
}

/** Garis amplop volume (fade in/out) di atas klip audio. */
function Envelope({ c, w }) {
  const H = 100, n = 48;
  const vmax = 2;
  const pts = [];
  const xs = new Set([0, c.duration]);
  if (c.fade_in > 0) xs.add(Math.min(c.duration, c.fade_in));
  if (c.fade_out > 0) xs.add(Math.max(0, c.duration - c.fade_out));
  for (let i = 0; i <= n; i++) xs.add((c.duration * i) / n);
  [...xs].sort((a, b) => a - b).forEach((x) => {
    const v = (c.volume ?? 1) * envelope(c, Math.min(x, c.duration - 1e-6));
    pts.push(`${(x / c.duration) * w},${H - (v / vmax) * H * 0.9}`);
  });
  return (
    <svg className="clip-env" viewBox={`0 0 ${w} ${H}`} preserveAspectRatio="none">
      <polygon points={`0,${H} ${pts.join(" ")} ${w},${H}`} />
      <polyline points={pts.join(" ")} />
    </svg>
  );
}

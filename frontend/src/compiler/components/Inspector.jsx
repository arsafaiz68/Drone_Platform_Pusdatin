// Panel properti: pengaturan klip terpilih (posisi, durasi, audio, fade, teks, efek) atau proyek.
import { useRef } from "react";
import { ASPECT_OPTIONS, applyCrossfade, clamp, clipEnd, fmtTime, mediaMaxDuration, removeCrossfade, round3 } from "../lib/model.js";
import { FONTS } from "../lib/textDraw.js";
import Icon from "./Icon.jsx";

export default function Inspector({ project, mm, selected, live, commit, onSplit, onDelete, onDuplicate, notify, time }) {
  if (!selected) return <ProjectPanel project={project} commit={commit} />;
  const c = selected;
  const tr = project.tracks.find((t) => t.id === c.track);
  const m = mm[c.media_id];
  const kind = c.media_id ? m?.kind : "text";
  const visual = tr.kind !== "audio";
  const hasAudio = tr.kind === "audio" || (tr.kind === "video" && m?.has_audio);
  const maxDur = mediaMaxDuration(m);
  const set = (patch) => commit((p) => ({ ...p, clips: p.clips.map((x) => (x.id === c.id ? { ...x, ...patch } : x)) }));
  const setLive = (patch) => live((p) => ({ ...p, clips: p.clips.map((x) => (x.id === c.id ? { ...x, ...patch } : x)) }));
  const R = (props) => <Range {...props} project={project} live={setLive} commit={commit} />;

  return (
    <div className="insp">
      <div className="panel-head"><span>Properti klip</span><span className="tag">{tr.id}</span></div>
      <div className="insp-body">
        <div className="insp-title">{kind === "text" ? "Teks" : m?.name || "Media hilang"}</div>
        <div className="row-gap wrap">
          <button className="btn sm" onClick={onSplit} title="Bagi klip di playhead (S)"><Icon n="split" size={14} /> Split</button>
          <button className="btn sm" onClick={onDuplicate} title="Duplikat klip (Ctrl+D)"><Icon n="copy" size={14} /> Duplikat</button>
          <button className="btn sm danger" onClick={onDelete} title="Hapus klip (Delete)"><Icon n="trash" size={14} /> Hapus</button>
        </div>

        <Section title="Waktu">
          <Num label="Mulai (dtk)" value={c.start} min={0} step={0.1} onChange={(v) => set({ start: round3(Math.max(0, v)) })} />
          <Num label="Durasi (dtk)" value={c.duration} min={0.1} step={0.1} max={isFinite(maxDur) ? maxDur - (c.in || 0) : undefined}
            onChange={(v) => set({ duration: round3(clamp(v, 0.1, maxDur - (c.in || 0))) })} />
          {isFinite(maxDur) && <Num label="Titik masuk sumber (dtk)" value={c.in || 0} min={0} step={0.1} max={maxDur - 0.1}
            onChange={(v) => { const nin = clamp(v, 0, maxDur - 0.1); set({ in: round3(nin), duration: round3(Math.min(c.duration, maxDur - nin)) }); }} />}
          <div className="kv-line"><span>Selesai</span><b className="mono">{fmtTime(clipEnd(c))}</b></div>
          {isFinite(maxDur) && <div className="kv-line"><span>Durasi sumber</span><b className="mono">{fmtTime(maxDur)}</b></div>}
          <div className="row-gap"><button className="btn xs" onClick={() => set({ start: round3(time) })}>Pindah ke playhead</button>
            {isFinite(maxDur) && <button className="btn xs" onClick={() => set({ duration: round3(maxDur - (c.in || 0)) })}>Durasi penuh</button>}</div>
        </Section>

        {kind === "text" && <TextSection c={c} set={set} R={R} />}

        {visual && (
          <Section title={kind === "text" ? "Tampilan teks" : "Visual & posisi"}>
            {R({ label: "Opacity", value: c.opacity ?? 1, min: 0, max: 1, step: 0.01, fmt: (v) => `${Math.round(v * 100)}%`, k: "opacity" })}
            {kind !== "text" && <>
              {R({ label: "Skala", value: c.scale ?? 1, min: 0.05, max: 3, step: 0.01, fmt: (v) => `${Math.round(v * 100)}%`, k: "scale" })}
              {R({ label: "Posisi X", value: c.x ?? 0.5, min: -0.5, max: 1.5, step: 0.001, fmt: (v) => `${Math.round(v * 100)}%`, k: "x" })}
              {R({ label: "Posisi Y", value: c.y ?? 0.5, min: -0.5, max: 1.5, step: 0.001, fmt: (v) => `${Math.round(v * 100)}%`, k: "y" })}
              <div className="presets">
                {[["Penuh", 1, 0.5, 0.5], ["Tengah", 0.5, 0.5, 0.5], ["Kiri atas", 0.3, 0.17, 0.18], ["Kanan atas", 0.3, 0.83, 0.18],
                  ["Kiri bawah", 0.3, 0.17, 0.82], ["Kanan bawah", 0.3, 0.83, 0.82]].map(([l, s, x, y]) => (
                  <button key={l} className="btn xs" onClick={() => set({ scale: s, x, y })}>{l}</button>))}
              </div>
              <p className="muted xs">Tip: seret objek langsung di Preview Monitor untuk memindahkan posisinya.</p>
            </>}
            {R({ label: "Fade in", value: c.video_fade_in || 0, min: 0, max: Math.min(10, c.duration), step: 0.1, fmt: (v) => `${v.toFixed(1)} dtk`, k: "video_fade_in" })}
            {R({ label: "Fade out", value: c.video_fade_out || 0, min: 0, max: Math.min(10, c.duration), step: 0.1, fmt: (v) => `${v.toFixed(1)} dtk`, k: "video_fade_out" })}
            {tr.kind === "video" && (
              <div className="field">
                <label>Transisi masuk</label>
                <div className="row-gap">
                  <select value={c.transition === "crossfade" ? "crossfade" : "none"} onChange={(e) => {
                    if (e.target.value === "crossfade") {
                      const r = applyCrossfade(project, c.id, Number(c.transition_duration || 1));
                      if (r.error) notify(r.error); else commit(r.project);
                    } else commit(removeCrossfade(project, c.id));
                  }}>
                    <option value="none">Tidak ada (potong langsung)</option>
                    <option value="crossfade">Crossfade dengan klip sebelumnya</option>
                  </select>
                  {c.transition === "crossfade" && <Num value={c.transition_duration || 1} min={0.1} max={5} step={0.1} small
                    onChange={(v) => { const r = applyCrossfade(removeCrossfade(project, c.id), c.id, clamp(v, 0.1, 5)); if (r.error) notify(r.error); else commit(r.project); }} />}
                </div>
                <p className="muted xs">Crossfade memperpanjang klip sebelumnya di bawah klip ini, sehingga posisi klip tidak bergeser.</p>
              </div>)}
          </Section>)}

        {hasAudio && (
          <Section title="Audio">
            {R({ label: "Volume", value: c.volume ?? 1, min: 0, max: 2, step: 0.01, fmt: (v) => `${Math.round(v * 100)}%`, k: "volume" })}
            {R({ label: "Fade in audio", value: c.fade_in || 0, min: 0, max: Math.min(20, c.duration), step: 0.1, fmt: (v) => `${v.toFixed(1)} dtk`, k: "fade_in" })}
            {R({ label: "Volume awal fade in", value: c.vol_start || 0, min: 0, max: 1, step: 0.01, fmt: (v) => `${Math.round(v * 100)}%`, k: "vol_start", disabled: !(c.fade_in > 0) })}
            {R({ label: "Fade out audio", value: c.fade_out || 0, min: 0, max: Math.min(20, c.duration), step: 0.1, fmt: (v) => `${v.toFixed(1)} dtk`, k: "fade_out" })}
            {R({ label: "Volume akhir fade out", value: c.vol_end || 0, min: 0, max: 1, step: 0.01, fmt: (v) => `${Math.round(v * 100)}%`, k: "vol_end", disabled: !(c.fade_out > 0) })}
            <div className="presets">
              <button className="btn xs" onClick={() => set({ fade_in: Math.min(2, c.duration / 2), fade_out: Math.min(3, c.duration / 2), vol_start: 0, vol_end: 0 })}>Fade musik standar</button>
              <button className="btn xs" onClick={() => set({ fade_in: 0, fade_out: 0 })}>Tanpa fade</button>
              <button className="btn xs" onClick={() => set({ volume: 0.3 })}>Latar 30%</button>
            </div>
            {tr.muted && <p className="xs warn">Track {tr.id} sedang dibisukan.</p>}
          </Section>)}
      </div>
    </div>
  );
}

function TextSection({ c, set, R }) {
  return (
    <Section title="Teks">
      <textarea rows={3} value={c.text || ""} onChange={(e) => set({ text: e.target.value })} placeholder="Isi teks…" />
      <div className="grid2">
        <div className="field"><label>Font</label>
          <select value={c.font} onChange={(e) => set({ font: e.target.value })}>{FONTS.map((f) => <option key={f} style={{ fontFamily: f }}>{f}</option>)}</select></div>
        <Num label="Ukuran (pt @1080p)" value={c.size || 72} min={8} max={400} step={1} onChange={(v) => set({ size: clamp(v, 8, 400) })} />
      </div>
      <div className="row-gap wrap">
        <label className="color"><input type="color" value={c.color || "#ffffff"} onChange={(e) => set({ color: e.target.value })} /> Warna</label>
        <button className={`btn xs ${c.bold ? "on" : ""}`} onClick={() => set({ bold: !c.bold })}><b>B</b></button>
        <button className={`btn xs ${c.italic ? "on" : ""}`} onClick={() => set({ italic: !c.italic })}><i>I</i></button>
      </div>
      <div className="field"><label>Posisi</label>
        <div className="seg">{[["top", "Atas"], ["middle", "Tengah"], ["bottom", "Bawah"]].map(([v, l]) => (
          <button key={v} className={c.vpos === v ? "on" : ""} onClick={() => set({ vpos: v, offset_y: 0 })}>{l}</button>))}</div></div>
      <div className="field"><label>Perataan</label>
        <div className="seg">{[["left", "Kiri"], ["center", "Tengah"], ["right", "Kanan"]].map(([v, l]) => (
          <button key={v} className={c.align === v ? "on" : ""} onClick={() => set({ align: v, offset_x: 0 })}>{l}</button>))}</div></div>
      <div className="row-gap wrap">
        <label className="check"><input type="checkbox" checked={!!c.bg} onChange={(e) => set({ bg: e.target.checked })} /> Latar teks</label>
        {c.bg && <label className="color"><input type="color" value={c.bg_color || "#000000"} onChange={(e) => set({ bg_color: e.target.value })} /></label>}
      </div>
      {c.bg && R({ label: "Opacity latar", value: c.bg_opacity ?? 0.55, min: 0, max: 1, step: 0.01, fmt: (v) => `${Math.round(v * 100)}%`, k: "bg_opacity" })}
      <div className="row-gap wrap">
        <label className="check"><input type="checkbox" checked={!!c.outline} onChange={(e) => set({ outline: e.target.checked })} /> Outline</label>
        {c.outline && <label className="color"><input type="color" value={c.outline_color || "#000000"} onChange={(e) => set({ outline_color: e.target.value })} /></label>}
        <label className="check"><input type="checkbox" checked={!!c.shadow} onChange={(e) => set({ shadow: e.target.checked })} /> Bayangan</label>
      </div>
      {(c.offset_x || c.offset_y) ? <button className="btn xs" onClick={() => set({ offset_x: 0, offset_y: 0 })}>Reset geser manual</button> : null}
    </Section>
  );
}

function ProjectPanel({ project, commit }) {
  const s = project.settings;
  const setS = (patch) => commit((p) => ({ ...p, settings: { ...p.settings, ...patch } }));
  return (
    <div className="insp">
      <div className="panel-head"><span>Pengaturan proyek</span></div>
      <div className="insp-body">
        <Section title="Komposisi">
          <div className="field"><label>Rasio aspek</label>
            <select value={s.aspect} onChange={(e) => setS({ aspect: e.target.value })}>{ASPECT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></div>
          <div className="field"><label>Warna latar</label><label className="color"><input type="color" value={s.background || "#000000"} onChange={(e) => setS({ background: e.target.value })} /> {s.background}</label></div>
          <div className="field"><label>Frame rate preview/proyek</label>
            <select value={s.fps} onChange={(e) => setS({ fps: Number(e.target.value) })}>{[24, 25, 30, 50, 60].map((f) => <option key={f} value={f}>{f} fps</option>)}</select></div>
          <div className="field"><label>Panjang timeline</label>
            <div className="row-gap">
              <select value={s.length ? "manual" : "auto"} onChange={(e) => setS({ length: e.target.value === "manual" ? Math.max(1, Math.ceil(project.clips.reduce((m, c) => Math.max(m, c.start + c.duration), 10))) : null })}>
                <option value="auto">Otomatis (sampai klip terakhir)</option><option value="manual">Manual</option></select>
              {s.length ? <Num value={s.length} min={1} step={1} small onChange={(v) => setS({ length: Math.max(1, v) })} /> : null}
            </div>
            <p className="muted xs">Durasi video hasil export mengikuti panjang timeline.</p></div>
        </Section>
        <Section title="Panduan singkat">
          <ul className="tips">
            <li>Seret media dari Media Bin ke track: <b>V1</b> video utama, <b>V2</b> overlay, <b>I1</b> gambar, <b>T1</b> teks, <b>A1/A2</b> audio & musik.</li>
            <li>Seret tepi klip untuk memotong, seret badan klip untuk menggeser atau pindah track.</li>
            <li><kbd>Spasi</kbd> putar/jeda · <kbd>S</kbd> split · <kbd>Delete</kbd> hapus · <kbd>Ctrl+Z</kbd>/<kbd>Ctrl+Y</kbd> undo/redo · <kbd>Ctrl+S</kbd> simpan.</li>
            <li>Track paling atas di daftar tampil paling depan; ubah dengan panah ▲▼ di kepala track.</li>
          </ul>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return <div className="sec"><div className="sec-title">{title}</div><div className="sec-body">{children}</div></div>;
}

function Num({ label, value, onChange, min, max, step = 0.1, small }) {
  const el = (
    <input type="number" className={small ? "num-sm" : ""} value={Number.isFinite(value) ? Math.round(value * 1000) / 1000 : 0} min={min} max={max} step={step}
      onChange={(e) => { const v = Number(e.target.value); if (Number.isFinite(v) && e.target.value !== "") onChange(v); }} />
  );
  return label ? <div className="field"><label>{label}</label>{el}</div> : el;
}

/** Slider: perubahan langsung terlihat (live), satu langkah undo saat dilepas. */
function Range({ label, value, min, max, step, fmt, k, project, live, commit, disabled }) {
  const snap = useRef(null);
  return (
    <div className={`field range ${disabled ? "disabled" : ""}`}>
      <label>{label}<span className="mono">{fmt ? fmt(value) : value}</span></label>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        onPointerDown={() => { snap.current = project; }}
        onChange={(e) => live({ [k]: Number(e.target.value) })}
        onPointerUp={() => { if (snap.current) commit((p) => p, snap.current); snap.current = null; }}
        onKeyDown={() => { if (!snap.current) snap.current = project; }}
        onKeyUp={() => { if (snap.current) commit((p) => p, snap.current); snap.current = null; }} />
    </div>
  );
}

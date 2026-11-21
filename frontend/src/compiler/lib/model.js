// Model data Drone Video Compiler — fungsi murni yang dipakai preview, timeline, dan inspector.
// Aturan komposisi di sini SAMA dengan backend (app/compiler/render.py) agar preview = hasil render.

export const ASPECTS = { "16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1, "4:3": 4 / 3 };
export const ASPECT_OPTIONS = [
  { value: "16:9", label: "16:9 Lanskap" }, { value: "9:16", label: "9:16 Vertikal" },
  { value: "1:1", label: "1:1 Persegi" }, { value: "4:3", label: "4:3 Klasik" }, { value: "original", label: "Original (ikuti sumber)" },
];
export const ACCEPT = { video: ["video", "image"], image: ["image"], text: ["text"], audio: ["audio", "video"] };
export const MIN_CLIP = 0.1;
export const IMAGE_DEFAULT_DUR = 5;
export const TEXT_DEFAULT_DUR = 4;

export const uid = (p = "c") => p + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const round3 = (v) => Math.round(v * 1000) / 1000;
export const clipEnd = (c) => c.start + c.duration;

export function projectDuration(p) {
  const end = p.clips.reduce((m, c) => Math.max(m, clipEnd(c)), 0);
  return p.settings?.length ? Number(p.settings.length) : end;
}

export function contentEnd(p) {
  return p.clips.reduce((m, c) => Math.max(m, clipEnd(c)), 0);
}

export function trackOf(p, id) { return p.tracks.find((t) => t.id === id); }
export function mediaMap(p) { const m = {}; for (const x of p.media) m[x.id] = x; return m; }

export function referenceMedia(p, mm) {
  const v1 = p.clips.filter((c) => c.track === "V1" && c.media_id).sort((a, b) => a.start - b.start);
  for (const c of [...v1, ...p.clips.filter((c) => c.media_id)]) {
    const m = mm[c.media_id];
    if (m && (m.kind === "video" || m.kind === "image") && m.width) return m;
  }
  return null;
}

export function aspectRatio(p, mm) {
  const a = p.settings?.aspect || "16:9";
  if (a === "original") {
    const r = referenceMedia(p, mm);
    return r ? r.width / r.height : 16 / 9;
  }
  return ASPECTS[a] || 16 / 9;
}

const even = (x) => Math.max(2, Math.round(x / 2) * 2);

/** Ukuran output render (sama dengan render.canvas di backend). */
export function outputSize(p, mm, exp = p.export) {
  const ref = referenceMedia(p, mm);
  const aspect = p.settings?.aspect || "16:9";
  const ratio = aspectRatio(p, mm);
  let w, h;
  if (exp.resolution === "source") {
    if (aspect === "original" && ref) { w = ref.width; h = ref.height; }
    else { const s = ref ? Math.min(ref.width, ref.height) : 1080; [w, h] = ratio >= 1 ? [s * ratio, s] : [s, s / ratio]; }
  } else {
    const s = Number(exp.resolution) || 1080;
    [w, h] = ratio >= 1 ? [s * ratio, s] : [s, s / ratio];
  }
  let fps = exp.fps;
  if (fps === "source" || !fps) fps = Math.min((ref && ref.kind === "video" && ref.fps) || p.settings?.fps || 30, 60);
  return { width: even(w), height: even(h), fps: Number(fps) };
}

/** Kotak tampilan klip visual pada kanvas W×H: contain × scale, titik tengah (x·W, y·H). */
export function clipBox(c, m, W, H) {
  if (!m || !m.width) return { x: 0, y: 0, w: W, h: H };
  const r = Math.min(W / m.width, H / m.height) * Math.max(0.01, c.scale ?? 1);
  const w = m.width * r, h = m.height * r;
  return { x: (c.x ?? 0.5) * W - w / 2, y: (c.y ?? 0.5) * H - h / 2, w, h };
}

/** Alpha klip visual pada waktu lokal (opacity × fade in/out). */
export function visualAlpha(c, local) {
  let a = c.opacity ?? 1;
  let fin = Number(c.video_fade_in || 0);
  if (c.transition === "crossfade") fin = Math.max(fin, Number(c.transition_duration || 1));
  const fout = Number(c.video_fade_out || 0);
  if (fin > 0 && local < fin) a *= clamp(local / fin, 0, 1);
  if (fout > 0 && local > c.duration - fout) a *= clamp((c.duration - local) / fout, 0, 1);
  return clamp(a, 0, 1);
}

/** Amplop volume audio pada waktu lokal (identik dengan ekspresi volume FFmpeg di backend). */
export function envelope(c, local) {
  const fi = Number(c.fade_in || 0), fo = Number(c.fade_out || 0);
  const vs = Number(c.vol_start || 0), ve = Number(c.vol_end || 0);
  if (fi > 0 && local < fi) return vs + (1 - vs) * clamp(local / fi, 0, 1);
  if (fo > 0 && local > c.duration - fo) return ve + (1 - ve) * clamp((c.duration - local) / fo, 0, 1);
  return 1;
}

export function mediaMaxDuration(m) {
  return m && (m.kind === "video" || m.kind === "audio") && m.duration ? m.duration : Infinity;
}

export const TEXT_DEFAULTS = {
  text: "Judul video", font: "Segoe UI", size: 72, color: "#ffffff", bold: true, italic: false,
  vpos: "bottom", align: "center", bg: true, bg_color: "#000000", bg_opacity: 0.55,
  outline: false, outline_color: "#000000", shadow: true, offset_x: 0, offset_y: 0,
  opacity: 1, video_fade_in: 0.3, video_fade_out: 0.3,
};

export function newClip(kind, trackId, start, m) {
  const base = { id: uid("c"), track: trackId, start: round3(Math.max(0, start)), in: 0 };
  if (kind === "text") return { ...base, duration: TEXT_DEFAULT_DUR, ...TEXT_DEFAULTS };
  if (!m) return null;
  const dur = m.kind === "image" ? IMAGE_DEFAULT_DUR : m.duration || 5;
  const c = { ...base, media_id: m.id, duration: round3(dur), opacity: 1, volume: 1, fade_in: 0, fade_out: 0,
    vol_start: 0, vol_end: 0, video_fade_in: 0, video_fade_out: 0, transition: "none", transition_duration: 1,
    scale: 1, x: 0.5, y: 0.5 };
  if (trackId === "V2") Object.assign(c, { scale: 0.4, x: 0.76, y: 0.74 });
  if (trackId === "I1") Object.assign(c, { scale: 0.25, x: 0.84, y: 0.18, video_fade_in: 0.3, video_fade_out: 0.3 });
  return c;
}

/** Track default untuk jenis media saat ditambahkan lewat tombol "+". */
export function defaultTrackFor(m) {
  if (m.kind === "audio") return "A2";
  if (m.kind === "image") return "I1";
  return "V1";
}

export function canAccept(track, kind) { return !!track && (ACCEPT[track.kind] || []).includes(kind); }

/** Akhir klip terakhir pada track (untuk menambah klip berurutan). */
export function trackEnd(p, trackId) {
  return p.clips.filter((c) => c.track === trackId).reduce((m, c) => Math.max(m, clipEnd(c)), 0);
}

export function splitClip(c, t) {
  if (t <= c.start + MIN_CLIP / 2 || t >= clipEnd(c) - MIN_CLIP / 2) return null;
  const leftDur = round3(t - c.start);
  const left = { ...c, duration: leftDur, fade_out: 0, video_fade_out: 0, vol_end: 0 };
  const right = { ...c, id: uid("c"), start: round3(t), in: round3((c.in || 0) + (c.media_id ? leftDur : 0)),
    duration: round3(c.duration - leftDur), fade_in: 0, video_fade_in: 0, vol_start: 0, transition: "none" };
  return [left, right];
}

export function fmtTime(s, withMs = true) {
  if (s == null || !isFinite(s)) return "–";
  s = Math.max(0, s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const ss = withMs ? sec.toFixed(2).padStart(5, "0") : String(Math.floor(sec)).padStart(2, "0");
  return (h ? `${h}:${String(m).padStart(2, "0")}` : String(m).padStart(2, "0")) + ":" + ss;
}

export function fmtBytes(b) {
  if (b == null) return "–";
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`;
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(b / 1e3))} KB`;
}

export function snapPoints(p, excludeId, playhead) {
  const pts = [0, playhead];
  for (const c of p.clips) if (c.id !== excludeId) pts.push(c.start, clipEnd(c));
  return pts;
}

export function snap(v, pts, tol) {
  let best = v, bd = tol;
  for (const s of pts) { const d = Math.abs(s - v); if (d < bd) { bd = d; best = s; } }
  return best;
}

/** Terapkan crossfade pada klip: klip sebelumnya diperpanjang di bawah fade-in klip ini. */
export function applyCrossfade(p, clipId, dur) {
  const c = p.clips.find((x) => x.id === clipId);
  const mm = mediaMap(p);
  const prev = p.clips.filter((x) => x.track === c.track && x.id !== c.id && x.start < c.start)
    .sort((a, b) => clipEnd(b) - clipEnd(a))[0];
  if (!prev) return { error: "Tidak ada klip sebelumnya di track yang sama." };
  if (clipEnd(prev) < c.start - 0.05) return { error: "Klip sebelumnya tidak bersambung dengan klip ini (ada jeda)." };
  const need = c.start + dur - clipEnd(prev);
  let prevNew = prev;
  if (need > 0) {
    const room = mediaMaxDuration(mm[prev.media_id]) - ((prev.in || 0) + prev.duration);
    if (room < need - 0.01) return { error: `Sumber klip sebelumnya hanya tersisa ${Math.max(0, room).toFixed(2)} dtk — pendekkan klip sebelumnya atau pilih durasi crossfade lebih pendek.` };
    prevNew = { ...prev, duration: round3(prev.duration + need) };
  }
  const clips = p.clips.map((x) => (x.id === prev.id ? prevNew : x.id === c.id
    ? { ...x, transition: "crossfade", transition_duration: dur, xf_prev: prev.id, xf_ext: round3(Math.max(0, need)) } : x));
  return { project: { ...p, clips } };
}

export function removeCrossfade(p, clipId) {
  const c = p.clips.find((x) => x.id === clipId);
  const clips = p.clips.map((x) => {
    if (x.id === c.id) return { ...x, transition: "none", xf_prev: undefined, xf_ext: 0 };
    if (x.id === c.xf_prev && c.xf_ext > 0) return { ...x, duration: round3(Math.max(MIN_CLIP, x.duration - c.xf_ext)) };
    return x;
  });
  return { ...p, clips };
}

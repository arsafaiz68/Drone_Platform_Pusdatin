// Media Bin: impor (tombol / drag & drop / path folder lokal), daftar media dengan thumbnail,
// durasi, ukuran, tipe; seret ke timeline atau tambahkan cepat di posisi playhead.
import { useRef, useState } from "react";
import { api, svgToPng } from "../lib/api.js";
import { fmtBytes, fmtTime } from "../lib/model.js";
import Icon from "./Icon.jsx";

const ACCEPT = ".mp4,.mov,.mkv,.avi,.m4v,.webm,.mts,.m2ts,.ts,.wmv,.flv,.3gp,.mpg,.mpeg,.mp3,.wav,.aac,.m4a,.ogg,.oga,.opus,.flac,.wma,.aiff,.aif,.jpg,.jpeg,.png,.webp,.bmp,.gif,.tif,.tiff,.svg";
const KIND_LABEL = { video: "Video", audio: "Audio", image: "Gambar" };
const FILTERS = [["all", "Semua"], ["video", "Video"], ["audio", "Audio"], ["image", "Gambar"]];

export default function MediaBin({ media, onImported, onRemove, onAdd, notify, importRef, onRelink }) {
  const inputRef = useRef(null);
  if (importRef) importRef.current = () => inputRef.current?.click();
  const [queue, setQueue] = useState([]); // {key, name, progress, error}
  const [over, setOver] = useState(false);
  const [filter, setFilter] = useState("all");
  const [pathOpen, setPathOpen] = useState(false);
  const [pathText, setPathText] = useState("");
  const [busy, setBusy] = useState(false);

  const uploadFiles = async (files) => {
    const list = Array.from(files || []);
    if (!list.length) return;
    const items = list.map((f, i) => ({ key: `${Date.now()}_${i}_${f.name}`, name: f.name, progress: 0, file: f }));
    setQueue((q) => [...q, ...items]);
    const added = [];
    for (const it of items) {
      try {
        let f = it.file, name = it.file.name;
        if (/\.svg$/i.test(name)) { f = await svgToPng(it.file); name = f.name; }
        const m = await api.upload(f, name, (pr) => setQueue((q) => q.map((x) => (x.key === it.key ? { ...x, progress: pr } : x))));
        added.push(m);
        setQueue((q) => q.filter((x) => x.key !== it.key));
      } catch (e) {
        setQueue((q) => q.map((x) => (x.key === it.key ? { ...x, error: e.message } : x)));
      }
    }
    if (added.length) onImported(added);
  };

  const registerPaths = async () => {
    const paths = pathText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    if (!paths.length) return;
    setBusy(true);
    try {
      const r = await api.registerPaths(paths);
      if (r.added.length) onImported(r.added);
      if (r.errors.length) notify(`${r.errors.length} file dilewati: ${r.errors[0].error}`);
      else notify(`${r.added.length} media ditambahkan (dibaca langsung dari lokasi aslinya).`);
      if (r.added.length) { setPathOpen(false); setPathText(""); }
    } catch (e) { notify(e.message); } finally { setBusy(false); }
  };

  const shown = media.filter((m) => filter === "all" || m.kind === filter);
  return (
    <div className={`bin ${over ? "over" : ""}`}
      onDragOver={(e) => { if (Array.from(e.dataTransfer.types).includes("Files")) { e.preventDefault(); setOver(true); } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setOver(false); }}
      onDrop={(e) => { if (e.dataTransfer.files?.length) { e.preventDefault(); setOver(false); uploadFiles(e.dataTransfer.files); } }}>
      <div className="panel-head">
        <span>Media Bin</span>
        <div className="row-gap">
          <button className="btn sm" onClick={() => inputRef.current?.click()} title="Impor file dari komputer (bisa banyak sekaligus)"><Icon n="import" size={14} /> Import</button>
          <button className="btn sm ghost" onClick={() => setPathOpen((v) => !v)} title="Tambahkan file/folder lewat path tanpa menyalin"><Icon n="folder" size={14} /></button>
        </div>
        <input ref={inputRef} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { uploadFiles(e.target.files); e.target.value = ""; }} />
      </div>
      {pathOpen && (
        <div className="bin-path">
          <textarea rows={3} placeholder={"Satu path per baris, mis.\nC:\\Users\\Saya\\Videos\\Drone\nD:\\Musik\\latar.mp3"} value={pathText} onChange={(e) => setPathText(e.target.value)} />
          <div className="row-gap"><button className="btn sm primary" disabled={busy} onClick={registerPaths}>{busy ? "Membaca…" : "Tambahkan"}</button>
            <span className="muted xs">File tidak disalin — dibaca langsung dari komputer Anda.</span></div>
        </div>)}
      <div className="bin-filters">
        {FILTERS.map(([k, l]) => <button key={k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}>{l}{k !== "all" ? ` ${media.filter((m) => m.kind === k).length}` : ""}</button>)}
      </div>
      {queue.length > 0 && (
        <div className="bin-queue">
          {queue.map((q) => (
            <div key={q.key} className="bq">
              <span className="bq-name">{q.name}</span>
              {q.error ? <span className="err xs">{q.error} <button className="link" onClick={() => setQueue((x) => x.filter((y) => y.key !== q.key))}>tutup</button></span>
                : <div className="bq-bar"><i style={{ width: `${Math.round(q.progress * 100)}%` }} /></div>}
            </div>))}
        </div>)}
      <div className="bin-list">
        <div className="bin-item bin-text" draggable onDragStart={(e) => { e.dataTransfer.setData("application/x-dvc-kind-text", "1"); e.dataTransfer.effectAllowed = "copy"; }}
          title="Seret ke track T1, atau klik + untuk menambah teks di playhead">
          <div className="bi-thumb t-text"><Icon n="text" size={22} /></div>
          <div className="bi-meta"><b>Teks / Judul</b><span className="muted xs">Seret ke T1</span></div>
          <button className="ib sm" title="Tambah teks di playhead" onClick={() => onAdd(null)}><Icon n="plus" size={14} /></button>
        </div>
        {shown.map((m) => (
          <div key={m.id} className={`bin-item ${m.missing ? "missing" : ""}`} draggable={!m.missing}
            onDragStart={(e) => { e.dataTransfer.setData("application/x-dvc-media", m.id); e.dataTransfer.setData(`application/x-dvc-kind-${m.kind}`, "1"); e.dataTransfer.effectAllowed = "copy"; }}
            title={`${m.name}\n${m.path}`}>
            <div className={`bi-thumb t-${m.kind}`}>
              {m.thumb && !m.missing ? <img src={api.thumbUrl(m.id)} alt="" draggable={false} /> : <Icon n={m.kind} size={22} />}
              {m.duration ? <span className="bi-dur mono">{fmtTime(m.duration, false)}</span> : null}
            </div>
            <div className="bi-meta">
              <b>{m.name}</b>
              <span className="muted xs">{KIND_LABEL[m.kind]} · {fmtBytes(m.size)}{m.width ? ` · ${m.width}×${m.height}` : ""}{m.fps && m.kind === "video" ? ` · ${Math.round(m.fps * 100) / 100} fps` : ""}</span>
              {m.missing && <span className="xs err">File tidak ditemukan · <button className="link" onClick={onRelink}>Panggil ulang</button></span>}
              {!m.missing && m.proxy === "pending" && <span className="xs warn">menyiapkan proxy preview…</span>}
              {m.proxy === "failed" && <span className="xs err">preview tidak tersedia (render tetap memakai file asli)</span>}
            </div>
            <div className="bi-actions">
              <button className="ib sm" title="Tambahkan ke timeline di playhead" onClick={() => onAdd(m)}><Icon n="plus" size={14} /></button>
              <button className="ib sm" title="Hapus dari daftar (file asli tidak dihapus)" onClick={() => onRemove(m)}><Icon n="x" size={14} /></button>
            </div>
          </div>))}
        {!media.length && <div className="bin-empty"><Icon n="import" size={28} /><p>Seret file video, audio, atau gambar ke sini<br />atau klik <b>Import</b>.</p><p className="muted xs">MP4 · MOV · MKV · AVI · MP3 · WAV · AAC · JPG · PNG · WEBP · SVG</p></div>}
      </div>
    </div>
  );
}

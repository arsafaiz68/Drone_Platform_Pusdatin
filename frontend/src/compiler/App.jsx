// Drone Video Compiler — halaman proyek & workspace editor (Media Bin · Preview · Inspector · Timeline).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ExportDialog from "./components/ExportDialog.jsx";
import Icon from "./components/Icon.jsx";
import Inspector from "./components/Inspector.jsx";
import MediaBin from "./components/MediaBin.jsx";
import MissingMedia from "./components/MissingMedia.jsx";
import Preview from "./components/Preview.jsx";
import ThemeButton from "./components/ThemeButton.jsx";
import Timeline from "./components/Timeline.jsx";
import { api } from "./lib/api.js";
import { ASPECT_OPTIONS, clamp, clipEnd, defaultTrackFor, fmtTime, mediaMap, newClip, projectDuration,
  round3, splitClip, trackEnd, uid } from "./lib/model.js";
import { useEditor } from "./lib/useEditor.js";

function useHashRoute() {
  const [h, setH] = useState(window.location.hash || "#/");
  useEffect(() => { const f = () => setH(window.location.hash || "#/"); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  return h;
}

function useToasts() {
  const [items, setItems] = useState([]);
  const notify = useCallback((text, tone = "info") => {
    const id = Math.random();
    setItems((x) => [...x.slice(-3), { id, text, tone }]);
    setTimeout(() => setItems((x) => x.filter((y) => y.id !== id)), 4500);
  }, []);
  const view = <div className="toasts">{items.map((t) => <div key={t.id} className={`toast ${t.tone}`}>{t.text}</div>)}</div>;
  return [notify, view];
}

export default function App() {
  const route = useHashRoute();
  const [notify, toasts] = useToasts();
  const m = route.match(/^#\/p\/([\w-]+)/);
  return (
    <>
      {m ? <Editor key={m[1]} projectId={m[1]} notify={notify} /> : <ProjectsHome notify={notify} />}
      {toasts}
    </>
  );
}

// ====================================================================== daftar proyek
function TopNav() {
  return (
    <nav className="topnav">
      <a href="/" title="Menu utama"><Icon n="home" size={15} /> Menu</a>
      <a href="/downloader/">Downloader</a>
      <a href="/trimmer/">Trimmer</a>
      <span className="on">Compiler</span>
    </nav>
  );
}

export function Logo({ size = 30 }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-label="Drone Video Compiler">
      <defs><linearGradient id="cmpLogo" x1="0.1" y1="0" x2="0.9" y2="1"><stop offset="0" stopColor="#bf5af2" /><stop offset="0.5" stopColor="#7d5cf5" /><stop offset="1" stopColor="#3a3ad6" /></linearGradient></defs>
      <rect width="32" height="32" rx="9" fill="url(#cmpLogo)" />
      <g fill="none" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        <rect x="6" y="8" width="20" height="5" rx="1.5" /><rect x="6" y="15.5" width="13" height="4" rx="1.5" /><rect x="11" y="22" width="15" height="3" rx="1.5" />
      </g>
    </svg>
  );
}

function ProjectsHome({ notify }) {
  const [list, setList] = useState(null);
  const [name, setName] = useState("");
  const [aspect, setAspect] = useState("16:9");
  const fileRef = useRef(null);
  const load = () => api.projects().then(setList).catch((e) => notify(e.message, "err"));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async () => {
    const p = await api.createProject(name.trim() || `Kompilasi ${new Date().toLocaleDateString("id-ID")}`, { aspect }).catch((e) => notify(e.message, "err"));
    if (p) window.location.hash = `#/p/${p.id}`;
  };
  const openFile = async () => {
    try {
      let text;
      if (window.showOpenFilePicker) {
        const [h] = await window.showOpenFilePicker({ types: [{ description: "Proyek Drone Video Compiler", accept: { "application/json": [".json", ".dvcproj"] } }] });
        text = await (await h.getFile()).text();
      } else { fileRef.current.click(); return; }
      await importText(text);
    } catch (e) { if (e.name !== "AbortError") notify(e.message, "err"); }
  };
  const importText = async (text) => {
    try {
      const p = await api.importProject(JSON.parse(text));
      if (p.missing_media?.length) notify(`${p.missing_media.length} media tidak ditemukan di pustaka komputer ini: ${p.missing_media.slice(0, 3).join(", ")}`, "warn");
      window.location.hash = `#/p/${p.id}`;
    } catch (e) { notify(`File proyek tidak valid: ${e.message}`, "err"); }
  };
  const rename = async (p) => {
    const n = window.prompt("Nama proyek baru:", p.name);
    if (n && n.trim()) { await api.renameProject(p.id, n.trim()).catch((e) => notify(e.message, "err")); load(); }
  };
  const dup = async (p) => { await api.duplicateProject(p.id).catch((e) => notify(e.message, "err")); load(); notify("Proyek diduplikat."); };
  const del = async (p) => {
    if (!window.confirm(`Hapus proyek "${p.name}"?\nFile video/audio/gambar asli di komputer Anda TIDAK ikut dihapus.`)) return;
    await api.deleteProject(p.id).catch((e) => notify(e.message, "err")); load(); notify("Proyek dihapus.");
  };

  return (
    <div className="home">
      <header className="home-top">
        <div className="brand"><Logo size={40} /><div><h1>Drone Video Compiler</h1><p>Editor multi-track sederhana — gabungkan video, gambar, teks, dan musik menjadi satu video final berkualitas tinggi.</p></div></div>
        <div className="row-gap"><ThemeButton /><TopNav /></div>
      </header>
      <section className="home-new">
        <div className="field grow"><label>Nama proyek baru</label><input value={name} placeholder="mis. Rangkuman Arus Mudik Merak" onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()} /></div>
        <div className="field"><label>Rasio aspek</label><select value={aspect} onChange={(e) => setAspect(e.target.value)}>{ASPECT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></div>
        <button className="btn primary" onClick={create}><Icon n="plus" size={14} /> New Project</button>
        <button className="btn" onClick={openFile}><Icon n="file" size={14} /> Load dari file…</button>
        <input ref={fileRef} type="file" accept=".json,.dvcproj" hidden onChange={async (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) importText(await f.text()); }} />
      </section>
      <section className="home-list">
        {list === null ? <p className="muted">Memuat…</p> : !list.length ? <p className="muted">Belum ada proyek. Buat proyek baru untuk mulai mengedit.</p> : list.map((p) => (
          <div key={p.id} className="pcard" onDoubleClick={() => { window.location.hash = `#/p/${p.id}`; }}>
            <a className="pcard-thumb" href={`#/p/${p.id}`}>{p.thumb_media ? <img src={api.thumbUrl(p.thumb_media)} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} /> : <Icon n="film" size={30} />}</a>
            <div className="pcard-body">
              <a href={`#/p/${p.id}`}><b>{p.name}</b></a>
              <span className="muted xs">{fmtTime(p.duration, false)} · {p.clips} klip · {p.media} media · {p.aspect}</span>
              <span className="muted xs">Diubah {p.updated_at ? new Date(p.updated_at).toLocaleString("id-ID") : "–"}</span>
            </div>
            <div className="pcard-actions">
              <a className="btn sm primary" href={`#/p/${p.id}`}>Buka</a>
              <button className="ib sm" title="Ganti nama" onClick={() => rename(p)}><Icon n="edit" size={14} /></button>
              <button className="ib sm" title="Duplikat" onClick={() => dup(p)}><Icon n="copy" size={14} /></button>
              <button className="ib sm danger" title="Hapus proyek" onClick={() => del(p)}><Icon n="trash" size={14} /></button>
            </div>
          </div>))}
      </section>
      <p className="home-foot muted xs">Proyek disimpan sebagai file JSON di komputer ini (folder data/compiler/projects). Semua pemrosesan berjalan lokal dengan FFmpeg — video tidak diunggah ke server luar.</p>
    </div>
  );
}

// ====================================================================== editor
function Editor({ projectId, notify }) {
  const ed = useEditor(projectId);
  const { project, commit, live, undo, redo } = ed;
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [zoom, setZoom] = useState(40);
  const [snapOn, setSnapOn] = useState(true);
  const [showExport, setShowExport] = useState(false);
  const [system, setSystem] = useState(null);
  const [tlH, setTlH] = useState(() => Number(localStorage.getItem("dvc-tl-h")) || 320);
  const importRef = useRef(null);
  const [missing, setMissing] = useState([]);
  const [showMissing, setShowMissing] = useState(false);
  const checkedRef = useRef(false);
  const missingIds = useMemo(() => new Set(missing.map((m) => m.id)), [missing]);
  const mm = useMemo(() => {
    if (!project) return {};
    const m = mediaMap(project);
    for (const id of missingIds) if (m[id]) m[id] = { ...m[id], missing: true };
    return m;
  }, [project, missingIds]);
  const selected = project?.clips.find((c) => c.id === selectedId) || null;

  useEffect(() => { api.system().then(setSystem).catch(() => {}); }, []);

  // cek media yang hilang / berpindah folder saat proyek dibuka
  const checkMissing = useCallback(async (open) => {
    const p = ed.getProject();
    if (!p || !p.media.length) { setMissing([]); return; }
    try {
      const st = await api.checkMedia(p.media);
      const miss = st.filter((x) => !x.exists);
      setMissing(miss);
      if (open && miss.length) setShowMissing(true);
    } catch { /* abaikan */ }
  }, [ed]);
  useEffect(() => { if (project && !checkedRef.current) { checkedRef.current = true; checkMissing(true); } }, [project, checkMissing]);

  const onRelinked = (res) => {
    const oldId = res.relinked_from;
    const { relinked_from: _a, warning: _b, ...media } = res;
    commit((p) => {
      const exists = p.media.some((x) => x.id === media.id && x.id !== oldId);
      const list = exists ? p.media.filter((x) => x.id !== oldId) : p.media.map((x) => (x.id === oldId ? { ...x, ...media } : x));
      return { ...p, media: list, clips: p.clips.map((c) => (c.media_id === oldId ? { ...c, media_id: media.id } : c)) };
    });
    setMissing((ms) => ms.filter((x) => x.id !== oldId));
  };
  useEffect(() => { document.title = project ? `${project.name} · Drone Video Compiler` : "Drone Video Compiler"; }, [project?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  // perbarui status thumbnail/waveform/proxy media yang masih diproses
  useEffect(() => {
    if (!project) return undefined;
    const pending = project.media.filter((m) => m.proxy === "pending" || ((m.kind === "video" || m.kind === "image") && !m.thumb) || (m.has_audio && !m.wave)).map((m) => m.id);
    if (!pending.length) return undefined;
    const t = setTimeout(() => api.mediaStatus(pending).then(ed.patchMedia).catch(() => {}), 1500);
    return () => clearTimeout(t);
  }, [project?.media]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const f = (e) => { if (ed.dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", f);
    return () => window.removeEventListener("beforeunload", f);
  }, [ed.dirty]);

  const save = useCallback(async () => {
    try { await ed.save(); notify("Proyek disimpan.", "ok"); } catch (e) { notify(`Gagal menyimpan: ${e.message}`, "err"); }
  }, [ed, notify]);

  const saveToFile = async () => {
    const p = ed.getProject();
    const data = JSON.stringify({ ...p, format: "drone-video-compiler-project", saved_at: new Date().toISOString() }, null, 2);
    const fname = `${p.name.replace(/[\\/:*?"<>|]+/g, "_")}.dvcproj.json`;
    try {
      if (window.showSaveFilePicker) {
        const h = await window.showSaveFilePicker({ suggestedName: fname, types: [{ description: "Proyek Drone Video Compiler", accept: { "application/json": [".json"] } }] });
        const w = await h.createWritable(); await w.write(data); await w.close();
      } else {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([data], { type: "application/json" })); a.download = fname; a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      }
      await ed.save();
      notify("Proyek disimpan ke file dan ke pustaka proyek.", "ok");
    } catch (e) { if (e.name !== "AbortError") notify(e.message, "err"); }
  };

  const ensureSaved = useCallback(async (override) => (override || ed.dirty ? ed.save(override) : ed.getProject()), [ed]);

  // ------------------------------------------------------------- aksi klip
  const addMedia = (list) => commit((p) => {
    const have = new Set(p.media.map((x) => x.id));
    const add = list.filter((x) => !have.has(x.id));
    return add.length ? { ...p, media: [...p.media, ...add] } : p;
  });

  const placeClip = (p, c) => {
    const overl = p.clips.some((x) => x.track === c.track && x.start < clipEnd(c) - 1e-3 && clipEnd(x) > c.start + 1e-3);
    if (overl && (c.track === "V1" || c.track === "A1")) c.start = round3(trackEnd(p, c.track));
    return c;
  };

  const dropMedia = (mid, trackId, t) => {
    const m = mm[mid];
    if (!m) return;
    const c = newClip(m.kind, trackId, t, m);
    commit((p) => ({ ...p, clips: [...p.clips, c] }));
    setSelectedId(c.id);
  };
  const dropText = (trackId, t) => {
    const c = newClip("text", trackId, t);
    commit((p) => ({ ...p, clips: [...p.clips, c] }));
    setSelectedId(c.id);
  };
  const addAtPlayhead = (m) => {
    if (!m) { dropText("T1", time); return; }
    const tr = defaultTrackFor(m);
    commit((p) => {
      const c = placeClip(p, newClip(m.kind, tr, time, m));
      setSelectedId(c.id);
      return { ...p, clips: [...p.clips, c] };
    });
  };
  const removeMedia = (m) => {
    const used = project.clips.filter((c) => c.media_id === m.id).length;
    if (used && !window.confirm(`"${m.name}" dipakai ${used} klip di timeline. Hapus dari daftar beserta klipnya?\n(File asli di komputer tidak dihapus.)`)) return;
    commit((p) => ({ ...p, media: p.media.filter((x) => x.id !== m.id), clips: p.clips.filter((c) => c.media_id !== m.id) }));
  };

  const doSplit = () => {
    const p = ed.getProject();
    const targets = selected && time > selected.start && time < clipEnd(selected) ? [selected]
      : p.clips.filter((c) => time > c.start && time < clipEnd(c) && !p.tracks.find((t) => t.id === c.track)?.locked);
    if (!targets.length) { notify("Tidak ada klip di posisi playhead untuk di-split."); return; }
    commit((cur) => {
      let clips = cur.clips;
      for (const c of targets) {
        const r = splitClip(c, time);
        if (r) clips = clips.flatMap((x) => (x.id === c.id ? r : [x]));
      }
      return { ...cur, clips };
    });
  };
  const doDelete = () => {
    if (!selected) { notify("Pilih klip yang akan dihapus."); return; }
    commit((p) => ({ ...p, clips: p.clips.filter((c) => c.id !== selected.id) }));
    setSelectedId(null);
  };
  const doDuplicate = () => {
    if (!selected) return;
    const c = { ...selected, id: uid("c"), start: round3(clipEnd(selected)), transition: "none" };
    commit((p) => ({ ...p, clips: [...p.clips, c] }));
    setSelectedId(c.id);
  };
  const livePatch = (id, patch) => live((p) => ({ ...p, clips: p.clips.map((c) => (c.id === id ? { ...c, ...patch } : c)) }));

  // ------------------------------------------------------------- pintasan keyboard
  const keyRef = useRef();
  keyRef.current = (e) => {
    const tag = e.target.tagName;
    const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target.isContentEditable;
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); save(); return; }
    if (typing) return;
    if (mod && e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
    else if (mod && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) { e.preventDefault(); redo(); }
    else if (mod && e.key.toLowerCase() === "d") { e.preventDefault(); doDuplicate(); }
    else if (e.key === " ") { e.preventDefault(); togglePlay(); }
    else if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); doDelete(); }
    else if (e.key.toLowerCase() === "s") doSplit();
    else if (e.key === "Home") { setPlaying(false); setTime(0); }
    else if (e.key === "End") { setPlaying(false); setTime(projectDuration(ed.getProject())); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const d = (e.shiftKey ? 1 : 1 / (project.settings?.fps || 30)) * (e.key === "ArrowLeft" ? -1 : 1);
      setPlaying(false); setTime((t) => clamp(t + d, 0, projectDuration(ed.getProject())));
    } else if (e.key === "Escape") setSelectedId(null);
    else if (e.key === "+" || e.key === "=") setZoom((z) => clamp(z * 1.3, 2, 400));
    else if (e.key === "-") setZoom((z) => clamp(z / 1.3, 2, 400));
  };
  useEffect(() => { const f = (e) => keyRef.current(e); window.addEventListener("keydown", f); return () => window.removeEventListener("keydown", f); }, []);

  const togglePlay = () => {
    if (!playing && time >= projectDuration(ed.getProject()) - 0.05) setTime(0);
    setPlaying((v) => !v);
  };

  const onSplitterDown = (e) => {
    const y0 = e.clientY, h0 = tlH;
    const move = (ev) => setTlH(clamp(h0 - (ev.clientY - y0), 180, window.innerHeight - 260));
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); localStorage.setItem("dvc-tl-h", String(tlH)); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };

  const goHome = () => {
    if (ed.dirty && !window.confirm("Perubahan belum disimpan. Tetap kembali ke daftar proyek?")) return;
    window.location.hash = "#/";
  };
  const rename = async () => {
    const n = window.prompt("Nama proyek:", project.name);
    if (n && n.trim()) commit((p) => ({ ...p, name: n.trim() }));
  };

  if (ed.error) return <div className="home"><p className="note err">{ed.error}</p><a className="btn" href="#/">Kembali ke daftar proyek</a></div>;
  if (!project) return <div className="loading">Memuat proyek…</div>;
  const btn = (n, label, onClick, opts = {}) => (
    <button className={`tb ${opts.cls || ""}`} onClick={onClick} disabled={opts.disabled} title={opts.title || label}><Icon n={n} size={16} /><span>{label}</span></button>);

  return (
    <div className="ed" style={{ gridTemplateRows: `46px minmax(200px, 1fr) 6px ${tlH}px` }}>
      <header className="toolbar">
        <button className="ib" onClick={goHome} title="Daftar proyek"><Icon n="back" /></button>
        <Logo size={26} />
        <button className="pname" onClick={rename} title="Ganti nama proyek">{project.name}{ed.dirty && <i className="dirty" title="Ada perubahan belum disimpan" />}</button>
        <div className="tb-group">
          {btn("import", "Import", () => importRef.current?.(), { title: "Impor media (video, audio, gambar)" })}
          {btn("split", "Split", doSplit, { title: "Bagi klip di playhead (S)" })}
          {btn("trash", "Delete", doDelete, { disabled: !selected, title: "Hapus klip terpilih (Delete)" })}
          {btn("undo", "Undo", undo, { disabled: !ed.canUndo, title: "Undo (Ctrl+Z)" })}
          {btn("redo", "Redo", redo, { disabled: !ed.canRedo, title: "Redo (Ctrl+Y)" })}
          {btn("save", ed.saving ? "Menyimpan…" : "Save Project", save, { title: "Simpan proyek (Ctrl+S)", cls: ed.dirty ? "attn" : "" })}
          {btn("file", "Simpan ke file", saveToFile, { title: "Simpan salinan proyek (.json) ke folder pilihan" })}
        </div>
        {missing.length > 0 && <button className="tb missing" onClick={() => setShowMissing(true)} title="Beberapa file media berpindah folder atau tidak ditemukan"><Icon n="folder" size={16} /><span>{missing.length} media hilang</span></button>}
        <span className="grow" />
        <ThemeButton />
        <TopNav />
        <button className="tb primary" onClick={() => {
          setPlaying(false);
          if (missing.some((m) => project.clips.some((c) => c.media_id === m.id))) { notify("Ada media yang hilang dan masih dipakai klip — panggil ulang dulu sebelum export.", "warn"); setShowMissing(true); return; }
          setShowExport(true);
        }} disabled={!project.clips.length}><Icon n="export" size={16} /><span>Export</span></button>
      </header>
      <div className="ed-mid">
        <MediaBin media={project.media.map((m) => mm[m.id] || m)} onRelink={() => setShowMissing(true)} onImported={(l) => { addMedia(l); notify(`${l.length} media diimpor.`, "ok"); }} onRemove={removeMedia}
          onAdd={addAtPlayhead} notify={notify} importRef={importRef} />
        <Preview project={project} mm={mm} time={time} playing={playing} onPlayingChange={setPlaying} onTime={setTime}
          selectedId={selectedId} onSelect={setSelectedId} onLivePatch={livePatch} onCommitFrom={(snap) => commit((p) => p, snap)} />
        <Inspector project={project} mm={mm} selected={selected} live={live} commit={commit} time={time}
          onSplit={doSplit} onDelete={doDelete} onDuplicate={doDuplicate} notify={notify} />
      </div>
      <div className="splitter" onPointerDown={onSplitterDown} title="Seret untuk mengubah tinggi timeline" />
      <Timeline project={project} mm={mm} zoom={zoom} setZoom={setZoom} time={time} onSeek={(t) => { setPlaying(false); setTime(t); }}
        selectedId={selectedId} onSelect={setSelectedId} live={live} commit={commit} onDropMedia={dropMedia} onDropText={dropText}
        notify={notify} snapOn={snapOn} setSnapOn={setSnapOn} />
      {showMissing && missing.length > 0 && <MissingMedia missing={missing} project={project} notify={notify} onRelinked={onRelinked}
        onClose={() => setShowMissing(false)} />}
      {showExport && <ExportDialog project={project} mm={mm} system={system} onClose={() => setShowExport(false)} ensureSaved={ensureSaved}
        notify={(t) => notify(t, "err")} onExportSettings={(x) => commit((p) => ({ ...p, export: { ...p.export, ...x } }))} />}
    </div>
  );
}

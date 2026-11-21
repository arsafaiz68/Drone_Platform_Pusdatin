// Dialog media hilang: file proyek berpindah folder/terhapus. Pengguna dapat memanggil ulang (relink)
// tiap file, mencari otomatis seluruh file di folder baru, atau membuka folder lamanya di Explorer.
import { useState } from "react";
import { api } from "../lib/api.js";
import { fmtBytes } from "../lib/model.js";
import Icon from "./Icon.jsx";

export default function MissingMedia({ missing, project, onRelinked, onClose, notify }) {
  const [busy, setBusy] = useState(null);       // id atau "folder"
  const [manual, setManual] = useState({});     // id -> path ketik manual
  const [folder, setFolder] = useState("");
  const [msg, setMsg] = useState({});           // id -> {tone,text}
  const usage = (id) => project.clips.filter((c) => c.media_id === id);
  const tracksOf = (id) => [...new Set(usage(id).map((c) => c.track))].join(", ");

  const apply = (res) => {
    onRelinked(res);
    setMsg((x) => ({ ...x, [res.relinked_from]: { tone: res.warning ? "warn" : "ok", text: res.warning || `Tersambung: ${res.path}` } }));
  };
  const relinkPath = async (m, path) => {
    if (!path) return;
    setBusy(m.id);
    try { apply(await api.relinkMedia(m.id, path, m.kind)); }
    catch (e) { setMsg((x) => ({ ...x, [m.id]: { tone: "err", text: e.message } })); }
    finally { setBusy(null); }
  };
  const browseFile = async (m) => {
    setBusy(m.id);
    try {
      const r = await api.pickFile(m.nearest_folder || folder || "", m.name);
      setBusy(null);
      if (r.path) await relinkPath(m, r.path);
    } catch (e) { setBusy(null); setMsg((x) => ({ ...x, [m.id]: { tone: "err", text: e.message } })); }
  };
  const searchFolder = async (path) => {
    const f = path || folder;
    if (!f) return;
    setBusy("folder");
    try {
      const r = await api.findMedia(f, missing.map((m) => ({ id: m.id, name: m.name, size: m.size, kind: m.kind })));
      r.relinked.forEach(apply);
      r.errors.forEach((e) => setMsg((x) => ({ ...x, [e.id]: { tone: "err", text: e.error } })));
      r.not_found.forEach((id) => setMsg((x) => ({ ...x, [id]: { tone: "err", text: "Tidak ditemukan di folder tersebut." } })));
      notify(`${r.relinked.length} dari ${missing.length} media ditemukan & dipanggil ulang (${r.scanned} file diperiksa).`, r.relinked.length ? "ok" : "warn");
    } catch (e) { notify(e.message, "err"); } finally { setBusy(null); }
  };
  const browseFolder = async () => {
    setBusy("folder");
    try {
      const r = await api.pickFolder(folder || missing[0]?.nearest_folder || "");
      setBusy(null);
      if (r.path) { setFolder(r.path); await searchFolder(r.path); }
    } catch (e) { setBusy(null); notify(e.message, "err"); }
  };
  const openOld = async (m) => {
    try { const r = await api.openLocation(m.path); notify(`Membuka ${r.opened}`); } catch (e) { notify(e.message, "err"); }
  };

  return (
    <div className="modal-bg">
      <div className="modal">
        <div className="modal-head"><span><Icon n="folder" /> Media tidak ditemukan ({missing.length})</span><button className="ib" onClick={onClose} title="Tutup"><Icon n="x" /></button></div>
        <div className="modal-body">
          <p className="muted" style={{ marginTop: 0 }}>File berikut sudah berpindah folder, diganti nama, atau berada di komputer lain. Panggil ulang filenya agar klip di track kembali tersambung — posisi, durasi, dan pengaturan klip tidak berubah.</p>
          <div className="mm-folder">
            <b>Cari otomatis di folder baru</b>
            <div className="row-gap">
              <input className="grow" value={folder} placeholder="mis. D:\Video Drone\Arsip 2026" onChange={(e) => setFolder(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchFolder()} />
              <button className="btn" disabled={busy === "folder"} onClick={browseFolder}><Icon n="folder" size={14} /> Pilih folder…</button>
              <button className="btn primary" disabled={!folder || busy === "folder"} onClick={() => searchFolder()}>{busy === "folder" ? "Mencari…" : "Cari & sambungkan"}</button>
            </div>
            <span className="muted xs">Semua subfolder diperiksa; file dicocokkan berdasarkan nama (dan ukuran bila ada beberapa).</span>
          </div>
          <div className="mm-list">
            {missing.map((m) => (
              <div key={m.id} className="mm-item">
                <div className={`bi-thumb t-${m.kind}`}><Icon n={m.kind || "file"} size={20} /></div>
                <div className="mm-meta">
                  <b>{m.name}</b>
                  <span className="xs muted mono wrap">{m.path || "(path tidak tercatat)"}</span>
                  <span className="xs muted">{m.kind} · {fmtBytes(m.size)} · dipakai {usage(m.id).length} klip{tracksOf(m.id) ? ` di ${tracksOf(m.id)}` : ""}</span>
                  <div className="row-gap">
                    <input className="grow" placeholder="Tempel path file baru…" value={manual[m.id] || ""} onChange={(e) => setManual({ ...manual, [m.id]: e.target.value })}
                      onKeyDown={(e) => e.key === "Enter" && relinkPath(m, manual[m.id])} />
                    {manual[m.id] && <button className="btn sm" onClick={() => relinkPath(m, manual[m.id])}>Pakai</button>}
                  </div>
                  {msg[m.id] && <span className={`xs ${msg[m.id].tone}`}>{msg[m.id].text}</span>}
                </div>
                <div className="mm-actions">
                  <button className="btn sm primary" disabled={busy === m.id} onClick={() => browseFile(m)} title="Pilih file pengganti; semua klip yang memakai media ini tersambung lagi">
                    <Icon n="file" size={14} /> {busy === m.id ? "…" : "Panggil ulang"}</button>
                  <button className="btn sm" onClick={() => openOld(m)} title="Buka folder lama (atau folder terdekat yang masih ada) di Explorer"><Icon n="folder" size={14} /> Buka folder</button>
                </div>
              </div>))}
          </div>
        </div>
        <div className="modal-foot"><span className="muted xs">Klip dari media yang hilang ditandai merah di timeline dan dilewati saat preview.</span><span className="grow" /><button className="btn" onClick={onClose}>Lanjutkan tanpa media ini</button></div>
      </div>
    </div>
  );
}

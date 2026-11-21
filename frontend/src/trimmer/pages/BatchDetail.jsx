import { useRef, useState } from "react";
import { DeleteBatchModal, ZipButton } from "../components/BatchActions.jsx";
import ImportDownloadsModal, { InfoSummary } from "../components/ImportDownloadsModal.jsx";
import RouteDiagram from "../components/RouteDiagram.jsx";
import { Card, Empty, ErrorBox, Field, Loading, Modal, Notice, ProgressBar, Segmented, Stat, StatusBadge,
  useAction, useConfirm } from "../components/ui.jsx";
import { navigate, useLoad, usePolling } from "../hooks/useApi.js";
import DurationSlider from "../components/DurationSlider.jsx";
import { api, fmtBytes, fmtDur, fmtSec, infoSourceLabel, tripLabel } from "../services/api.js";

const MAX = 24;
const TRAFFIC = ["Lancar", "Ramai Lancar", "Ramai", "Padat", "Padat Merayap", "Macet", "Tidak Teridentifikasi"];

function PendingFiles({ files, setFiles, existing, onUpload, busy, progress }) {
  const total = existing + files.length;
  const over = total > MAX;
  return (
    <Card title={`File dipilih (${files.length})`} actions={<button className="btn btn-sm" onClick={() => setFiles([])}>Kosongkan</button>}>
      {over && <Notice tone="err" title="Melebihi batas batch">
        Batch maksimal {MAX} video. Saat ini {existing} video + {files.length} dipilih = {total}. Hapus sebagian file; unggahan dan pemrosesan tidak akan dimulai.
      </Notice>}
      <table className="table table-compact">
        <thead><tr><th>Nama file</th><th>Ukuran</th><th>Tipe</th><th /></tr></thead>
        <tbody>
          {files.map((f, i) => (
            <tr key={i}><td>{f.name}</td><td>{fmtBytes(f.size)}</td><td className="small muted">{f.type || "–"}</td>
              <td><button className="btn btn-sm btn-ghost" onClick={() => setFiles(files.filter((_, j) => j !== i))}>Hapus</button></td></tr>
          ))}
        </tbody>
      </table>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn btn-primary" disabled={over || busy || !files.length} onClick={onUpload}>Unggah {files.length} video</button>
        {busy && <div style={{ flex: 1 }}><ProgressBar value={progress} label={`Mengunggah ${Math.round(progress * 100)}%`} /></div>}
      </div>
      <p className="small muted">Video disalin ke folder data lokal; file asli tidak diubah. Untuk file sangat besar gunakan “Tambah dari path lokal” agar tidak disalin.</p>
    </Card>
  );
}

function VideoInfoModal({ video, templates, onClose, onSave }) {
  const [f, setF] = useState({ location_name: video.location_name || "", traffic_condition: video.traffic_condition || "",
    event_date: video.event_date || "", event_time: video.event_time || "", template_code: video.template_code || "" });
  const meta = video.source_meta || {};
  return (
    <Modal open title={`Informasi video — ${video.filename}`} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Batal</button>
      <button className="btn btn-primary" onClick={() => onSave(f)}>Simpan</button>
    </>}>
      <p className="small muted">Sumber informasi: <b>{meta._source === "filename" ? "nama file" : infoSourceLabel(video.source_origin)}</b>.
        Informasi ini dipakai untuk nama file & metadata video hasil (Clipped_DD.MM_HH.MM_Lokasi_Lalin.mp4).</p>
      <div className="form">
        <Field label="Nama lokasi"><input value={f.location_name} onChange={(e) => setF({ ...f, location_name: e.target.value })} /></Field>
        <Field label="Jenis lokasi (template pemantauan)" hint="Ditebak otomatis dari nama lokasi. Mengubahnya menghapus kandidat lama; video perlu dianalisis ulang.">
          <select value={f.template_code} onChange={(e) => setF({ ...f, template_code: e.target.value })}>
            {(templates || []).map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
          </select>
        </Field>
        <Field label="Kondisi lalu lintas" hint="Teks bebas dari laporan, atau pilih kategori standar.">
          <input list="traffic-list" value={f.traffic_condition} onChange={(e) => setF({ ...f, traffic_condition: e.target.value })} />
          <datalist id="traffic-list">{TRAFFIC.map((t) => <option key={t} value={t} />)}</datalist>
        </Field>
        <div className="grid-2">
          <Field label="Tanggal"><input type="date" value={f.event_date} onChange={(e) => setF({ ...f, event_date: e.target.value })} /></Field>
          <Field label="Waktu"><input type="time" value={f.event_time} onChange={(e) => setF({ ...f, event_time: e.target.value })} /></Field>
        </div>
        {(meta.weather || meta.url_original || meta.timezone) && <div className="small muted">
          {meta.weather && <div>Cuaca: {meta.weather}</div>}
          {meta.timezone && <div>Zona waktu laporan: {meta.timezone}</div>}
          {meta.url_original && <div className="wrap-any">URL: {meta.url_original}</div>}
        </div>}
      </div>
    </Modal>
  );
}

function MappingModal({ video, template, onClose, onSave }) {
  const [sel, setSel] = useState(video?.point_mapping || []);
  const [dir, setDir] = useState(video?.direction_override || "");
  if (!video) return null;
  const pts = template?.points || [];
  const toggle = (c) => setSel(sel.includes(c) ? sel.filter((x) => x !== c) : [...sel, c]);
  return (
    <Modal open title={`Pemetaan titik — ${video.filename}`} onClose={onClose} footer={<>
      <button className="btn" onClick={() => onSave({ point_mapping: [], direction_override: "" })}>Hapus pemetaan (otomatis)</button>
      <button className="btn btn-primary" onClick={() => onSave({ point_mapping: sel, direction_override: dir })}>Simpan</button>
    </>}>
      <p className="small muted">Gunakan bila video hanya mencakup sebagian lintasan atau urutan file tidak sama dengan urutan titik.
        Klik titik sesuai urutan kemunculannya di video. Video akan dibagi menurut urutan ini dan label ditandai sebagai pemetaan operator.
        Analisis ulang diperlukan setelah mengubah pemetaan.</p>
      <div className="chips">
        {pts.map((p) => (
          <button key={p.code} className={`chip ${sel.includes(p.code) ? "chip-on" : ""}`} onClick={() => toggle(p.code)}>
            {sel.includes(p.code) && <b>{sel.indexOf(p.code) + 1}. </b>}{p.code} · {p.name}
          </button>
        ))}
      </div>
      <Field label="Urutan terpilih"><div className="mono">{sel.length ? sel.join(" → ") : "otomatis (seluruh lintasan)"}</div></Field>
      <Field label="Arah perjalanan video">
        <Segmented value={dir} onChange={setDir} options={[{ value: "", label: "Otomatis" }, { value: "outbound", label: "Pergi" }, { value: "return", label: "Kembali" }]} />
      </Field>
    </Modal>
  );
}

function RouteEditor({ batch, onSave, disabled }) {
  const r = batch.route_resolved;
  const [out, setOut] = useState(r.outbound.join(","));
  const [ret, setRet] = useState(r.return.join(","));
  const [turn, setTurn] = useState(r.turnarounds.join(","));
  const parse = (s) => s.split(/[,\s→>]+/).map((x) => x.trim()).filter(Boolean);
  return (
    <div className="form">
      <RouteDiagram outbound={r.outbound} ret={r.return} turnarounds={r.turnarounds} showReturn={batch.trip_mode === "round_trip"} />
      <div className="grid-3">
        <Field label="Urutan pergi"><input disabled={disabled} value={out} onChange={(e) => setOut(e.target.value)} /></Field>
        <Field label="Urutan kembali"><input disabled={disabled} value={ret} onChange={(e) => setRet(e.target.value)} /></Field>
        <Field label="Titik putar balik"><input disabled={disabled} value={turn} onChange={(e) => setTurn(e.target.value)} /></Field>
      </div>
      <div className="row">
        <button className="btn btn-sm" disabled={disabled} onClick={() => onSave({ outbound: parse(out), return: parse(ret), turnarounds: parse(turn) })}>Simpan lintasan</button>
        <button className="btn btn-sm btn-ghost" disabled={disabled} onClick={() => onSave(null)}>Kembalikan ke default template</button>
      </div>
      <p className="small muted">Berlaku untuk video berjenis lokasi {batch.template_name}; video dengan jenis lokasi lain memakai lintasan bawaan templatenya. Ubah bila pola penerbangan aktual berbeda dari template. Berlaku untuk analisis berikutnya.</p>
    </div>
  );
}

function GroupRow({ g, onSave, onDelete, canDelete }) {
  const [f, setF] = useState({ name: g.name, location_name: g.location_name || "", traffic_condition: g.traffic_condition || "Tidak Teridentifikasi",
    event_date: g.event_date || "", event_time: g.event_time || "" });
  const dirty = JSON.stringify(f) !== JSON.stringify({ name: g.name, location_name: g.location_name || "", traffic_condition: g.traffic_condition || "Tidak Teridentifikasi", event_date: g.event_date || "", event_time: g.event_time || "" });
  return (
    <tr>
      <td><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></td>
      <td><input value={f.location_name} placeholder="Nama lokasi" onChange={(e) => setF({ ...f, location_name: e.target.value })} /></td>
      <td><select value={f.traffic_condition} onChange={(e) => setF({ ...f, traffic_condition: e.target.value })}>{TRAFFIC.map((t) => <option key={t}>{t}</option>)}</select></td>
      <td><input type="date" value={f.event_date} onChange={(e) => setF({ ...f, event_date: e.target.value })} /></td>
      <td><input type="time" value={f.event_time} onChange={(e) => setF({ ...f, event_time: e.target.value })} /></td>
      <td className="center">{g.video_count}</td>
      <td className="nowrap">
        <button className="btn btn-sm" disabled={!dirty} onClick={() => onSave(g.id, f)}>Simpan</button>
        {canDelete && <button className="btn btn-sm btn-ghost" onClick={() => onDelete(g.id)}>Hapus</button>}
      </td>
    </tr>
  );
}

export default function BatchDetail({ batchId }) {
  const b = useLoad(() => api.batch(batchId), [batchId]);
  const it = useLoad(() => api.items(batchId), [batchId]);
  const tmpl = useLoad(async () => (b.data ? api.template(b.data.template_code) : null), [b.data?.template_code]);
  const tmpls = useLoad(() => api.templates(), []);
  const tmplName = (code) => ((tmpls.data || []).find((t) => t.code === code) || {}).name || code;
  const [files, setFiles] = useState([]);
  const [upProg, setUpProg] = useState(0);
  const [pathsOpen, setPathsOpen] = useState(false);
  const [pathsText, setPathsText] = useState("");
  const [mapVideo, setMapVideo] = useState(null);
  const [infoVideo, setInfoVideo] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [delOpen, setDelOpen] = useState(false);
  const [report, setReport] = useState(null);
  const fileRef = useRef(null);
  const [run, busy] = useAction();
  const confirm = useConfirm();
  const active = b.data && ["running", "queued"].includes(b.data.status);
  usePolling(async () => { await Promise.all([b.reload(), it.reload()]); }, 1500, true);

  if (b.loading && !b.data) return <div className="page"><Loading /></div>;
  if (b.error && !b.data) return <div className="page"><ErrorBox error={b.error} onRetry={b.reload} /></div>;
  const batch = b.data;
  const items = it.data || [];
  const st = batch.stats;
  const editable = !active;
  const refresh = () => Promise.all([b.reload(), it.reload()]);

  const pick = (e) => {
    const chosen = Array.from(e.target.files || []);
    e.target.value = "";
    const next = [...files, ...chosen];
    setFiles(next);
  };
  const upload = async () => {
    if (items.length + files.length > MAX) return;
    setUpProg(0);
    const r = await run(() => api.uploadVideos(batchId, files, setUpProg), `${files.length} video diunggah`);
    if (r) { setFiles([]); refresh(); }
  };
  const addPaths = async () => {
    const list = pathsText.split(/\r?\n/).map((s) => s.trim().replace(/^"|"$/g, "")).filter(Boolean);
    if (items.length + list.length > MAX) {
      return run(async () => { throw new Error(`Maksimal ${MAX} video per batch (akan menjadi ${items.length + list.length}).`); });
    }
    const r = await run(() => api.addPaths(batchId, list), `${list.length} video ditambahkan`);
    if (r) { setPathsOpen(false); setPathsText(""); refresh(); }
  };
  const act = (fn, msg) => run(fn, msg).then(refresh);
  const move = (idx, d) => {
    const ids = items.map((x) => x.video_id);
    const j = idx + d;
    if (j < 0 || j >= ids.length) return;
    [ids[idx], ids[j]] = [ids[j], ids[idx]];
    act(() => api.reorderVideos(batchId, ids));
  };
  const buildFinals = async () => {
    const r = await run(() => api.buildFinals(batchId));
    if (r) {
      run(async () => true, `${r.length} video hasil disusun — satu untuk setiap video sumber (${batch.final_duration} dtk)`);
      if (r.length) navigate(`/review/${batchId}?final=${r[0].id}`);
    }
  };
  const doImport = async (body) => {
    const r = await run(() => api.importDownloads(batchId, body));
    if (r) {
      run(async () => true, `${r.added} video diimpor dari Drone Video Downloader`);
      setImportOpen(false); refresh();
    }
  };
  const exportAll = async () => {
    const r = await run(() => api.exportAll(batchId, false));
    if (r) {
      if (r.errors.length) r.errors.forEach((e) => run(async () => { throw new Error(`Video final #${e.final_video_id}: ${e.error}`); }));
      if (r.started.length) run(async () => true, `${r.started.length} ekspor dimulai — lihat Riwayat Ekspor`);
    }
  };
  const showReport = async () => setReport(await run(() => api.report(batchId)));

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <a href="#/batches" className="small">← Semua batch</a>
          <h1>{batch.name} <StatusBadge status={batch.status} label={batch.status_label} /></h1>
          <p className="muted">{batch.project_name} · Template {batch.template_name}{batch.recovered ? " · dipulihkan setelah aplikasi dimulai ulang — klik Lanjutkan" : ""}</p>
        </div>
      </header>

      <div className="toolbar">
        <input ref={fileRef} type="file" multiple accept="video/*,.mp4,.mov,.mkv,.avi,.m4v,.mts,.ts" hidden onChange={pick} />
        <button className="btn" disabled={!editable} onClick={() => fileRef.current.click()}>Tambah Video</button>
        <button className="btn" disabled={!editable} onClick={() => setPathsOpen(true)}>Tambah dari path lokal</button>
        <button className="btn" disabled={!editable} onClick={() => setImportOpen(true)}>Impor dari Downloader</button>
        <span className="sep" />
        {["draft", "review", "completed", "failed", "cancelled"].includes(batch.status) &&
          <button className="btn btn-primary" disabled={!items.length || items.length > MAX} onClick={() => act(() => api.startBatch(batchId), "Batch dimulai")}>Mulai Batch</button>}
        {active && <button className="btn" onClick={() => act(() => api.pauseBatch(batchId), "Batch dijeda")}>Jeda Batch</button>}
        {batch.status === "paused" && <button className="btn btn-primary" onClick={() => act(() => api.resumeBatch(batchId), "Batch dilanjutkan")}>Lanjutkan Batch</button>}
        {(active || batch.status === "paused") && <button className="btn btn-danger" onClick={async () => {
          if (await confirm({ title: "Batalkan batch?", message: "Video yang menunggu dan sedang dianalisis akan dibatalkan. Hasil yang sudah selesai tetap tersimpan.", danger: true, confirmText: "Batalkan batch" }))
            act(() => api.cancelBatch(batchId), "Batch dibatalkan");
        }}>Batalkan Batch</button>}
        <span className="sep" />
        <button className="btn" disabled={!st.completed} onClick={() => navigate(`/review/${batchId}`)}>Review Hasil</button>
        {(batch.stats.by_status?.review || 0) > 0 && <button className="btn" title="Tandai semua video berstatus 'Menunggu review' sebagai selesai direview"
          onClick={async () => { if (await confirm({ title: "Tandai semua selesai direview?", message: `${batch.stats.by_status.review} video berstatus "Menunggu review" akan ditandai "Selesai direview".`, confirmText: "Tandai selesai" }))
            act(() => api.markReviewed(batchId), "Semua video ditandai selesai direview"); }}>Tandai semua selesai review</button>}
        <button className="btn" disabled={!st.completed} onClick={buildFinals} title="Satu video hasil untuk setiap video sumber">Buat Video Hasil</button>
        <button className="btn" onClick={exportAll}>Ekspor Semua</button>
        <ZipButton key={`zip-${batch.status}-${st.completed}`} batchId={batchId} />
        <button className="btn btn-ghost" onClick={() => run(() => api.openFolder(null))}>Buka Folder Output</button>
        <button className="btn btn-ghost" onClick={showReport}>Laporan</button>
        <span className="sep" />
        <button className="btn btn-danger-ghost" onClick={() => setDelOpen(true)}>Hapus batch</button>
      </div>
      {delOpen && <DeleteBatchModal batch={batch} onClose={() => setDelOpen(false)} onDeleted={() => navigate("/batches")} />}

      <div className="stats">
        <Stat label="Jumlah video" value={`${st.total} / ${MAX}`} />
        <Stat label="Selesai" value={st.completed} tone="ok" />
        <Stat label="Sedang diproses" value={st.processing} />
        <Stat label="Menunggu" value={st.waiting} />
        <Stat label="Gagal" value={st.failed} tone={st.failed ? "err" : undefined} />
        <Stat label="Estimasi selesai" value={st.eta_seconds != null ? fmtDur(st.eta_seconds) : "–"} />
      </div>
      <Card>
        <ProgressBar value={st.progress} label={`Progres keseluruhan ${Math.round(st.progress * 100)}%`} />
        <div className="settings-row">
          <Field label="Durasi tiap video hasil">
            <DurationSlider disabled={!editable} value={batch.final_duration} onChange={(v) => act(() => api.updateBatch(batchId, { final_duration: v }), `Durasi tiap video hasil: ${v} detik`)} />
          </Field>
          <Field label="Mode perjalanan">
            <Segmented disabled={!editable} value={batch.trip_mode} onChange={(v) => act(() => api.updateBatch(batchId, { trip_mode: v }))}
              options={[{ value: "outbound", label: "Pergi saja" }, { value: "round_trip", label: "Pergi & kembali" }]} />
          </Field>
          <Field label="Proses bersamaan">
            <Segmented disabled={!editable} value={batch.concurrency} onChange={(v) => act(() => api.updateBatch(batchId, { concurrency: v }))}
              options={[1, 2, 4].map((c) => ({ value: c, label: String(c) }))} />
          </Field>
          <Field label="Informasi cadangan">
            <Segmented value={batch.metadata_mode} onChange={(v) => act(() => api.updateBatch(batchId, { metadata_mode: v }))}
              options={[{ value: "shared", label: "Dari kelompok lokasi" }, { value: "per_final", label: "Manual per video" }]} />
          </Field>
          <div className="small muted">{st.total} video sumber → {st.total} video hasil × {batch.final_duration} dtk · {tripLabel(batch.trip_mode)}</div>
        </div>
      </Card>

      {files.length > 0 && <PendingFiles files={files} setFiles={setFiles} existing={items.length} onUpload={upload} busy={busy} progress={upProg} />}

      <Card title="Daftar video">
        {items.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>No.</th><th>Nama Video</th><th>Informasi video</th><th>Ukuran</th><th>Durasi</th><th>Resolusi</th>
                <th style={{ minWidth: 170 }}>Status Analisis</th><th>Kandidat</th><th>Status</th><th>Kelompok</th><th>Titik</th><th /></tr></thead>
              <tbody>
                {items.map((x, i) => (
                  <tr key={x.id}>
                    <td className="nowrap">{i + 1}
                      {editable && <span className="mini-btns"><button onClick={() => move(i, -1)} title="Naik">▲</button><button onClick={() => move(i, 1)} title="Turun">▼</button></span>}</td>
                    <td className="vname"><strong className="wrap-any">{x.filename}</strong>{!x.is_uploaded && <div className="small muted">path lokal (tidak disalin)</div>}
                      {(x.error || x.probe_error) && <div className="small text-err err-clamp" title={x.error || x.probe_error}>{x.error || x.probe_error}</div>}</td>
                    <td className="info-cell">
                      {x.template_code && <span className="badge badge-info">{tmplName(x.template_code)}</span>}{" "}
                      <InfoSummary fields={x} />
                      <div className="row info-src">
                        <span className="muted">{x.source_meta?._source === "filename" ? "dari nama file" : x.source_origin === "downloader" ? "dari Downloader" : "manual"}</span>
                        <button className="btn btn-sm btn-ghost" onClick={() => setInfoVideo(x)}>Ubah</button>
                      </div>
                    </td>
                    <td className="nowrap">{fmtBytes(x.size_bytes)}</td>
                    <td className="nowrap">{x.duration ? fmtSec(x.duration) : "–"}</td>
                    <td className="nowrap">{x.width ? `${x.width}×${x.height}` : "–"}<div className="small muted">{x.fps ? `${x.fps.toFixed(2)} fps` : ""}</div></td>
                    <td><ProgressBar small value={x.progress} tone={x.status === "failed" ? "err" : "info"} /><div className="small muted">{x.stage || "–"}</div></td>
                    <td className="center">{x.candidate_count}</td>
                    <td><StatusBadge status={x.status} label={x.status_label} /></td>
                    <td>
                      <select value={x.location_group_id || ""} onChange={(e) => act(() => api.updateVideo(x.video_id, { location_group_id: Number(e.target.value) }))}>
                        {batch.groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                      </select>
                    </td>
                    <td><button className="btn btn-sm btn-ghost" onClick={() => setMapVideo({ ...x, id: x.video_id, point_mapping: x.point_mapping })}>
                      {x.point_mapping && x.point_mapping.length ? x.point_mapping.join("→") : "Otomatis"}</button></td>
                    <td className="nowrap">
                      <button className="btn btn-sm" disabled={!["review", "done"].includes(x.status)} onClick={() => navigate(`/review/${batchId}?video=${x.video_id}`)}>Buka</button>
                      {x.final_video_id && <button className="btn btn-sm btn-ghost" onClick={() => navigate(`/review/${batchId}?final=${x.final_video_id}`)}>Hasil</button>}
                      <button className="btn btn-sm btn-ghost" disabled={["analyzing", "processing", "analyzed"].includes(x.status)} onClick={() => act(() => api.analyze(x.video_id), "Analisis ulang dijadwalkan")}>Analisis</button>
                      <button className="btn btn-sm btn-ghost" disabled={!editable || ["analyzing", "processing"].includes(x.status)} onClick={async () => {
                        if (await confirm({ title: "Hapus video dari batch?", message: `${x.filename} akan dihapus dari batch beserta kandidatnya. File sumber asli tidak dihapus.`, danger: true, confirmText: "Hapus" }))
                          act(() => api.removeVideo(batchId, x.video_id), "Video dihapus dari batch");
                      }}>Hapus</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty>Belum ada video. Klik “Impor dari Downloader” untuk memakai video hasil unduhan beserta informasinya,
          atau “Tambah Video” untuk memilih file (maks. {MAX}).</Empty>}
      </Card>

      <div className="stack">
        <Card title="Kelompok lokasi" actions={<button className="btn btn-sm" onClick={() => act(() => api.createGroup({ batch_id: batchId, name: `Lokasi ${batch.groups.length + 1}` }), "Kelompok ditambahkan")}>Tambah kelompok</button>}>
          <p className="small muted">Setiap video sumber menghasilkan satu video hasil {batch.final_duration} detik; video tidak digabung.
            Kelompok lokasi hanya menjadi <b>informasi cadangan</b> bagi video yang belum memiliki lokasi/tanggal/waktu/lalin sendiri.</p>
          <div className="table-wrap">
            <table className="table table-compact">
              <thead><tr><th>Kelompok</th><th>Nama lokasi</th><th>Kondisi lalin</th><th>Tanggal</th><th>Waktu</th><th>Video</th><th /></tr></thead>
              <tbody>
                {batch.groups.map((g) => <GroupRow key={`${g.id}-${g.location_name}-${g.traffic_condition}-${g.event_date}-${g.event_time}-${g.name}`} g={g} canDelete={batch.groups.length > 1}
                  onSave={(id, f) => act(() => api.updateGroup(id, f), "Kelompok disimpan")}
                  onDelete={(id) => act(() => api.deleteGroup(id), "Kelompok dihapus")} />)}
              </tbody>
            </table>
          </div>
          <p className="small muted">Tanggal/waktu kosong → memakai metadata waktu video jika tersedia dan dapat dipercaya.</p>
        </Card>
        <Card title="Konfigurasi lintasan">
          <RouteEditor key={JSON.stringify(batch.route_resolved)} batch={batch} disabled={!editable}
            onSave={(route) => act(() => api.updateBatch(batchId, { route }), "Lintasan disimpan")} />
        </Card>
      </div>

      <Modal open={pathsOpen} title="Tambah video dari path lokal" onClose={() => setPathsOpen(false)} footer={<>
        <button className="btn" onClick={() => setPathsOpen(false)}>Batal</button>
        <button className="btn btn-primary" onClick={addPaths}>Tambahkan</button>
      </>}>
        <p className="small muted">Satu path per baris, mis. <span className="mono">D:\Drone\DJI_0001.MP4</span>. File tidak disalin dan tidak diubah.</p>
        <textarea rows={8} className="mono" value={pathsText} onChange={(e) => setPathsText(e.target.value)} />
      </Modal>
      {infoVideo && <VideoInfoModal video={infoVideo} templates={tmpls.data} onClose={() => setInfoVideo(null)}
        onSave={async (v) => { await act(() => api.updateVideo(infoVideo.video_id, v), "Informasi video disimpan"); setInfoVideo(null); }} />}
      <ImportDownloadsModal open={importOpen} existing={items.length} onClose={() => setImportOpen(false)} onSubmit={doImport} />
      {mapVideo && <MappingModal video={mapVideo}
        template={(tmpls.data || []).find((t) => t.code === mapVideo.template_code) || tmpl.data} onClose={() => setMapVideo(null)}
        onSave={async (v) => { await act(() => api.updateVideo(mapVideo.id, v), "Pemetaan disimpan — jalankan Analisis ulang"); setMapVideo(null); }} />}
      <Modal open={!!report} wide title="Laporan hasil batch" onClose={() => setReport(null)}
        footer={<button className="btn" onClick={() => {
          const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
          const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `laporan_batch_${batchId}.json`; a.click();
        }}>Unduh JSON</button>}>
        {report && <div>
          <div className="stats">
            <Stat label="Total video" value={report.stats.total} /><Stat label="Selesai" value={report.stats.completed} tone="ok" />
            <Stat label="Gagal" value={report.stats.failed} tone={report.stats.failed ? "err" : undefined} />
            <Stat label="Video hasil" value={report.final_videos.length} /><Stat label="Ekspor berhasil" value={report.exports_succeeded.length} tone="ok" />
            <Stat label="Ekspor gagal" value={report.exports_failed.length} tone={report.exports_failed.length ? "err" : undefined} />
          </div>
          <h4>Video</h4>
          <table className="table table-compact"><thead><tr><th>No.</th><th>Nama</th><th>Durasi</th><th>Status</th><th>Kandidat</th><th>Keterangan</th></tr></thead>
            <tbody>{report.videos.map((v) => <tr key={v.no}><td>{v.no}</td><td>{v.filename}</td><td>{fmtSec(v.duration)}</td><td>{v.status}</td><td>{v.candidates}</td><td className="small text-err">{v.error}</td></tr>)}</tbody></table>
          <h4>File diekspor</h4>
          {report.exports_succeeded.length ? <ul className="mono small">{report.exports_succeeded.map((e) => <li key={e.export_id}>{e.file}</li>)}</ul> : <p className="muted small">Belum ada.</p>}
          {report.exports_failed.length > 0 && <><h4>Ekspor gagal</h4><ul className="small text-err">{report.exports_failed.map((e) => <li key={e.export_id}>#{e.final_video_id}: {e.error}</li>)}</ul></>}
        </div>}
      </Modal>
    </div>
  );
}

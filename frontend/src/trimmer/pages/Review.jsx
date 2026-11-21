import { useEffect, useMemo, useRef, useState } from "react";
import ScoreChart from "../components/ScoreChart.jsx";
import Timeline from "../components/Timeline.jsx";
import VideoPlayer from "../components/VideoPlayer.jsx";
import { Card, Empty, ErrorBox, Field, Loading, Modal, Notice, ProgressBar, Segmented, StatusBadge, Tag,
  useAction, useConfirm } from "../components/ui.jsx";
import { navigate, useLoad, usePolling } from "../hooks/useApi.js";
import { api, dirLabel, fmtSec, parseTime } from "../services/api.js";
import DurationSlider from "../components/DurationSlider.jsx";
import SegmentSelector from "../components/SegmentSelector.jsx";

const TRAFFIC = ["Lancar", "Ramai Lancar", "Ramai", "Padat", "Padat Merayap", "Macet", "Tidak Teridentifikasi"];

// ====================================================================== pemilih batch
function BatchPicker() {
  const { data, loading } = useLoad(() => api.batches(), []);
  if (loading && !data) return <Loading />;
  const list = (data || []).filter((b) => b.stats.completed > 0);
  return (
    <div className="page">
      <header className="page-head"><div><h1>Review dan Editing</h1><p className="muted">Pilih batch yang sudah memiliki hasil analisis.</p></div></header>
      <Card>{list.length ? (
        <table className="table"><thead><tr><th>Batch</th><th>Proyek</th><th>Template</th><th>Siap review</th><th>Status</th></tr></thead>
          <tbody>{list.map((b) => (
            <tr key={b.id} className="clickable" onClick={() => navigate(`/review/${b.id}`)}>
              <td><strong>{b.name}</strong></td><td>{b.project_name}</td><td>{b.template_name}</td>
              <td>{b.stats.completed} / {b.stats.total}</td><td><StatusBadge status={b.status} label={b.status_label} /></td></tr>))}
          </tbody></table>) : <Empty>Belum ada batch dengan hasil analisis.</Empty>}
      </Card>
    </div>
  );
}

// ====================================================================== baris kandidat
function CandidateRow({ c, idx, points, playerRef, onChanged, finalId, run, confirm, selected, onSelect }) {
  const [f, setF] = useState({ start: c.start.toFixed(2), end: c.end.toFixed(2), point_code: c.point_code, direction: c.direction });
  useEffect(() => setF({ start: c.start.toFixed(2), end: c.end.toFixed(2), point_code: c.point_code, direction: c.direction }), [c]);
  const dirty = Number(f.start) !== Number(c.start.toFixed(2)) || Number(f.end) !== Number(c.end.toFixed(2))
    || f.point_code !== c.point_code || f.direction !== c.direction;
  const save = () => run(() => api.updateCandidate(c.id, { start: parseTime(f.start), end: parseTime(f.end), point_code: f.point_code, direction: f.direction }), "Kandidat dikoreksi").then(onChanged);
  const status = c.verified ? <Tag tone="ok">Terverifikasi</Tag> : c.edited ? <Tag tone="warn">Dikoreksi</Tag>
    : c.origin === "operator" ? <Tag tone="ok">Operator</Tag> : <Tag tone="muted" title="Perlu verifikasi operator">AI · perlu verifikasi</Tag>;
  return (
    <tr className={`${c.edited ? "row-edited" : ""} ${c.direction === "return" ? "row-ret" : ""} ${selected ? "row-sel" : ""}`} title={c.reason || ""}>
      <td>{idx + 1}{c.is_turnaround ? <span title="Mengandung putar balik"> ↻</span> : null}</td>
      <td><select value={f.point_code} onChange={(e) => setF({ ...f, point_code: e.target.value })}>
        {points.map((p) => <option key={p.code} value={p.code}>{p.code} · {p.name}</option>)}</select></td>
      <td><select value={f.direction} onChange={(e) => setF({ ...f, direction: e.target.value })}>
        <option value="outbound">Pergi</option><option value="return">Kembali</option></select></td>
      <td><div className="time-input"><input className="mono" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} />
        <button title="Ambil posisi pemutar" onClick={() => setF({ ...f, start: playerRef.current.currentTime().toFixed(2) })}>⌖</button></div></td>
      <td><div className="time-input"><input className="mono" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} />
        <button title="Ambil posisi pemutar" onClick={() => setF({ ...f, end: playerRef.current.currentTime().toFixed(2) })}>⌖</button></div></td>
      <td className="mono">{(parseTime(f.end) - parseTime(f.start)).toFixed(1)}s</td>
      <td className="mono">{c.quality_score != null ? c.quality_score.toFixed(2) : "–"}</td>
      <td className="mono">{c.relevance_score != null ? c.relevance_score.toFixed(2) : "–"}</td>
      <td className="mono" title="Keyakinan label titik (estimasi temporal)">{c.confidence != null ? `${Math.round(c.confidence * 100)}%` : "–"}</td>
      <td className="small">{c.traffic_suggestion ? <span title="Saran AI, belum tervalidasi">{c.traffic_suggestion}*</span> : "–"}</td>
      <td>{status}</td>
      <td className="nowrap">
        <button className="btn btn-sm" title="Putar segmen" onClick={() => playerRef.current.playRange(parseTime(f.start), parseTime(f.end))}>▶</button>
        <button className={`btn btn-sm ${selected ? "btn-primary" : ""}`} title="Atur awal & akhir langsung di video (pemilih segmen)" onClick={() => onSelect(c)}>⇔ Pilih di video</button>
        {dirty && <button className="btn btn-sm btn-primary" onClick={save}>Simpan</button>}
        {!c.verified && !dirty && <button className="btn btn-sm" onClick={() => run(() => api.updateCandidate(c.id, { verified: true }), "Diverifikasi").then(onChanged)}>Verifikasi</button>}
        {c.ai_start != null && c.edited ? <button className="btn btn-sm btn-ghost" title="Kembalikan ke hasil AI" onClick={() => run(() => api.resetCandidate(c.id), "Dikembalikan ke hasil AI").then(onChanged)}>Reset AI</button> : null}
        {finalId && <button className="btn btn-sm btn-ghost" title="Tambahkan ke video hasil" onClick={() => run(() => api.addSegment(finalId, { candidate_id: c.id }), "Ditambahkan ke timeline").then(onChanged)}>+ Final</button>}
        <button className="btn btn-sm btn-ghost" onClick={async () => {
          if (!(await confirm({ title: "Hapus kandidat?", message: "Kandidat ditandai ditolak (disimpan sebagai data koreksi). Bila dipakai di video hasil, potongannya ikut dihapus sehingga durasi video hasil berkurang.", danger: true, confirmText: "Hapus" }))) return;
          const r = await run(() => api.deleteCandidate(c.id));
          if (r) {
            const fx = (r.removed_from_finals || [])[0];
            run(async () => true, fx ? `Kandidat dihapus · durasi video hasil kini ${fx.duration.total} / ${fx.duration.target} dtk` : "Kandidat dihapus");
            onChanged();
          }
        }}>✕</button>
      </td>
    </tr>
  );
}

/** Status review video: otomatis "Selesai direview" bila semua kandidat terverifikasi, atau ditandai manual. */
function ReviewStatusBar({ v, cands, run, onChanged }) {
  const item = v?.item;
  if (!item || !["review", "done"].includes(item.status)) return null;
  const unverified = cands.filter((c) => !c.verified).length;
  const done = item.status === "done";
  return (
    <div className={`notice ${done ? "notice-ok" : "notice-info"} review-status`}>
      <div>
        <b>Status: {item.status_label}</b>
        <div className="small">{done ? "Video ini sudah direview."
          : unverified ? `${unverified} dari ${cands.length} kandidat belum diverifikasi. Status otomatis menjadi "Selesai direview" bila semua kandidat terverifikasi (atau kandidat yang salah dihapus).`
          : "Semua kandidat sudah diverifikasi."}</div>
      </div>
      <div className="row">
        {!done && unverified > 0 && <button className="btn btn-sm" onClick={() =>
          run(() => api.verifyAll(v.id), "Semua kandidat diverifikasi").then(onChanged)}>✓ Verifikasi Semua</button>}
        {done
          ? <button className="btn btn-sm btn-ghost" onClick={() => run(() => api.setReviewed(v.id, false), "Status dikembalikan ke Menunggu review").then(onChanged)}>Batalkan status selesai</button>
          : <button className="btn btn-sm btn-primary" onClick={() => run(() => api.setReviewed(v.id, true), "Video ditandai selesai direview").then(onChanged)}>Tandai selesai direview</button>}
      </div>
    </div>
  );
}

/** Verifikasi Semua untuk seluruh video batch: semua kandidat AI diterima, video -> "Selesai direview". */
function VerifyAllBatchButton({ batch, items, onDone }) {
  const [run, busy] = useAction();
  const confirm = useConfirm();
  const pending = items.filter((x) => x.status === "review").length;
  if (!pending) return null;
  return (
    <button className="btn btn-primary" disabled={busy} title="Terima semua kandidat AI di seluruh video batch ini" onClick={async () => {
      if (!(await confirm({ title: "Verifikasi semua video?", message: `Semua kandidat AI pada ${pending} video berstatus "Menunggu review" akan diterima sebagai terverifikasi, dan video ditandai "Selesai direview".`, confirmText: "Verifikasi Semua" }))) return;
      const r = await run(() => api.verifyAllBatch(batch.id));
      if (r) { run(async () => true, `${r.verified} kandidat diverifikasi pada ${r.videos} video`); onDone(); }
    }}>✓ Verifikasi Semua ({pending} video)</button>
  );
}

// ====================================================================== tab kandidat
function CandidatesTab({ batch, items, template, videoId, setVideoId, finalId }) {
  const playerRef = useRef(null);
  const vid = useLoad(async () => (videoId ? api.video(videoId) : null), [videoId]);
  const cands = useLoad(async () => (videoId ? api.candidates(videoId) : []), [videoId]);
  const [run] = useAction();
  const confirm = useConfirm();
  const [add, setAdd] = useState({ start: "", end: "", point_code: "", direction: "outbound" });
  const points = template?.points || [];
  const v = vid.data;
  const res = v?.analysis?.result;
  const reload = () => { cands.reload(); vid.reload(); };
  useEffect(() => {
    const on = () => { cands.reload(); vid.reload(); };
    window.addEventListener("dvp:reload", on);
    return () => window.removeEventListener("dvp:reload", on);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [sel, setSel] = useState({ start: 0, end: 5, candId: null });
  useEffect(() => { setSel({ start: 0, end: Math.min(5, v?.duration || 5), candId: null }); }, [videoId, v?.duration]);
  const selCand = (cands.data || []).find((c) => c.id === sel.candId);
  const selIndex = (cands.data || []).findIndex((c) => c.id === sel.candId);
  const pickCandidate = (c) => {
    if (sel.candId === c.id) { setSel({ ...sel, candId: null }); return; }
    setSel({ start: c.start, end: c.end, candId: c.id });
    playerRef.current?.seek(c.start);
  };
  const verifyAll = async () => {
    const r = await run(() => api.verifyAll(videoId));
    if (r) { run(async () => true, r.verified ? `${r.verified} kandidat diverifikasi · video selesai direview` : "Semua kandidat sudah terverifikasi"); reload(); }
  };
  const ready = items.filter((x) => ["review", "done"].includes(x.status));
  return (
    <div className="review-grid">
      <aside className="review-list">
        <h4>Video ({ready.length}/{items.length})</h4>
        {items.map((x) => (
          <button key={x.id} disabled={!["review", "done"].includes(x.status)} className={`list-item ${x.video_id === videoId ? "active" : ""}`}
            onClick={() => setVideoId(x.video_id)}>
            <div className="wrap-any"><strong>{x.filename}</strong></div>
            <div className="small muted">{fmtSec(x.duration)} · {x.candidate_count} kandidat</div>
            <StatusBadge status={x.status} label={x.status_label} />
          </button>
        ))}
      </aside>
      <div className="review-main">
        {!videoId ? <Card><Empty>Pilih video di sebelah kiri.</Empty></Card> : vid.loading && !v ? <Loading /> : v && (
          <>
            {res?.is_heuristic !== false && <Notice tone="warn" title="Hasil analisis masih berupa kandidat awal">
              {res?.point_identification === "manual" ? "Titik berasal dari pemetaan manual operator." :
                "Titik pemantauan diestimasi dari urutan temporal template (tanpa GPS dan belum ada model titik terlatih). "}
              {res?.is_heuristic ? " Deteksi objek belum aktif (tidak ada model) — skor aktivitas memakai heuristik gerak. " : ""}
              Verifikasi atau koreksi setiap kandidat; koreksi disimpan sebagai data pelatihan.
            </Notice>}
            <Card title={v.filename} actions={<span className="small muted">{v.width}×{v.height} · {v.fps?.toFixed(2)} fps · {v.codec}{v.has_proxy ? " · preview proxy" : ""}</span>}>
              <VideoPlayer ref={playerRef} src={api.streamUrl(v.id)} duration={v.duration}
                markers={(cands.data || []).map((c) => ({ start: c.start, end: c.end, className: `mk-${c.direction} ${c.edited ? "mk-edited" : ""}`, title: `T${c.point_code} ${dirLabel(c.direction)}` }))} />
              <SegmentSelector duration={v.duration} value={sel} playerRef={playerRef}
                onChange={(x) => setSel({ ...sel, ...x })}
                markers={(cands.data || []).map((c) => ({ start: c.start, end: c.end, className: `mk-${c.direction} ${c.id === sel.candId ? "mk-active" : ""}`, title: `T${c.point_code} ${dirLabel(c.direction)}` }))}
                label={selCand ? `Mengatur kandidat #${selIndex + 1} (Titik ${selCand.point_code} · ${dirLabel(selCand.direction)})` : "Pilih segmen di video"}
                actions={selCand ? <>
                  <button className="btn btn-sm btn-primary" onClick={() => run(() => api.updateCandidate(selCand.id, { start: sel.start, end: sel.end }), `Kandidat #${selIndex + 1} diperbarui`).then(reload)}>Simpan ke kandidat #{selIndex + 1}</button>
                  <button className="btn btn-sm btn-ghost" onClick={() => setSel({ ...sel, candId: null })}>Selesai</button>
                </> : <button className="btn btn-sm" onClick={() => setAdd({ ...add, start: sel.start.toFixed(2), end: sel.end.toFixed(2) })}
                  title="Isi awal & akhir di form 'Tambah segmen manual'">Pakai untuk segmen manual ↓</button>} />
              {res && <>
                <ScoreChart curve={res.curve} zones={res.zones} events={res.events} duration={v.duration} />
                <div className="legend-line small muted"><span className="lg-q">— kualitas</span> <span className="lg-a">— aktivitas</span> <span>| putar balik</span> <span>pita atas: zona titik (biru pergi, ungu kembali)</span></div>
                <div className="analysis-info small">
                  <span>Detektor: <b>{res.detector === "none" ? "tidak ada (heuristik)" : res.detector}</b></span>
                  <span>Aktivitas: {res.activity_method}</span>
                  {res.turnaround?.time != null && <span>Putar balik: <b>{fmtSec(res.turnaround.time)}</b> (keyakinan {Math.round((res.turnaround.confidence || 0) * 100)}%{res.turnaround.motion_reversal ? ", arah gerak berbalik" : ""})</span>}
                  <span>Frame buram: {Math.round((res.blurry_fraction || 0) * 100)}%</span>
                  <span>Waktu analisis: {res.elapsed_sec}s · perangkat {v.analysis.device}</span>
                </div>
                {res.warnings?.length > 0 && <Notice tone="warn">{res.warnings.map((w, i) => <div key={i}>• {w}</div>)}</Notice>}
              </>}
              {v.analysis?.status === "failed" && <Notice tone="err">{v.analysis.error}</Notice>}
            </Card>
            <ReviewStatusBar v={v} cands={cands.data || []} run={run} onChanged={reload} />
            <Card title={`Kandidat segmen (${(cands.data || []).length})`} actions={<>
              <span className="small muted">Template {template?.name} · waktu dalam detik</span>
              <button className="btn btn-sm btn-primary" disabled={!(cands.data || []).some((c) => !c.verified)} onClick={verifyAll}
                title="Terima semua kandidat AI video ini sebagai terverifikasi">✓ Verifikasi Semua</button>
            </>}>
              <div className="table-wrap">
                <table className="table table-compact">
                  <thead><tr><th>#</th><th>Titik</th><th>Arah</th><th>Awal</th><th>Akhir</th><th>Durasi</th><th>Kualitas</th><th>Relevansi</th><th>Keyakinan</th><th>Saran lalin</th><th>Verifikasi</th><th /></tr></thead>
                  <tbody>{(cands.data || []).map((c, i) => <CandidateRow key={c.id} c={c} idx={i} points={points} playerRef={playerRef}
                    onChanged={reload} finalId={finalId} run={run} confirm={confirm}
                    selected={c.id === sel.candId} onSelect={pickCandidate} />)}</tbody>
                </table>
              </div>
              {(cands.data || []).length > 0 && <p className="small muted">Arahkan kursor ke baris untuk melihat alasan pemilihan. * Saran lalu lintas AI belum tervalidasi.</p>}
              <div className="add-row">
                <strong className="small">Tambah segmen manual:</strong>
                <div className="time-input"><input placeholder="awal" className="mono" value={add.start} onChange={(e) => setAdd({ ...add, start: e.target.value })} />
                  <button onClick={() => setAdd({ ...add, start: playerRef.current.currentTime().toFixed(2) })}>⌖</button></div>
                <div className="time-input"><input placeholder="akhir" className="mono" value={add.end} onChange={(e) => setAdd({ ...add, end: e.target.value })} />
                  <button onClick={() => setAdd({ ...add, end: playerRef.current.currentTime().toFixed(2) })}>⌖</button></div>
                <select value={add.point_code} onChange={(e) => setAdd({ ...add, point_code: e.target.value })}>
                  <option value="">titik…</option>{points.map((p) => <option key={p.code} value={p.code}>{p.code} · {p.name}</option>)}</select>
                <select value={add.direction} onChange={(e) => setAdd({ ...add, direction: e.target.value })}>
                  <option value="outbound">Pergi</option><option value="return">Kembali</option></select>
                <button className="btn btn-sm btn-primary" disabled={!add.point_code || add.start === "" || add.end === ""} onClick={() =>
                  run(() => api.addCandidate(v.id, { start: parseTime(add.start), end: parseTime(add.end), point_code: add.point_code, direction: add.direction }), "Segmen ditambahkan")
                    .then((r) => { if (r) { setAdd({ ...add, start: "", end: "" }); reload(); } })}>Tambah</button>
              </div>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

// ====================================================================== tab video final
function SegmentEditor({ seg, final, playerRef, run, onChanged, points, confirm, index, count, onMove }) {
  const [f, setF] = useState({});
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [pool, setPool] = useState([]);
  useEffect(() => setF({ start: seg.start.toFixed(2), end: seg.end.toFixed(2), allocated: seg.duration.toFixed(1), point_code: seg.point_code, direction: seg.direction, role: seg.role }), [seg]);
  const save = (body) => run(() => api.updateSegment(final.id, seg.id, body), "Segmen diperbarui").then(onChanged);
  const openReplace = async () => {
    const lists = await Promise.all([...new Set(final.segments.map((s) => s.video_id))].map((vid) => api.candidates(vid).then((cs) => cs.map((c) => ({ ...c })))));
    setPool(lists.flat().filter((c) => c.point_code === seg.point_code && c.id !== seg.candidate_id));
    setReplaceOpen(true);
  };
  return (
    <Card title={`Segmen #${index + 1} — ${seg.point_code ? `Titik ${seg.point_code} · ${dirLabel(seg.direction)}` : "Potongan pengisi"}`}
      actions={<span className="small muted">{seg.video_filename} {seg.edited ? <Tag tone="warn">dikoreksi operator</Tag> : <Tag tone="info">hasil AI</Tag>}</span>}>
      <div className="seg-editor">
        <Field label="Awal (dtk)"><div className="time-input"><input className="mono" value={f.start || ""} onChange={(e) => setF({ ...f, start: e.target.value })} />
          <button onClick={() => setF({ ...f, start: playerRef.current.currentTime().toFixed(2) })}>⌖</button></div></Field>
        <Field label="Akhir (dtk)"><div className="time-input"><input className="mono" value={f.end || ""} onChange={(e) => setF({ ...f, end: e.target.value })} />
          <button onClick={() => setF({ ...f, end: playerRef.current.currentTime().toFixed(2) })}>⌖</button></div></Field>
        <Field label="Alokasi durasi (dtk)"><input className="mono" value={f.allocated || ""} onChange={(e) => setF({ ...f, allocated: e.target.value })} /></Field>
        <Field label="Titik"><select value={f.point_code || ""} onChange={(e) => setF({ ...f, point_code: e.target.value })}>
          {points.map((p) => <option key={p.code} value={p.code}>{p.code} · {p.name}</option>)}</select></Field>
        <Field label="Arah"><select value={f.direction || ""} onChange={(e) => setF({ ...f, direction: e.target.value })}>
          <option value="outbound">Pergi</option><option value="return">Kembali</option></select></Field>
        <Field label="Peran"><select value={f.role || "point"} onChange={(e) => setF({ ...f, role: e.target.value })}>
          <option value="point">Titik utama</option><option value="support">Momen pendukung</option></select></Field>
      </div>
      <div className="row wrap">
        <button className="btn btn-sm" onClick={() => playerRef.current.playRange(parseTime(f.start), parseTime(f.end))}>▶ Putar segmen</button>
        <button className="btn btn-sm btn-primary" onClick={() => save({ start: parseTime(f.start), end: parseTime(f.end), point_code: f.point_code, direction: f.direction, role: f.role })}>Simpan timestamp</button>
        <button className="btn btn-sm" onClick={() => save({ start: parseTime(f.start), allocated: Number(f.allocated) })}>Terapkan alokasi</button>
        <button className="btn btn-sm" disabled={index === 0} onClick={() => onMove(-1)}>◀ Geser</button>
        <button className="btn btn-sm" disabled={index === count - 1} onClick={() => onMove(1)}>Geser ▶</button>
        <button className="btn btn-sm" onClick={openReplace}>Ganti footage</button>
        {seg.ai_start != null && <button className="btn btn-sm btn-ghost" onClick={() => run(() => api.resetSegment(final.id, seg.id), "Dikembalikan ke hasil AI").then(onChanged)}>Reset ke AI</button>}
        <button className="btn btn-sm btn-danger" onClick={async () => {
          if (await confirm({ title: "Hapus segmen dari timeline?", message: "Segmen dihapus dari video final (kandidat tetap tersedia).", danger: true, confirmText: "Hapus" }))
            run(() => api.deleteSegment(final.id, seg.id), "Segmen dihapus").then(onChanged);
        }}>Hapus</button>
      </div>
      <Modal open={replaceOpen} wide title={`Ganti footage titik ${seg.point_code}`} onClose={() => setReplaceOpen(false)}>
        {pool.length ? <table className="table table-compact"><thead><tr><th>Video</th><th>Arah</th><th>Awal</th><th>Akhir</th><th>Kualitas</th><th>Relevansi</th><th /></tr></thead>
          <tbody>{pool.map((c) => <tr key={c.id}><td>#{c.video_id}</td><td>{dirLabel(c.direction)}</td><td className="mono">{fmtSec(c.start)}</td><td className="mono">{fmtSec(c.end)}</td>
            <td>{c.quality_score?.toFixed(2) ?? "–"}</td><td>{c.relevance_score?.toFixed(2) ?? "–"}</td>
            <td><button className="btn btn-sm btn-primary" onClick={() => { setReplaceOpen(false); run(() => api.replaceSegment(final.id, seg.id, c.id), "Footage diganti").then(onChanged); }}>Pakai</button></td></tr>)}</tbody></table>
          : <Empty>Tidak ada kandidat lain untuk titik ini dalam video sumber.</Empty>}
      </Modal>
    </Card>
  );
}

function MetadataForm({ final, run, onChanged }) {
  const init = () => ({ location_name: final.location_name || "", traffic_condition: final.traffic_condition || "Tidak Teridentifikasi",
    event_date: final.event_date || "", event_time: final.event_time || "", custom_filename: final.custom_filename || "" });
  const [f, setF] = useState(init);
  useEffect(() => setF(init()), [final.id, final.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Card title="Metadata & nama file output">
      <div className="form">
        <div className="grid-2">
          <Field label="Nama lokasi"><input value={f.location_name} onChange={(e) => setF({ ...f, location_name: e.target.value })} /></Field>
          <Field label="Kondisi lalu lintas" hint="Default “Tidak Teridentifikasi”. Saran AI hanya ditampilkan bila model tersedia dan belum tervalidasi.">
            <select value={TRAFFIC.includes(f.traffic_condition) ? f.traffic_condition : "__manual"} onChange={(e) => setF({ ...f, traffic_condition: e.target.value === "__manual" ? "" : e.target.value })}>
              {TRAFFIC.map((t) => <option key={t}>{t}</option>)}<option value="__manual">Isi manual…</option></select>
            {!TRAFFIC.includes(f.traffic_condition) && <input placeholder="Kondisi lalin manual" value={f.traffic_condition} onChange={(e) => setF({ ...f, traffic_condition: e.target.value })} />}
          </Field>
          <Field label="Tanggal kejadian" hint={`Sumber waktu saat ini: ${final.time_source_resolved === "operator" ? "input operator" : final.time_source_resolved === "metadata" ? "metadata video" : "tidak tersedia — isi manual"}`}>
            <input type="date" value={f.event_date} onChange={(e) => setF({ ...f, event_date: e.target.value })} /></Field>
          <Field label="Waktu kejadian (24 jam)"><input type="time" value={f.event_time} onChange={(e) => setF({ ...f, event_time: e.target.value })} /></Field>
        </div>
        <Field label="Nama file standar"><div className="mono filename">{final.suggested_filename || <span className="text-err">{final.filename_error}</span>}</div></Field>
        <Field label="Nama file kustom (opsional)" hint="Harus tetap berformat Clipped_DD.MM_HH.MM_NamaLokasi_KondisiLalin.mp4">
          <input className="mono" placeholder={final.suggested_filename || ""} value={f.custom_filename} onChange={(e) => setF({ ...f, custom_filename: e.target.value })} /></Field>
        <div className="row"><button className="btn btn-primary btn-sm" onClick={() => run(() => api.updateFinal(final.id, f), "Metadata disimpan").then(onChanged)}>Simpan metadata</button>
          <span className="small muted">Akan diekspor sebagai: <b className="mono">{final.output_filename || "–"}</b></span></div>
      </div>
    </Card>
  );
}

const fmtBytes = (b) => (b == null ? "–" : b >= 1e9 ? `${(b / 1e9).toFixed(2)} GB` : `${(b / 1e6).toFixed(1)} MB`);
const fmtRes = (w, h) => (w && h ? `${w} × ${h}` : "–");
const fmtFps = (f) => (f ? `${Number(f).toFixed(f % 1 ? 3 : 0).replace(/\.?0+$/, "")} fps` : "–");

function ExportInfo({ final }) {
  const sig = final.segments.map((s) => `${s.id}:${s.start}:${s.end}`).join("|");
  const info = useLoad(() => api.exportInfo(final.id), [final.id, sig]);
  const d = info.data;
  if (info.loading && !d) return <p className="small muted">Menghitung informasi ekspor…</p>;
  if (!d || !d.sources?.length) return null;
  const o = d.output;
  return (
    <div className="export-info">
      <table className="table table-compact">
        <thead><tr><th>Video sumber</th><th>Resolusi</th><th>Frame rate</th><th>Durasi</th><th>Codec</th><th>Bitrate</th></tr></thead>
        <tbody>{d.sources.map((v) => (
          <tr key={v.id}><td className="small wrap-any">{v.filename}</td><td className="mono">{fmtRes(v.width, v.height)}</td>
            <td className="mono">{fmtFps(v.fps)}</td><td className="mono">{fmtSec(v.duration)}</td>
            <td className="small">{v.codec || "–"}{v.audio_codec ? ` / ${v.audio_codec}` : ""}</td>
            <td className="mono">{v.bit_rate ? `${(v.bit_rate / 1e6).toFixed(1)} Mbps` : "–"}</td></tr>))}</tbody>
      </table>
      <dl className="kv">
        <dt>Hasil</dt><dd><b className="mono">{fmtRes(o.width, o.height)}</b> · <span className="mono">{fmtFps(o.fps)}</span> · durasi <span className="mono">{d.duration.toFixed(1)} dtk</span> ({d.segments} segmen)
          {o.keeps_source_resolution && o.keeps_source_fps ? <Tag tone="ok">resolusi & fps asli</Tag> : <Tag tone="warn">disesuaikan</Tag>}</dd>
        <dt>Mode</dt><dd>{d.mode === "copy" ? <><Tag tone="ok">Tanpa re-encode (stream copy)</Tag> kualitas identik dengan sumber</> : <Tag tone="info">Re-encode kualitas tinggi</Tag>}
          <div className="small muted">{d.mode_reason}</div></dd>
        {d.quality && <><dt>Encoding</dt><dd className="small">{d.quality.codec} · {d.quality.encoder} · CRF {d.quality.crf} · preset {d.quality.preset} · {d.quality.pix_fmt} · {d.quality.audio}</dd></>}
        <dt>Perkiraan ukuran</dt><dd className="mono">≈ {fmtBytes(d.estimated_size_bytes)}</dd>
      </dl>
    </div>
  );
}

function ExportsPanel({ final }) {
  if (!final.exports?.length) return null;
  return (
    <Card title="Ekspor video hasil ini">
      <table className="table table-compact"><thead><tr><th>#</th><th>Jenis</th><th>Status</th><th>Progres</th><th>Mode</th><th>Output</th><th /></tr></thead>
        <tbody>{final.exports.map((e) => (
          <tr key={e.id}><td>{e.id}</td><td>{{ final: "Video hasil", individual: "Potongan individual", preview: "Preview" }[e.kind]}</td>
            <td><StatusBadge status={e.status === "done" ? "done" : e.status === "failed" ? "failed" : "running"} label={e.status} /></td>
            <td style={{ width: 150 }}><ProgressBar small value={e.progress} label={e.status === "running" || e.status === "queued" ? `${Math.round((e.progress || 0) * 100)}%` : undefined} /></td>
            <td className="small">{e.mode || "–"} {e.encoder ? `(${e.encoder})` : ""}</td>
            <td className="mono small wrap-any">{e.error ? <span className="text-err">{e.error}</span> : e.output_path?.split(/[\\/]/).pop()}</td>
            <td className="nowrap">{e.status === "done" && e.kind === "final" && <a className="btn btn-sm" href={api.downloadUrl(e.id)}>Unduh</a>}
              {e.status === "done" && e.kind !== "preview" && <button className="btn btn-sm btn-ghost" onClick={() => api.openFolder(e.output_path)}>Folder</button>}</td></tr>
        ))}</tbody></table>
    </Card>
  );
}

function FinalTab({ batch, items, tmplOf, finalId, setFinalId }) {
  const finals = useLoad(() => api.batchFinals(batch.id), [batch.id]);
  const fin = useLoad(async () => (finalId ? api.final(finalId) : null), [finalId]);
  const [selSeg, setSelSeg] = useState(null);
  const [previewJob, setPreviewJob] = useState(null);
  const playerRef = useRef(null);
  const previewRef = useRef(null);
  const [run] = useAction();
  const confirm = useConfirm();
  const final = fin.data;
  const running = final?.exports?.some((e) => ["queued", "running"].includes(e.status));
  usePolling(fin.reload, 1500, !!running);
  usePolling(async () => {
    if (!previewJob || previewJob.status === "done" || previewJob.status === "failed") return;
    setPreviewJob(await api.exportJob(previewJob.id));
  }, 1000, !!previewJob);
  const template = tmplOf(final?.template_code);
  const points = template?.points || [];
  const seg = useMemo(() => final?.segments.find((s) => s.id === selSeg) || null, [final, selSeg]);
  const reloadAll = () => { fin.reload(); finals.reload(); };

  const createFor = async (x) => {
    const f = await run(() => api.createFinal({ project_id: batch.project_id, batch_id: batch.id, source_video_id: x.video_id,
      target_duration: batch.final_duration, trip_mode: batch.trip_mode }), `Video hasil untuk ${x.filename} disusun`);
    if (f) { finals.reload(); setFinalId(f.id); }
  };
  const buildAll = async () => {
    const r = await run(() => api.buildFinals(batch.id), "Video hasil disusun untuk setiap video sumber");
    if (r) { finals.reload(); if (!finalId && r.length) setFinalId(r[0].id); }
  };
  const byVideo = {};
  (finals.data || []).forEach((f) => { if (f.source_video_id && !byVideo[f.source_video_id]) byVideo[f.source_video_id] = f; });
  const legacy = (finals.data || []).filter((f) => !f.source_video_id);
  const move = (d) => {
    const ids = final.segments.map((s) => s.id);
    const i = ids.indexOf(seg.id), j = i + d;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    run(() => api.reorderSegments(final.id, ids), "Urutan diubah").then(fin.reload);
  };
  const ds = final?.duration_status;
  return (
    <div className="final-layout">
      <Card title={`Video hasil per video sumber (${Object.keys(byVideo).length}/${items.length})`}
        actions={<button className="btn btn-sm btn-primary" disabled={!items.length} onClick={buildAll}>Susun semua (1 hasil per video)</button>}>
        <p className="small muted" style={{ marginTop: 0 }}>Setiap video sumber menghasilkan satu video hasil berdurasi {batch.final_duration} detik
          (24 video masuk → 24 video hasil). Video tidak digabung satu sama lain.</p>
        <div className="chips">
          {items.map((x, i) => {
            const f = byVideo[x.video_id];
            return f ? (
              <button key={x.video_id} className={`chip ${finalId === f.id ? "chip-on" : ""}`} onClick={() => setFinalId(f.id)} title={x.filename}>
                {i + 1}. {f.location_name || x.location_name || x.filename} · {f.total_duration}/{f.target_duration}s <StatusBadge status={f.status} label={f.status} /></button>
            ) : <button key={x.video_id} className="chip" disabled={!x.duration} onClick={() => createFor(x)} title={x.filename}>+ {i + 1}. Susun hasil · {x.location_name || x.filename}</button>;
          })}
          {legacy.map((f) => (
            <button key={f.id} className={`chip ${finalId === f.id ? "chip-on" : ""}`} onClick={() => setFinalId(f.id)}>Gabungan (versi lama) · {f.location_name} · {f.total_duration}/{f.target_duration}s</button>
          ))}
        </div>
      </Card>
      {!finalId ? <Card><Empty>Pilih atau susun video hasil.</Empty></Card> : fin.loading && !final ? <Loading /> : final && (
        <>
          <Card title={`Timeline — ${final.location_name || "Lokasi"} (${final.target_duration} detik${final.cross_location ? ", lintas lokasi" : ""})${final.source_video ? ` · ${final.source_video.filename}` : ""}`}
            actions={<>
              <DurationSlider value={final.target_duration} onChange={(v) => run(() => api.updateFinal(final.id, { target_duration: v }).then(() => api.selectSegments(final.id)), `Target ${v} dtk, disusun ulang`).then(fin.reload)} />
              <button className="btn btn-sm" onClick={async () => { if (await confirm({ title: "Susun ulang otomatis?", message: "Timeline akan diganti dengan seleksi AI terbaru (koreksi kandidat tetap dipakai). Perubahan timeline manual akan hilang." })) run(() => api.selectSegments(final.id), "Disusun ulang").then(fin.reload); }}>Susun ulang (AI)</button>
            </>}>
            <div className={`duration-bar state-${ds.state}`}>
              <div><span className="big mono">{ds.total.toFixed(1)}</span> / {ds.target} dtk</div>
              <div>{ds.message}{ds.state === "under" && ` Sisa ${ds.remaining.toFixed(1)} dtk.`}</div>
              <div className="small">{final.metadata.jumlah_segmen} segmen · {final.metadata.jumlah_video_sumber} video sumber</div>
            </div>
            <Timeline segments={final.segments} target={final.target_duration} selectedId={selSeg}
              onSelect={(s) => { setSelSeg(s.id); }} onReorder={(ids) => run(() => api.reorderSegments(final.id, ids), "Urutan diubah").then(fin.reload)} />
            {final.warnings?.length > 0 && <Notice tone="warn">{final.warnings.map((w, i) => <div key={i}>• {w}</div>)}</Notice>}
            {ds.state === "under" && final.recommendations?.length > 0 && (
              <div className="recs"><strong className="small">Rekomendasi kandidat tambahan:</strong>
                {final.recommendations.map((r) => (
                  <button key={r.id} className="chip" onClick={() => run(() => api.addSegment(final.id, { candidate_id: r.id, end: Math.min(r.end, r.start + Math.max(1.5, ds.remaining)) }), "Ditambahkan").then(fin.reload)}>
                    + T{r.point_code} {dirLabel(r.direction)} · video #{r.video_id} · {fmtSec(r.start)}–{fmtSec(r.end)}</button>))}
              </div>)}
            {ds.state === "under" && <Notice tone="info">Video hasil lebih pendek dari target karena footage dikurangi — tetap dapat diproses dan diekspor.</Notice>}
            {ds.state === "over" && (
              <label className="check"><input type="checkbox" checked={!!final.approved_duration_mismatch}
                onChange={(e) => run(() => api.updateFinal(final.id, { approved_duration_mismatch: e.target.checked })).then(fin.reload)} />
                Saya menyetujui ekspor dengan durasi aktual {ds.total.toFixed(1)} dtk (target {ds.target} dtk).</label>)}
          </Card>
          <div className="grid-2">
            <div>
              <Card title="Preview">
                <VideoPlayer ref={playerRef} src={seg ? api.streamUrl(seg.video_id) : null} duration={seg?.video_duration}
                  markers={seg ? [{ start: seg.start, end: seg.end, className: `mk-${seg.direction}` }] : []} />
                {!seg && <p className="small muted">Klik blok timeline untuk memilih segmen dan memutar video sumbernya.</p>}
              </Card>
              <Card title="Preview video hasil (resolusi rendah)" actions={
                <button className="btn btn-sm" disabled={!final.segments.length || (previewJob && !["done", "failed"].includes(previewJob.status))}
                  onClick={async () => { const j = await run(() => api.previewFinal(final.id)); if (j) setPreviewJob(j); }}>Render preview</button>}>
                {previewJob && previewJob.status !== "done" && previewJob.status !== "failed" && <ProgressBar value={previewJob.progress} label={`Merender preview ${Math.round(previewJob.progress * 100)}%`} />}
                {previewJob?.status === "failed" && <Notice tone="err">{previewJob.error}</Notice>}
                {previewJob?.status === "done" && <VideoPlayer ref={previewRef} src={api.exportStreamUrl(previewJob.id)} duration={previewJob.duration} />}
              </Card>
            </div>
            <div>
              {seg ? <SegmentEditor key={seg.id} seg={seg} final={final} playerRef={playerRef} run={run} onChanged={fin.reload} points={points}
                confirm={confirm} index={final.segments.indexOf(seg)} count={final.segments.length} onMove={move} />
                : <Card title="Segmen"><Empty>Pilih segmen pada timeline untuk mengedit timestamp, alokasi durasi, urutan, atau mengganti footage.</Empty></Card>}
              <Card title="Daftar segmen">
                <table className="table table-compact"><thead><tr><th>#</th><th>Titik</th><th>Arah</th><th>Video</th><th>Awal</th><th>Akhir</th><th>Alokasi</th><th>Asal</th></tr></thead>
                  <tbody>{final.segments.map((s, i) => (
                    <tr key={s.id} className={`clickable ${selSeg === s.id ? "row-sel" : ""}`} onClick={() => setSelSeg(s.id)}>
                      <td>{i + 1}</td><td>{s.point_code || "Isi"}{s.role === "support" ? " (pendukung)" : ""}</td><td>{dirLabel(s.direction)}</td>
                      <td className="small wrap-any">{s.video_filename}</td><td className="mono">{fmtSec(s.start)}</td><td className="mono">{fmtSec(s.end)}</td>
                      <td className="mono">{s.duration.toFixed(1)}s</td><td>{s.edited ? <Tag tone="warn">operator</Tag> : <Tag tone="info">AI</Tag>}</td></tr>))}</tbody></table>
              </Card>
            </div>
          </div>
          <MetadataForm final={final} run={run} onChanged={reloadAll} />
          <Card title="Ekspor">
            <ExportInfo final={final} />
            <div className="row wrap">
              <button className="btn btn-primary" disabled={!final.segments.length} onClick={() => run(() => api.exportFinal(final.id, "final"), "Ekspor video hasil dimulai").then(fin.reload)}>Ekspor video hasil</button>
              <button className="btn" disabled={!final.segments.length} onClick={() => run(() => api.exportFinal(final.id, "individual"), "Ekspor potongan individual dimulai").then(fin.reload)}>Ekspor potongan individual</button>
              <span className="small muted">Output: <span className="mono">{final.output_filename || "–"}</span> · Nama duplikat otomatis diberi akhiran _01, _02, …</span>
            </div>
          </Card>
          <ExportsPanel final={final} />
        </>
      )}
    </div>
  );
}

// ====================================================================== halaman
export default function Review({ batchId, query }) {
  const b = useLoad(async () => (batchId ? api.batch(batchId) : null), [batchId]);
  const it = useLoad(async () => (batchId ? api.items(batchId) : []), [batchId]);
  const tmpls = useLoad(() => api.templates(), []);
  // template per video (jenis lokasi video sendiri), cadangan: template batch
  const tmplOf = (code) => (tmpls.data || []).find((t) => t.code === code)
    || (tmpls.data || []).find((t) => t.code === b.data?.template_code) || null;
  const tab = query.tab || (query.final ? "final" : "candidates");
  const setQ = (patch) => {
    const q = { ...query, ...patch };
    Object.keys(q).forEach((k) => (q[k] == null || q[k] === "") && delete q[k]);
    navigate(`/review/${batchId}?${new URLSearchParams(q).toString()}`);
  };
  usePolling(it.reload, 3000, !!batchId);
  const videoId = query.video ? Number(query.video) : null;
  const finalId = query.final ? Number(query.final) : null;
  useEffect(() => {
    if (batchId && !videoId && it.data && tab === "candidates") {
      const first = it.data.find((x) => ["review", "done"].includes(x.status));
      if (first) setQ({ video: first.video_id });
    }
  }, [batchId, it.data, tab]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!batchId) return <BatchPicker />;
  if (b.loading && !b.data) return <div className="page"><Loading /></div>;
  if (b.error) return <div className="page"><ErrorBox error={b.error} onRetry={b.reload} /></div>;
  const batch = b.data;
  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <a href={`#/batches/${batch.id}`} className="small">← {batch.name}</a>
          <h1>Review dan Editing</h1>
          <p className="muted">{batch.project_name} · {batch.template_name} · tiap video hasil {batch.final_duration} detik (1 hasil per video sumber)</p>
        </div>
        <div className="row">
          <VerifyAllBatchButton batch={batch} items={it.data || []} onDone={() => { it.reload(); b.reload(); window.dispatchEvent(new Event("dvp:reload")); }} />
          <Segmented value={tab} onChange={(v) => setQ({ tab: v })}
            options={[{ value: "candidates", label: "Kandidat per video" }, { value: "final", label: "Video hasil & timeline" }]} />
        </div>
      </header>
      {tab === "candidates"
        ? <CandidatesTab batch={batch} items={it.data || []} template={tmplOf((it.data || []).find((x) => x.video_id === Number(videoId))?.template_code)} videoId={videoId} setVideoId={(id) => setQ({ video: id })} finalId={finalId} />
        : <FinalTab batch={batch} items={it.data || []} tmplOf={tmplOf} finalId={finalId} setFinalId={(id) => setQ({ final: id, tab: "final" })} />}
    </div>
  );
}

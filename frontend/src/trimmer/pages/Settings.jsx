import { useEffect, useState } from "react";
import { Card, ErrorBox, Field, Loading, Segmented, useAction } from "../components/ui.jsx";
import { useLoad, usePolling } from "../hooks/useApi.js";
import { api } from "../services/api.js";
import DurationSlider from "../components/DurationSlider.jsx";

export default function Settings() {
  const s = useLoad(api.settings, []);
  const hw = useLoad(() => api.hardware(true), []);
  const [v, setV] = useState(null);
  const [run, busy] = useAction();
  useEffect(() => { if (s.data) setV(s.data.values); }, [s.data]);
  usePolling(async () => hw.setData(await api.hardware(false)), 5000);
  if (!v) return <div className="page"><Loading /></div>;
  const set = (k) => (val) => setV({ ...v, [k]: val });
  const num = (k) => (e) => set(k)(Number(e.target.value));
  const h = hw.data || {};
  return (
    <div className="page">
      <header className="page-head"><div><h1>Pengaturan</h1><p className="muted">Disimpan di database lokal (SQLite).</p></div>
        <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.updateSettings(v), "Pengaturan disimpan").then(s.reload)}>Simpan pengaturan</button></header>
      <ErrorBox error={s.error} onRetry={s.reload} />
      <div className="grid-2">
        <Card title="Default batch">
          <div className="form">
            <Field label="Durasi default tiap video hasil"><DurationSlider value={v.default_final_duration} onChange={set("default_final_duration")} live /></Field>
            <Field label="Mode perjalanan default"><Segmented value={v.default_trip_mode} onChange={set("default_trip_mode")} options={[{ value: "outbound", label: "Pergi saja" }, { value: "round_trip", label: "Pergi & kembali" }]} /></Field>
            <Field label="Proses bersamaan default" hint={`Rekomendasi ${h.recommended_concurrency ?? "–"}, maksimum perangkat ${h.max_concurrency ?? "–"}`}>
              <Segmented value={v.default_concurrency} onChange={set("default_concurrency")} options={[1, 2, 4].map((c) => ({ value: c, label: String(c) }))} /></Field>
          </div>
        </Card>
        <Card title="Analisis">
          <div className="form grid-2">
            <Field label="Sampling frame (fps)" hint="Lebih tinggi = lebih teliti, lebih lambat"><input type="number" step="0.5" min="0.5" max="10" value={v.analysis_sample_fps} onChange={num("analysis_sample_fps")} /></Field>
            <Field label="Lebar frame analisis (px)"><input type="number" step="32" min="160" max="960" value={v.analysis_width} onChange={num("analysis_width")} /></Field>
            <Field label="Deteksi objek (fps)"><input type="number" step="0.5" min="0.2" max="5" value={v.detector_sample_fps} onChange={num("detector_sample_fps")} /></Field>
            <Field label="Durasi potongan min (dtk)"><input type="number" step="0.5" min="1" max="10" value={v.min_segment_seconds} onChange={num("min_segment_seconds")} /></Field>
            <Field label="Durasi potongan maks (dtk)"><input type="number" step="1" min="4" max="60" value={v.max_segment_seconds} onChange={num("max_segment_seconds")} /></Field>
            <Field label="Porsi momen pendukung" hint="Bagian durasi final untuk footage pendukung"><input type="number" step="0.05" min="0" max="0.5" value={v.support_share} onChange={num("support_share")} /></Field>
            <label className="check"><input type="checkbox" checked={!!v.include_home_point} onChange={(e) => set("include_home_point")(e.target.checked)} /> Sertakan footage Home Point</label>
            <label className="check"><input type="checkbox" checked={!!v.generate_preview_proxy} onChange={(e) => set("generate_preview_proxy")(e.target.checked)} /> Buat proxy preview (H.265/4K)</label>
          </div>
        </Card>
        <Card title="Ekspor">
          <div className="form grid-2">
            <Field label="Mode ekspor"><select value={v.export_mode} onChange={(e) => set("export_mode")(e.target.value)}>
              <option value="auto">Otomatis (stream copy bila kompatibel)</option><option value="reencode">Selalu re-encode (paling akurat)</option><option value="copy">Paksa stream copy (potong di keyframe)</option></select></Field>
            <Field label="Tinggi maksimum (px)"><select value={v.export_max_height} onChange={(e) => set("export_max_height")(Number(e.target.value))}>
              <option value={0}>Asli (sesuai sumber)</option>
              {[720, 1080, 1440, 2160].map((x) => <option key={x} value={x}>Maks {x}p</option>)}</select></Field>
            <Field label="Codec video"><select value={v.export_codec || "h264"} onChange={(e) => set("export_codec")(e.target.value)}>
              <option value="h264">H.264 (kompatibel luas)</option><option value="hevc">H.265 / HEVC (ukuran lebih kecil)</option></select></Field>
            <Field label="Bitrate audio AAC"><select value={v.export_audio_bitrate || 320} onChange={(e) => set("export_audio_bitrate")(Number(e.target.value))}>
              {[192, 256, 320].map((x) => <option key={x} value={x}>{x} kbps</option>)}</select></Field>
            <Field label="Frame rate (bila sumber berbeda)"><input type="number" value={v.export_fps} onChange={num("export_fps")} /></Field>
            <Field label="Kualitas CRF (14–18 = sangat tinggi)" hint="Angka kecil = kualitas lebih tinggi, file lebih besar"><input type="number" min="12" max="28" value={v.export_crf} onChange={num("export_crf")} /></Field>
            <Field label="Preset encoder (slow/veryslow = terbaik)"><select value={v.export_preset} onChange={(e) => set("export_preset")(e.target.value)}>
              {["medium", "slow", "slower", "veryslow"].map((x) => <option key={x}>{x}</option>)}</select></Field>
            <label className="check"><input type="checkbox" checked={!!v.use_gpu_encoder} onChange={(e) => set("use_gpu_encoder")(e.target.checked)} /> Gunakan encoder GPU (NVENC) bila tersedia — lebih cepat, kualitas per ukuran sedikit di bawah x264 slow</label>
            <Field label="Folder output" hint={`Kosong = ${s.data.exports_dir}`}><input className="mono" value={v.output_dir} onChange={(e) => set("output_dir")(e.target.value)} /></Field>
          </div>
        </Card>
        <Card title="Waktu kejadian">
          <div className="form">
            <label className="check"><input type="checkbox" checked={!!v.metadata_time_is_utc} onChange={(e) => set("metadata_time_is_utc")(e.target.checked)} /> Metadata creation_time video dalam UTC</label>
            <Field label="Zona waktu lokal (UTC+jam)" hint="WIB = 7, WITA = 8, WIT = 9"><input type="number" min="-12" max="14" value={v.local_utc_offset_hours} onChange={num("local_utc_offset_hours")} /></Field>
            <p className="small muted">Prioritas waktu nama file: input operator → metadata video yang valid. Waktu ekspor tidak pernah dipakai.</p>
          </div>
        </Card>
      </div>
      <Card title="Perangkat" actions={<button className="btn btn-sm" onClick={hw.reload}>Deteksi ulang</button>}>
        <dl className="kv kv-2">
          <dt>Mode pemrosesan</dt><dd>{h.mode === "cuda" ? "GPU (CUDA)" : "CPU"}</dd>
          <dt>Nama perangkat</dt><dd>{h.device_name}</dd>
          <dt>Status CUDA</dt><dd>{h.cuda_status}</dd>
          <dt>GPU NVIDIA</dt><dd>{h.gpus?.length ? h.gpus.map((g) => `${g.name} (${g.memory_used_mb}/${g.memory_total_mb} MB, ${g.utilization_pct}%)`).join(", ") : "–"}</dd>
          <dt>OpenCV CUDA</dt><dd>{h.opencv_cuda_devices} perangkat</dd>
          <dt>ONNX Runtime CUDA</dt><dd>{h.onnxruntime_cuda ? "Ya" : "Tidak"}</dd>
          <dt>NVENC</dt><dd>{h.nvenc_available ? "Tersedia" : "Tidak"}</dd>
          <dt>CPU</dt><dd>{h.cpu_name} · {h.cpu_cores} core · {h.usage?.cpu_percent ?? "–"}%</dd>
          <dt>RAM</dt><dd>{h.ram_available_gb} / {h.ram_total_gb} GB tersedia · {h.usage?.ram_percent ?? "–"}% terpakai</dd>
          <dt>Platform</dt><dd>{h.platform}</dd>
          <dt>FFmpeg / FFprobe</dt><dd>{h.ffmpeg_available ? "✓" : "✗"} / {h.ffprobe_available ? "✓" : "✗"}</dd>
          <dt>Folder data</dt><dd className="mono small">{s.data.data_dir}</dd>
        </dl>
      </Card>
    </div>
  );
}

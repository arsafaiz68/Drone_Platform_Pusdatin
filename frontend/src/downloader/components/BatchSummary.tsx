import {
  CheckCircle2,
  Download,
  Film,
  FolderOpen,
  SkipForward,
  Loader2,
  PlusCircle,
  RotateCw,
  Scissors,
  StopCircle,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";
import type { Batch } from "../types";
import type { SocketState } from "../services/websocket";
import { formatBytes, formatDateId } from "../utils/format";

interface Props {
  batch: Batch;
  socketState: SocketState;
  onCancel: () => void;
  onRetryFailed: () => void;
  onNewBatch: () => void;
  onOpenFolder: () => void;
  busy: boolean;
}

const STATUS_LABEL: Record<Batch["status"], { label: string; cls: string }> = {
  running: { label: "Sedang berjalan", cls: "bg-blue-50 text-blue-700" },
  completed: { label: "Selesai", cls: "bg-emerald-50 text-emerald-700" },
  partial: { label: "Selesai sebagian", cls: "bg-amber-50 text-amber-700" },
  failed: { label: "Gagal", cls: "bg-red-50 text-red-700" },
  cancelled: { label: "Dibatalkan", cls: "bg-slate-200 text-slate-600" },
};

export default function BatchSummary({ batch, socketState, onCancel, onRetryFailed, onNewBatch, onOpenFolder, busy }: Props) {
  const s = batch.summary;
  const tiles = [
    { label: "Total video", value: s.total, Icon: Film, cls: "text-navy-700 bg-navy-50" },
    { label: `Berhasil disimpan · ${formatBytes(s.total_bytes)}`, value: s.success, Icon: Download, cls: "text-emerald-700 bg-emerald-50" },
    { label: "Dilewati (sudah ada)", value: s.skipped, Icon: SkipForward, cls: "text-sky-700 bg-sky-50" },
    { label: "Gagal", value: s.failed, Icon: XCircle, cls: "text-red-700 bg-red-50" },
    { label: "Sedang diproses", value: s.in_progress + s.pending, Icon: Loader2, cls: "text-amber-700 bg-amber-50" },
  ];
  const st = STATUS_LABEL[batch.status];
  const doneRatio = s.total ? ((s.success + s.skipped + s.failed + s.cancelled) / s.total) * 100 : 0;

  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="card-title">
            <CheckCircle2 className="h-5 w-5 text-navy-600" />
            Ringkasan Batch
            <span className={`badge ${st.cls}`}>{st.label}</span>
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            ID {batch.id} · dibuat {formatDateId(batch.created_at)} · {batch.quality}p · paralel {batch.parallel}
          </p>
          <p className="mt-0.5 truncate font-mono text-xs text-slate-600" title={batch.output_dir}>
            Folder: {batch.output_dir}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`badge ${socketState === "open" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}
            title="Koneksi monitoring real-time"
          >
            {socketState === "open" ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
            {socketState === "open" ? "Live" : socketState === "connecting" ? "Menghubungkan…" : "Terputus"}
          </span>
          <button type="button" className="btn-secondary" onClick={onOpenFolder}>
            <FolderOpen className="h-4 w-4" /> Buka folder
          </button>
          {batch.status === "running" && (
            <button type="button" className="btn-danger" onClick={onCancel} disabled={busy}>
              <StopCircle className="h-4 w-4" /> Batalkan batch
            </button>
          )}
          {(s.failed > 0 || s.cancelled > 0) && batch.status !== "running" && (
            <button type="button" className="btn-secondary" onClick={onRetryFailed} disabled={busy}>
              <RotateCw className="h-4 w-4" /> Ulangi yang gagal ({s.failed + s.cancelled})
            </button>
          )}
          {batch.status !== "running" && s.success + s.skipped > 0 && (
            <a
              className="btn-primary bg-emerald-700 hover:bg-emerald-800"
              href={`/trimmer/#/batches?import=${encodeURIComponent(batch.id)}`}
              title="Buka Drone Video Trimmer; informasi tiap video (lokasi, tanggal, waktu, lalin) terbawa otomatis"
            >
              <Scissors className="h-4 w-4" /> Proses di Trimmer ({s.success + s.skipped} video)
            </a>
          )}
          {batch.status !== "running" && (
            <button type="button" className="btn-secondary" onClick={onNewBatch}>
              <PlusCircle className="h-4 w-4" /> Batch baru
            </button>
          )}
        </div>
      </div>
      <div className="h-1 bg-slate-100">
        <div className="h-full bg-navy-600 transition-all duration-500" style={{ width: `${doneRatio}%` }} />
      </div>
      <div className="grid grid-cols-2 gap-3 p-5 md:grid-cols-5">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-xl border border-slate-100 p-4">
            <div className={`mb-2 inline-flex rounded-lg p-2 ${t.cls}`}>
              <t.Icon className="h-4 w-4" />
            </div>
            <p className="text-2xl font-semibold text-navy-900">{t.value}</p>
            <p className="text-xs text-slate-500">{t.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

import { CheckCircle2, History, Loader2, Server, X, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Batch, Health } from "../types";
import { formatDateId } from "../utils/format";

interface Props {
  open: boolean;
  onClose: () => void;
  health: Health | null;
  onOpenBatch: (id: string) => void;
}

function Row({ ok, label, value }: { ok: boolean | null; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 py-2">
      {ok === null ? (
        <span className="mt-0.5 h-4 w-4" />
      ) : ok ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" />
      ) : (
        <XCircle className="mt-0.5 h-4 w-4 text-red-600" />
      )}
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-700">{label}</p>
        <p className="break-all text-xs text-slate-500">{value}</p>
      </div>
    </div>
  );
}

export default function SettingsPanel({ open, onClose, health, onOpenBatch }: Props) {
  const [batches, setBatches] = useState<Batch[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setBatches(null);
    api
      .listBatches()
      .then((r) => setBatches(r.batches))
      .catch((e: Error) => setError(e.message));
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/25 backdrop-blur-sm" onClick={onClose}>
      <aside
        className="glass m-3 h-[calc(100%-1.5rem)] w-full max-w-md overflow-y-auto rounded-[28px]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="card-title">
            <Server className="h-5 w-5 text-navy-600" /> Pengaturan & Status Sistem
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Tutup">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="divide-y divide-slate-100 px-5">
          <Row ok={!!health} label="Backend" value={health ? `v${health.version} · http://127.0.0.1:8000` : "Tidak terhubung"} />
          <Row
            ok={health ? health.ffmpeg : null}
            label="FFmpeg"
            value={health?.ffmpeg ? health.ffmpeg_path ?? "" : "Tidak ditemukan. Pasang FFmpeg & tambahkan ke PATH atau isi FFMPEG_LOCATION."}
          />
          <Row
            ok={health ? !!health.yt_dlp_version : null}
            label="yt-dlp"
            value={health?.yt_dlp_version ?? "Belum terpasang (pip install -r requirements.txt)"}
          />
          <Row ok={null} label="Folder tujuan bawaan" value={health?.default_output_dir ?? "-"} />
          <Row ok={null} label="Log aktivitas" value={health?.log_dir ?? "-"} />
        </div>
        <div className="mt-4 border-t border-slate-100 px-5 py-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-navy-900">
            <History className="h-4 w-4" /> Riwayat Batch
          </h3>
          {error && <p className="text-xs text-red-600">{error}</p>}
          {batches === null && !error && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
          {batches?.length === 0 && <p className="text-xs text-slate-500">Belum ada riwayat.</p>}
          <ul className="space-y-2">
            {batches?.map((b) => (
              <li key={b.id}>
                <button
                  type="button"
                  className="w-full rounded-xl border border-slate-200 p-3 text-left hover:border-navy-200 hover:bg-navy-50/50"
                  onClick={() => {
                    onOpenBatch(b.id);
                    onClose();
                  }}
                >
                  <p className="text-sm font-medium text-slate-700">{formatDateId(b.created_at)}</p>
                  <p className="text-xs text-slate-500">
                    {b.summary.total} video · {b.summary.success} berhasil · {b.summary.skipped} dilewati · {b.summary.failed} gagal
                  </p>
                  <p className="truncate font-mono text-[11px] text-slate-400">→ {b.output_dir}</p>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}

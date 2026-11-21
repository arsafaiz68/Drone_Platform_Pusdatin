import {
  CheckCircle2,
  Clock,
  Download,
  SkipForward,
  Film,
  ListVideo,
  Loader2,
  RotateCw,
  Ban,
  Square,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { Job, JobStatus } from "../types";
import { formatBytes, formatEta, formatSpeed } from "../utils/format";

const STATUS: Record<JobStatus, { label: string; cls: string; Icon: typeof Clock; spin?: boolean }> = {
  pending: { label: "Menunggu", cls: "bg-slate-100 text-slate-600", Icon: Clock },
  downloading: { label: "Mengunduh", cls: "bg-blue-50 text-blue-700", Icon: Download },
  processing: { label: "Memproses video", cls: "bg-indigo-50 text-indigo-700", Icon: Loader2, spin: true },
  success: { label: "Berhasil", cls: "bg-emerald-50 text-emerald-700", Icon: CheckCircle2 },
  skipped: { label: "Dilewati", cls: "bg-sky-50 text-sky-700", Icon: SkipForward },
  failed: { label: "Gagal", cls: "bg-red-50 text-red-700", Icon: XCircle },
  cancelled: { label: "Dibatalkan", cls: "bg-slate-200 text-slate-600", Icon: Ban },
};

const ACTIVE: JobStatus[] = ["pending", "downloading", "processing"];

function Progress({ value, color, label, sub }: { value: number; color: string; label: string; sub?: string }) {
  const v = Math.max(0, Math.min(100, value || 0));
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px] text-slate-500">
        <span>{label}</span>
        <span>
          {sub && <span className="mr-2">{sub}</span>}
          {v.toFixed(v === 100 || v === 0 ? 0 : 1)}%
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full transition-all duration-300 ${color}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

interface Props {
  jobs: Job[];
  onRetryJob: (jobId: string) => void;
  onCancelJob: (jobId: string) => void;
}

type Filter = "all" | "active" | "success" | "failed";

export default function DownloadQueue({ jobs, onRetryJob, onCancelJob }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const shown = useMemo(
    () =>
      jobs.filter((j) =>
        filter === "all"
          ? true
          : filter === "active"
            ? ACTIVE.includes(j.status)
            : filter === "success"
              ? j.status === "success" || j.status === "skipped"
              : j.status === "failed" || j.status === "cancelled",
      ),
    [jobs, filter],
  );

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">
          <ListVideo className="h-5 w-5 text-navy-600" />
          Monitoring Pekerjaan
        </h2>
        <div className="inline-flex rounded-xl bg-slate-100 p-1 text-xs">
          {(
            [
              ["all", "Semua"],
              ["active", "Diproses"],
              ["success", "Berhasil"],
              ["failed", "Gagal/Batal"],
            ] as [Filter, string][]
          ).map(([f, l]) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`rounded-lg px-3 py-1 font-medium ${filter === f ? "bg-white text-navy-800 shadow-sm" : "text-slate-500"}`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      <ul className="divide-y divide-slate-100">
        {shown.length === 0 && <li className="p-6 text-center text-sm text-slate-500">Tidak ada pekerjaan.</li>}
        {shown.map((j) => {
          const st = STATUS[j.status];
          const dlSub =
            j.status === "downloading"
              ? [
                  j.downloaded_bytes != null && j.total_bytes
                    ? `${formatBytes(j.downloaded_bytes)} / ${formatBytes(j.total_bytes)}`
                    : j.downloaded_bytes != null
                      ? formatBytes(j.downloaded_bytes)
                      : "",
                  formatSpeed(j.speed),
                  j.eta != null ? `sisa ${formatEta(j.eta)}` : "",
                ]
                  .filter(Boolean)
                  .join(" · ")
              : undefined;
          const meta = j.metadata ?? {};
          return (
            <li key={j.id} className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,2.2fr)_minmax(0,2fr)_auto]">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-400">#{j.index}</span>
                  <span className="truncate font-medium text-navy-900">{meta.location ?? "Tanpa lokasi"}</span>
                  <span className={`badge ${st.cls}`}>
                    <st.Icon className={`h-3.5 w-3.5 ${st.spin ? "animate-spin" : ""}`} /> {st.label}
                  </span>
                </div>
                <p
                  className="mt-1 flex items-center gap-1.5 truncate font-mono text-xs text-slate-600"
                  title={j.output_path ?? undefined}
                >
                  <Film className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                  {j.final_filename ?? `${j.base_name}.mp4`}
                </p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  {meta.traffic && <>Lalin: {meta.traffic} · </>}
                  Ukuran: {formatBytes(j.file_size ?? j.total_bytes)}
                  {j.attempts > 1 && <> · Percobaan: {j.attempts}</>}
                </p>
                {j.note && <p className="mt-1 text-xs text-sky-700">{j.note}</p>}
                {j.error && (
                  <p
                    className={`mt-1.5 rounded-lg px-2 py-1 text-xs ${
                      j.status === "failed" ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"
                    }`}
                  >
                    {j.error}
                  </p>
                )}
              </div>
              <div className="space-y-2 self-center">
                <Progress
                  value={j.status === "success" || j.status === "skipped" ? 100 : j.download_progress}
                  color={
                    j.status === "failed"
                      ? "bg-red-400"
                      : j.status === "success"
                        ? "bg-emerald-500"
                        : j.status === "skipped"
                          ? "bg-sky-400"
                          : "bg-blue-500"
                  }
                  label={
                    j.status === "processing"
                      ? "Menggabungkan audio & video, menyimpan ke folder"
                      : j.status === "success"
                        ? "Tersimpan"
                        : j.status === "skipped"
                          ? "Sudah ada di folder"
                          : "Unduh"
                  }
                  sub={dlSub}
                />
              </div>
              <div className="flex items-center justify-end gap-1 self-center">
                {ACTIVE.includes(j.status) && (
                  <button type="button" className="btn-ghost text-red-600" onClick={() => onCancelJob(j.id)} title="Batalkan">
                    <Square className="h-4 w-4" />
                  </button>
                )}
                {(j.status === "failed" || j.status === "cancelled") && (
                  <button type="button" className="btn-secondary px-3 py-1.5" onClick={() => onRetryJob(j.id)}>
                    <RotateCw className="h-4 w-4" /> Ulangi
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

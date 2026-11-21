import { AlertTriangle, Loader2, Play, SlidersHorizontal } from "lucide-react";
import type { DownloadOptions } from "../types";

interface Props {
  options: DownloadOptions;
  onChange: (o: DownloadOptions) => void;
  onStart: () => void;
  starting: boolean;
  validCount: number;
  invalidCount: number;
  outputDir: string | null;
  ffmpegOk: boolean | null;
  disabled?: boolean;
}

function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  disabled,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded-xl bg-slate-100 p-1">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
            value === o.value ? "bg-white text-navy-800 shadow-sm" : "text-slate-500 hover:text-slate-700"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function DownloadSettings({
  options,
  onChange,
  onStart,
  starting,
  validCount,
  invalidCount,
  outputDir,
  ffmpegOk,
  disabled,
}: Props) {
  const problems: string[] = [];
  if (validCount === 0) problems.push("Belum ada URL valid untuk diproses.");
  if (invalidCount > 0) problems.push(`${invalidCount} entri memiliki URL tidak valid — perbaiki atau hapus.`);
  if (!outputDir) problems.push("Folder tujuan belum dipilih.");
  if (ffmpegOk === false) problems.push("FFmpeg tidak ditemukan di komputer (lihat Pengaturan).");

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">
          <SlidersHorizontal className="h-5 w-5 text-navy-600" />
          4. Pengaturan Download
        </h2>
      </div>
      <div className="grid gap-5 p-5 md:grid-cols-2 xl:grid-cols-4">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Kualitas maksimal</p>
          <Segmented
            value={options.quality}
            disabled={disabled}
            onChange={(v) => onChange({ ...options, quality: v })}
            options={[
              { value: 480, label: "480p" },
              { value: 720, label: "720p" },
              { value: 1080, label: "1080p" },
            ]}
          />
          <p className="mt-1.5 text-xs text-slate-500">Jika tidak tersedia, dipakai kualitas tertinggi di bawahnya.</p>
        </div>
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Unduhan paralel</p>
          <Segmented
            value={options.parallel}
            disabled={disabled}
            onChange={(v) => onChange({ ...options, parallel: v })}
            options={[
              { value: 1, label: "1" },
              { value: 2, label: "2" },
              { value: 3, label: "3" },
            ]}
          />
        </div>
        <div className="md:col-span-2">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Jika nama file sudah ada di folder tujuan
          </p>
          <select
            className="input"
            value={options.conflict_behavior}
            disabled={disabled}
            onChange={(e) =>
              onChange({ ...options, conflict_behavior: e.target.value as DownloadOptions["conflict_behavior"] })
            }
          >
            <option value="rename">Simpan dengan nama baru (…_2.mp4) — aman</option>
            <option value="skip">Lewati, jangan unduh ulang</option>
            <option value="replace">Timpa file lama</option>
          </select>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-4">
        <div className="space-y-1 text-sm">
          {problems.length === 0 ? (
            <p className="text-emerald-700">
              Siap mengunduh <b>{validCount}</b> video ke <code className="rounded bg-emerald-50 px-1">{outputDir}</code>.
            </p>
          ) : (
            problems.map((p) => (
              <p key={p} className="flex items-center gap-2 text-amber-700">
                <AlertTriangle className="h-4 w-4" /> {p}
              </p>
            ))
          )}
        </div>
        <button
          type="button"
          className="btn-primary px-6 py-2.5"
          onClick={onStart}
          disabled={disabled || starting || problems.length > 0}
        >
          {starting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Mulai Batch
        </button>
      </div>
    </section>
  );
}

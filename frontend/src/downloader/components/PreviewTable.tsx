import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Plus,
  Table2,
  Trash2,
  Wand2,
  XCircle,
} from "lucide-react";
import { Fragment, useState } from "react";
import type { Entry } from "../types";

interface Props {
  entries: Entry[];
  globalWarnings: string[];
  onChange: (entries: Entry[]) => void;
  refreshing: boolean;
  disabled?: boolean;
}

type Field = keyof Pick<
  Entry,
  | "location"
  | "date"
  | "time"
  | "timezone"
  | "traffic"
  | "weather"
  | "wave_height"
  | "wave_direction"
  | "traffic_engineering"
  | "url_original"
  | "filename"
>;

function newEntry(index: number): Entry {
  return {
    id: `new-${Date.now()}-${index}`,
    index,
    location: "",
    date: null,
    time: null,
    timezone: null,
    weather: null,
    wave_height: null,
    wave_direction: null,
    traffic: "",
    traffic_engineering: null,
    notes: [],
    url_original: "",
    url: null,
    video_id: null,
    url_valid: false,
    url_error: "URL kosong",
    filename: "",
    filename_manual: false,
    warnings: [],
    raw_block: "",
  };
}

export default function PreviewTable({ entries, globalWarnings, onChange, refreshing, disabled }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const update = (id: string, field: Field, value: string) => {
    onChange(
      entries.map((e) => {
        if (e.id !== id) return e;
        const next: Entry = { ...e, [field]: value === "" ? null : value };
        if (field === "filename") {
          next.filename = value;
          next.filename_manual = value.trim() !== "";
        }
        if (field === "url_original") next.url_original = value;
        return next;
      }),
    );
  };

  const remove = (id: string) =>
    onChange(entries.filter((e) => e.id !== id).map((e, i) => ({ ...e, index: i + 1 })));

  const resetName = (id: string) =>
    onChange(entries.map((e) => (e.id === id ? { ...e, filename: "", filename_manual: false } : e)));

  const add = () => onChange([...entries, newEntry(entries.length + 1)]);

  const valid = entries.filter((e) => e.url_valid).length;
  const withWarn = entries.filter((e) => e.warnings.length > 0).length;

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">
          <Table2 className="h-5 w-5 text-navy-600" />
          2. Preview Hasil Parsing
          {refreshing && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
        </h2>
        <div className="flex items-center gap-2 text-xs">
          <span className="badge bg-emerald-50 text-emerald-700">{valid} URL valid</span>
          {entries.length - valid > 0 && (
            <span className="badge bg-red-50 text-red-700">{entries.length - valid} URL tidak valid</span>
          )}
          {withWarn > 0 && <span className="badge bg-amber-50 text-amber-700">{withWarn} perlu dicek</span>}
        </div>
      </div>

      {globalWarnings.length > 0 && (
        <div className="mx-5 mt-4 space-y-1 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {globalWarnings.map((w, i) => (
            <p key={i} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {w}
            </p>
          ))}
        </div>
      )}

      {entries.length === 0 ? (
        <p className="p-8 text-center text-sm text-slate-500">
          Belum ada data. Tempel laporan lalu klik <b>Parse Data</b>.
        </p>
      ) : (
        <div className="overflow-x-auto p-2">
          <table className="w-full min-w-[1100px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500">
              <tr className="border-b border-slate-200">
                <th className="w-8 px-2 py-2" />
                <th className="w-10 px-2 py-2">No</th>
                <th className="px-2 py-2">Lokasi</th>
                <th className="w-36 px-2 py-2">Tanggal</th>
                <th className="w-28 px-2 py-2">Waktu</th>
                <th className="w-40 px-2 py-2">Lalin</th>
                <th className="px-2 py-2">URL</th>
                <th className="min-w-[280px] px-2 py-2">Nama File</th>
                <th className="w-16 px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const isOpen = !!expanded[e.id];
                const hasWarn = e.warnings.length > 0;
                return (
                  <Fragment key={e.id}>
                    <tr
                      className={`border-b border-slate-100 align-top ${
                        !e.url_valid ? "bg-red-50/60" : hasWarn ? "bg-amber-50/50" : ""
                      }`}
                    >
                      <td className="px-1 py-1.5">
                        <button
                          type="button"
                          className="btn-ghost"
                          onClick={() => setExpanded({ ...expanded, [e.id]: !isOpen })}
                          title="Detail metadata"
                        >
                          {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </button>
                      </td>
                      <td className="px-2 py-2.5 font-medium text-slate-500">{e.index}</td>
                      <td className="px-1 py-1.5">
                        <input
                          className="cell-input"
                          value={e.location ?? ""}
                          disabled={disabled}
                          onChange={(ev) => update(e.id, "location", ev.target.value)}
                          placeholder="Nama lokasi"
                        />
                      </td>
                      <td className="px-1 py-1.5">
                        <input
                          type="date"
                          className="cell-input"
                          value={e.date ?? ""}
                          disabled={disabled}
                          onChange={(ev) => update(e.id, "date", ev.target.value)}
                        />
                      </td>
                      <td className="px-1 py-1.5">
                        <div className="flex items-center gap-1">
                          <input
                            type="time"
                            className="cell-input"
                            value={e.time ?? ""}
                            disabled={disabled}
                            onChange={(ev) => update(e.id, "time", ev.target.value)}
                          />
                          {e.timezone && <span className="text-[10px] text-slate-400">{e.timezone}</span>}
                        </div>
                      </td>
                      <td className="px-1 py-1.5">
                        <input
                          className="cell-input"
                          value={e.traffic ?? ""}
                          disabled={disabled}
                          onChange={(ev) => update(e.id, "traffic", ev.target.value)}
                          placeholder="Kondisi lalin"
                        />
                      </td>
                      <td className="px-1 py-1.5">
                        <div className="flex items-start gap-1">
                          {e.url_valid ? (
                            <CheckCircle2 className="mt-1.5 h-4 w-4 shrink-0 text-emerald-600" />
                          ) : (
                            <XCircle className="mt-1.5 h-4 w-4 shrink-0 text-red-600" />
                          )}
                          <div className="w-full">
                            <input
                              className="cell-input font-mono text-xs"
                              value={e.url_original}
                              disabled={disabled}
                              onChange={(ev) => update(e.id, "url_original", ev.target.value)}
                              placeholder="https://youtu.be/…"
                              title={e.url ?? e.url_error ?? ""}
                            />
                            {!e.url_valid && e.url_error && (
                              <p className="px-2 text-[11px] text-red-600">{e.url_error}</p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-1 py-1.5">
                        <div className="flex items-center gap-1">
                          <input
                            className={`cell-input font-mono text-xs ${e.filename_manual ? "text-navy-700" : ""}`}
                            value={e.filename}
                            disabled={disabled}
                            onChange={(ev) => update(e.id, "filename", ev.target.value)}
                            title="Ekstensi (.mp4/.mkv) ditambahkan otomatis sesuai format video"
                          />
                          <span className="text-[11px] text-slate-400">.mp4</span>
                          {e.filename_manual && (
                            <button
                              type="button"
                              className="btn-ghost"
                              title="Kembalikan ke nama otomatis"
                              onClick={() => resetName(e.id)}
                            >
                              <Wand2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="px-1 py-1.5">
                        <div className="flex items-center justify-end gap-1">
                          {hasWarn && (
                            <span title={e.warnings.join("\n")}>
                              <AlertTriangle className="h-4 w-4 text-amber-500" />
                            </span>
                          )}
                          <button
                            type="button"
                            className="btn-ghost text-red-600"
                            onClick={() => remove(e.id)}
                            disabled={disabled}
                            title="Hapus entri"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="border-b border-slate-100 bg-slate-50/70">
                        <td />
                        <td colSpan={8} className="px-2 py-3">
                          <div className="grid gap-3 md:grid-cols-5">
                            {(
                              [
                                ["weather", "Cuaca"],
                                ["wave_height", "Tinggi gelombang"],
                                ["wave_direction", "Arah gelombang"],
                                ["traffic_engineering", "Rekayasa lalin"],
                                ["timezone", "Zona waktu"],
                              ] as [Field, string][]
                            ).map(([f, label]) => (
                              <label key={f} className="text-xs text-slate-500">
                                {label}
                                <input
                                  className="input mt-1"
                                  value={(e[f] as string | null) ?? ""}
                                  disabled={disabled}
                                  onChange={(ev) => update(e.id, f, ev.target.value)}
                                />
                              </label>
                            ))}
                          </div>
                          {e.warnings.length > 0 && (
                            <ul className="mt-3 list-inside list-disc text-xs text-amber-700">
                              {e.warnings.map((w, i) => (
                                <li key={i}>{w}</li>
                              ))}
                            </ul>
                          )}
                          {e.raw_block && (
                            <pre className="mt-3 max-h-40 overflow-auto rounded-lg bg-white p-3 text-[11px] text-slate-500 ring-1 ring-slate-200">
                              {e.raw_block}
                            </pre>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
          <div className="p-3">
            <button type="button" className="btn-secondary" onClick={add} disabled={disabled}>
              <Plus className="h-4 w-4" /> Tambah entri manual
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

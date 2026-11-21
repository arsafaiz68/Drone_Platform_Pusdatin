import {
  ArrowUp,
  ChevronRight,
  ExternalLink,
  Folder,
  FolderCheck,
  FolderOpen,
  FolderPlus,
  FolderSearch,
  HardDrive,
  Home,
  Loader2,
  RefreshCw,
  Star,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { LocalFolder, LocalRoot } from "../types";
import { formatBytes } from "../utils/format";

interface Props {
  value: string | null;
  onChange: (path: string) => void;
  disabled?: boolean;
}

/** Memecah path Windows/Unix menjadi breadcrumb: C:\A\B → [C:\, C:\A, C:\A\B]. */
function crumbs(path: string): { name: string; path: string }[] {
  const win = /^[A-Za-z]:[\\/]/.test(path) || path.includes("\\");
  const sep = win ? "\\" : "/";
  const parts = path.split(/[\\/]+/).filter(Boolean);
  const out: { name: string; path: string }[] = [];
  let acc = win ? "" : "/";
  if (!win) out.push({ name: "/", path: "/" });
  parts.forEach((p, i) => {
    if (win) acc = i === 0 ? `${p}${sep}` : `${acc}${acc.endsWith(sep) ? "" : sep}${p}`;
    else acc = `${acc}${acc.endsWith("/") ? "" : "/"}${p}`;
    out.push({ name: win && i === 0 ? p : p, path: acc });
  });
  return out;
}

export default function LocalFolderBrowser({ value, onChange, disabled }: Props) {
  const [roots, setRoots] = useState<LocalRoot[]>([]);
  const [listing, setListing] = useState<LocalFolder | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const [manual, setManual] = useState(value ?? "");
  const [targetInfo, setTargetInfo] = useState<LocalFolder | null>(null);
  const [targetMissing, setTargetMissing] = useState(false);

  const run = useCallback(async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
    setLoading(label);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError((e as Error).message);
      return undefined;
    } finally {
      setLoading(null);
    }
  }, []);

  const browse = useCallback(
    async (path: string) => {
      const r = await run("browse", () => api.localFolder(path));
      if (r) {
        setListing(r);
        setNewFolder(null);
      }
    },
    [run],
  );

  // Muat pintasan & drive; jika belum ada pilihan, pakai folder bawaan.
  useEffect(() => {
    api
      .localRoots()
      .then((r) => {
        setRoots(r.roots);
        if (!value) onChange(r.default);
      })
      .catch((e: Error) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Info folder terpilih (ruang kosong, izin tulis). Folder belum ada → dibuat saat batch dimulai.
  useEffect(() => {
    setManual(value ?? "");
    if (!value) return;
    let alive = true;
    api
      .localFolder(value)
      .then((r) => {
        if (!alive) return;
        setTargetInfo(r);
        setTargetMissing(false);
        setListing((cur) => cur ?? r);
      })
      .catch(() => {
        if (!alive) return;
        setTargetInfo(null);
        setTargetMissing(true);
        // Tampilkan lokasi pertama (mis. folder Video) agar penjelajah tidak kosong.
        api
          .localRoots()
          .then((rr) => (rr.roots[0] ? api.localFolder(rr.roots[0].path) : null))
          .then((r) => r && alive && setListing((cur) => cur ?? r))
          .catch(() => undefined);
      });
    return () => {
      alive = false;
    };
  }, [value]);

  async function pickNative() {
    const r = await run("pick", () => api.localPick(value));
    if (r?.path) {
      onChange(r.path);
      void browse(r.path);
    }
  }

  async function createFolder() {
    if (!listing || !newFolder?.trim()) return;
    const created = await run("create", () => api.localCreateFolder(listing.path, newFolder.trim()));
    if (created) {
      await browse(listing.path);
      onChange(created.path);
    }
  }

  const selectedHere = !!listing && listing.path === value;

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">
          <FolderOpen className="h-5 w-5 text-navy-600" />
          3. Folder Tujuan Unduhan
        </h2>
        <span className="text-xs text-slate-500">Video disimpan langsung di komputer ini</span>
      </div>

      <div className="space-y-4 p-5">
        {/* --- Folder terpilih --- */}
        <div
          className={`rounded-xl border p-4 ${
            value && !targetMissing && targetInfo?.writable !== false
              ? "border-emerald-200 bg-emerald-50"
              : "border-amber-200 bg-amber-50"
          }`}
        >
          <p className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            <FolderCheck className="h-4 w-4" /> Folder tujuan
          </p>
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(ev) => {
              ev.preventDefault();
              if (manual.trim()) onChange(manual.trim());
            }}
          >
            <input
              className="input min-w-[280px] flex-1 font-mono text-[13px]"
              value={manual}
              disabled={disabled}
              onChange={(e) => setManual(e.target.value)}
              onBlur={() => manual.trim() && manual.trim() !== value && onChange(manual.trim())}
              placeholder="D:\Arsip Video\April 2026"
            />
            <button type="button" className="btn-primary" onClick={pickNative} disabled={disabled || !!loading}>
              {loading === "pick" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderSearch className="h-4 w-4" />}
              Pilih folder…
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={!value || targetMissing}
              onClick={() => value && run("open", () => api.localOpen(value))}
              title="Buka di File Explorer"
            >
              <ExternalLink className="h-4 w-4" /> Buka
            </button>
          </form>
          <p className="mt-2 text-xs text-slate-600">
            {!value ? (
              "Belum ada folder dipilih."
            ) : targetMissing ? (
              <>Folder belum ada — akan dibuat otomatis saat batch dimulai.</>
            ) : targetInfo ? (
              <>
                {targetInfo.writable ? "Dapat ditulis" : "Tidak ada izin menulis!"} · ruang kosong{" "}
                <b>{formatBytes(targetInfo.free_bytes)}</b> · {targetInfo.video_count} video sudah ada di folder ini
              </>
            ) : (
              "Memeriksa folder…"
            )}
          </p>
          {loading === "pick" && (
            <p className="mt-1 text-xs text-navy-700">
              Jendela “Pilih folder” terbuka di layar Windows (mungkin di belakang browser).
            </p>
          )}
        </div>

        {error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

        {/* --- Penjelajah folder --- */}
        <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div className="rounded-xl border border-slate-200 p-1">
            <p className="px-3 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-slate-500">Lokasi</p>
            <ul>
              {roots.map((r) => (
                <li key={r.path}>
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => browse(r.path)}
                    className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-100 ${
                      listing?.path === r.path ? "bg-navy-50 font-medium text-navy-800" : ""
                    }`}
                    title={r.path}
                  >
                    {r.kind === "drive" ? (
                      <HardDrive className="h-4 w-4 text-slate-500" />
                    ) : r.kind === "home" ? (
                      <Home className="h-4 w-4 text-slate-500" />
                    ) : (
                      <Star className="h-4 w-4 text-amber-500" />
                    )}
                    <span className="flex-1 truncate">{r.name}</span>
                    {r.free_bytes != null && (
                      <span className="text-[10px] text-slate-400">{formatBytes(r.free_bytes)}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl border border-slate-200">
            <div className="flex items-center gap-1 border-b border-slate-100 p-2">
              <button
                type="button"
                className="btn-ghost"
                title="Folder induk"
                disabled={!listing?.parent || !!loading}
                onClick={() => listing?.parent && browse(listing.parent)}
              >
                <ArrowUp className="h-4 w-4" />
              </button>
              <button
                type="button"
                className="btn-ghost"
                title="Muat ulang"
                disabled={!listing || !!loading}
                onClick={() => listing && browse(listing.path)}
              >
                {loading === "browse" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              </button>
              <nav className="flex min-w-0 flex-1 flex-wrap items-center gap-0.5 text-sm">
                {listing ? (
                  crumbs(listing.path).map((c, i) => (
                    <span key={c.path} className="flex items-center">
                      {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-slate-400" />}
                      <button
                        type="button"
                        className="max-w-[160px] truncate rounded px-1 hover:bg-slate-100"
                        onClick={() => browse(c.path)}
                      >
                        {c.name}
                      </button>
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-slate-500">Pilih lokasi di sebelah kiri.</span>
                )}
              </nav>
            </div>
            <ul className="max-h-72 overflow-y-auto p-1">
              {listing?.error && <li className="p-3 text-xs text-red-600">{listing.error}</li>}
              {listing && !listing.error && listing.children.length === 0 && (
                <li className="p-3 text-xs text-slate-500">Tidak ada subfolder.</li>
              )}
              {listing?.children.map((f) => (
                <li key={f.path}>
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-100"
                    onClick={() => browse(f.path)}
                    disabled={!!loading || disabled}
                  >
                    {f.path === value ? (
                      <FolderCheck className="h-4 w-4 text-emerald-600" />
                    ) : (
                      <Folder className="h-4 w-4 text-amber-500" />
                    )}
                    <span className="flex-1 truncate">{f.name}</span>
                    <ChevronRight className="h-4 w-4 text-slate-300" />
                  </button>
                </li>
              ))}
            </ul>
            {listing && (
              <div className="border-t border-slate-100 p-2">
                {newFolder !== null ? (
                  <form
                    className="flex gap-1"
                    onSubmit={(ev) => {
                      ev.preventDefault();
                      void createFolder();
                    }}
                  >
                    <input
                      autoFocus
                      className="input py-1.5"
                      placeholder="Nama folder baru, mis. April 2026"
                      value={newFolder}
                      onChange={(e) => setNewFolder(e.target.value)}
                    />
                    <button type="submit" className="btn-primary px-3" disabled={loading === "create"}>
                      Buat
                    </button>
                    <button type="button" className="btn-ghost" onClick={() => setNewFolder(null)}>
                      Batal
                    </button>
                  </form>
                ) : (
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => onChange(listing.path)}
                      disabled={disabled || selectedHere || !listing.writable}
                      title={listing.writable ? "" : "Tidak ada izin menulis ke folder ini"}
                    >
                      <FolderCheck className="h-4 w-4" />
                      {selectedHere ? "Folder ini dipilih" : "Gunakan folder ini"}
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setNewFolder("")}
                      disabled={disabled || !listing.writable}
                    >
                      <FolderPlus className="h-4 w-4" /> Folder baru
                    </button>
                    <span className="truncate text-xs text-slate-500">
                      Ruang kosong {formatBytes(listing.free_bytes)}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

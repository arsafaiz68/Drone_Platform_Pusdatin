import type {
  Batch,
  DownloadOptions,
  Entry,
  Health,
  LocalFolder,
  LocalFolderChild,
  LocalRoot,
  ParseResponse,
} from "../types";

// Modul Drone Video Downloader: semua endpoint di bawah /api/downloader (backend platform 127.0.0.1:8000).
// Default: alamat relatif (proxy Vite saat dev, atau backend yang sama saat build). Bisa diganti via VITE_API_BASE.
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      "Backend tidak dapat dihubungi. Jalankan start.bat (Drone Video Platform) — backend di http://127.0.0.1:8000.",
      0,
    );
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    let msg = `Permintaan gagal (HTTP ${res.status})`;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") msg = detail;
      else if (Array.isArray(detail))
        msg = detail
          .map((d: { msg?: string; loc?: unknown[] }) => `${(d.loc ?? []).join(".")}: ${d.msg ?? ""}`)
          .join("; ");
    }
    throw new ApiError(msg, res.status);
  }
  return data as T;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/api/downloader/health"),
  parse: (text: string) => request<ParseResponse>("/api/downloader/parse", post({ text })),
  previewNames: (entries: Entry[]) => request<{ entries: Entry[] }>("/api/downloader/naming/preview", post({ entries })),

  localRoots: () => request<{ roots: LocalRoot[]; default: string }>("/api/downloader/local/roots"),
  localFolder: (path: string) => request<LocalFolder>(`/api/downloader/local/folders?path=${encodeURIComponent(path)}`),
  localCreateFolder: (parent: string, name: string) =>
    request<LocalFolderChild>("/api/downloader/local/folders", post({ parent, name })),
  localPick: (initial?: string | null) => request<{ path: string | null }>("/api/downloader/local/pick", post({ initial })),
  localOpen: (path: string) => request<{ ok: boolean }>("/api/downloader/local/open", post({ path })),

  createBatch: (entries: Entry[], options: DownloadOptions, outputDir: string, reportDate: string | null) =>
    request<Batch>(
      "/api/downloader/batches",
      post({ entries, ...options, output_dir: outputDir, create_dir: true, report_date: reportDate }),
    ),
  listBatches: () => request<{ batches: Batch[] }>("/api/downloader/batches"),
  getBatch: (id: string) => request<Batch>(`/api/downloader/batches/${encodeURIComponent(id)}`),
  cancelBatch: (id: string) => request<Batch>(`/api/downloader/batches/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  retryBatch: (id: string, jobIds?: string[]) =>
    request<{ retried: number; batch: Batch }>(
      `/api/downloader/batches/${encodeURIComponent(id)}/retry`,
      post({ job_ids: jobIds ?? null }),
    ),
  cancelJob: (batchId: string, jobId: string) =>
    request(`/api/downloader/batches/${encodeURIComponent(batchId)}/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    }),
  retryJob: (batchId: string, jobId: string) =>
    request<{ retried: number; batch: Batch }>(
      `/api/downloader/batches/${encodeURIComponent(batchId)}/jobs/${encodeURIComponent(jobId)}/retry`,
      { method: "POST" },
    ),
};

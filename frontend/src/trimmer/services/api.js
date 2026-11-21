// Klien API modul Drone Video Trimmer (Drone Video Platform). Semua permintaan ke backend lokal (127.0.0.1).
const BASE = "/api";

async function request(method, path, body, opts = {}) {
  const init = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, init);
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    let msg = data && data.detail ? data.detail : `HTTP ${res.status}`;
    if (Array.isArray(msg)) msg = msg.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ");
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return data;
}

export function uploadWithProgress(path, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", BASE + path);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { data = xhr.responseText; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error((data && data.detail) || `HTTP ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error("Koneksi ke backend gagal"));
    xhr.send(formData);
  });
}

const get = (p) => request("GET", p);
const post = (p, b) => request("POST", p, b ?? {});
const patch = (p, b) => request("PATCH", p, b);
const del = (p) => request("DELETE", p);

export const api = {
  health: () => get("/health"),
  meta: () => get("/meta"),
  dashboard: () => get("/dashboard"),
  hardware: (refresh = false) => get(`/hardware?refresh=${refresh}`),
  settings: () => get("/settings"),
  updateSettings: (values) => patch("/settings", { values }),
  templates: () => get("/templates"),
  template: (code) => get(`/templates/${code}`),

  projects: () => get("/projects"),
  project: (id) => get(`/projects/${id}`),
  createProject: (b) => post("/projects", b),
  updateProject: (id, b) => patch(`/projects/${id}`, b),
  deleteProject: (id, deleteExports = false) => del(`/projects/${id}?delete_exports=${!!deleteExports}`),

  batches: (projectId) => get(`/batches${projectId ? `?project_id=${projectId}` : ""}`),
  batch: (id) => get(`/batches/${id}`),
  createBatch: (b) => post("/batches", b),
  updateBatch: (id, b) => patch(`/batches/${id}`, b),
  deleteBatch: (id, deleteExports = false) => del(`/batches/${id}?delete_exports=${!!deleteExports}`),
  batchZipSummary: (id) => get(`/batches/${id}/zip/summary`),
  batchZipUrl: (id) => `${BASE}/batches/${id}/zip`,
  projectZipSummary: (id) => get(`/projects/${id}/zip/summary`),
  projectZipUrl: (id) => `${BASE}/projects/${id}/zip`,
  startBatch: (id) => post(`/batches/${id}/start`),
  pauseBatch: (id) => post(`/batches/${id}/pause`),
  resumeBatch: (id) => post(`/batches/${id}/resume`),
  cancelBatch: (id) => post(`/batches/${id}/cancel`),
  markReviewed: (id) => post(`/batches/${id}/mark-reviewed`),
  items: (id) => get(`/batches/${id}/items`),
  report: (id) => get(`/batches/${id}/report`),
  uploadVideos: (id, files, onProgress) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    return uploadWithProgress(`/batches/${id}/videos`, fd, onProgress);
  },
  addPaths: (id, paths) => post(`/batches/${id}/videos/paths`, { paths }),
  removeVideo: (bid, vid) => del(`/batches/${bid}/videos/${vid}`),
  reorderVideos: (bid, ids) => post(`/batches/${bid}/videos/reorder`, { ids }),
  buildFinals: (bid) => post(`/batches/${bid}/final-videos`),
  batchFinals: (bid) => get(`/batches/${bid}/final-videos`),
  exportAll: (bid, includeIndividual) => post(`/batches/${bid}/export-all?include_individual=${!!includeIndividual}`),

  video: (id) => get(`/videos/${id}`),
  updateVideo: (id, b) => patch(`/videos/${id}`, b),
  analyze: (id) => post(`/videos/${id}/analyze`),
  setReviewed: (id, reviewed = true) => post(`/videos/${id}/reviewed?reviewed=${!!reviewed}`),
  verifyAll: (id) => post(`/videos/${id}/verify-all`),
  verifyAllBatch: (bid) => post(`/batches/${bid}/verify-all`),
  candidates: (id) => get(`/videos/${id}/candidates`),
  addCandidate: (id, b) => post(`/videos/${id}/candidates`, b),
  updateCandidate: (id, b) => patch(`/candidates/${id}`, b),
  resetCandidate: (id) => post(`/candidates/${id}/reset`),
  deleteCandidate: (id) => del(`/candidates/${id}`),
  streamUrl: (id, proxy = true) => `${BASE}/videos/${id}/stream?proxy=${proxy}`,
  thumbUrl: (id, t) => `${BASE}/videos/${id}/thumbnail?t=${t}`,

  createGroup: (b) => post("/location-groups", b),
  group: (id) => get(`/location-groups/${id}`),
  updateGroup: (id, b) => patch(`/location-groups/${id}`, b),
  deleteGroup: (id) => del(`/location-groups/${id}`),

  finals: (q = "") => get(`/final-videos${q}`),
  createFinal: (b) => post("/final-videos", b),
  final: (id) => get(`/final-videos/${id}`),
  updateFinal: (id, b) => patch(`/final-videos/${id}`, b),
  selectSegments: (id) => post(`/final-videos/${id}/select-segments`),
  addSegment: (id, b) => post(`/final-videos/${id}/segments`, b),
  updateSegment: (fid, sid, b) => patch(`/final-videos/${fid}/segments/${sid}`, b),
  deleteSegment: (fid, sid) => del(`/final-videos/${fid}/segments/${sid}`),
  resetSegment: (fid, sid) => post(`/final-videos/${fid}/segments/${sid}/reset`),
  replaceSegment: (fid, sid, candidate_id) => post(`/final-videos/${fid}/segments/${sid}/replace`, { candidate_id }),
  reorderSegments: (fid, ids) => post(`/final-videos/${fid}/reorder`, { ids }),
  setAllocations: (fid, allocations) => post(`/final-videos/${fid}/allocations`, { allocations }),
  exportFinal: (fid, kind = "final") => post(`/final-videos/${fid}/export`, { kind }),
  previewFinal: (fid) => post(`/final-videos/${fid}/preview`),
  exportInfo: (fid) => get(`/final-videos/${fid}/export-info`),

  exports: () => get("/exports"),
  exportJob: (id) => get(`/exports/${id}`),
  downloadUrl: (id, index) => `${BASE}/exports/${id}/download${index != null ? `?index=${index}` : ""}`,
  exportStreamUrl: (id) => `${BASE}/exports/${id}/stream`,
  openFolder: (path) => post("/open-folder", { path }),

  // integrasi Drone Video Downloader -> Trimmer
  downloads: () => get("/integration/downloads"),
  scanFolder: (path) => get(`/integration/folder?path=${encodeURIComponent(path)}`),
  importDownloads: (bid, body) => post(`/integration/batches/${bid}/import`, body),
  batchFromDownload: (body) => post("/integration/batch-from-download", body),
  pickFolder: (initial) => post("/downloader/local/pick", { initial: initial || null }),

  models: () => get("/models"),
  addModel: (b) => post("/models", b),
  updateModel: (id, b) => patch(`/models/${id}`, b),
  exportDataset: () => post("/dataset/export"),
};

// ---------------------------------------------------------------- format
export const fmtSec = (s) => {
  if (s == null || isNaN(s)) return "–";
  const sign = s < 0 ? "-" : "";
  s = Math.abs(s);
  const m = Math.floor(s / 60);
  const sec = s - m * 60;
  return `${sign}${m}:${sec.toFixed(1).padStart(4, "0")}`;
};
export const fmtDur = (s) => {
  if (s == null) return "–";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.round(s % 60);
  return h ? `${h}j ${m}m ${sec}d` : m ? `${m}m ${sec}d` : `${sec}d`;
};
export const fmtBytes = (b) => {
  if (!b) return "–";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return `${b.toFixed(i > 1 ? 1 : 0)} ${u[i]}`;
};
export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString("id-ID") : "–");
export const dirLabel = (d) => (d === "return" ? "Kembali" : d === "outbound" ? "Pergi" : "–");
export const pointLabel = (s) => (s.point_code ? `T${s.point_code}${s.direction === "return" ? "↩" : ""}` : "Isi");
export const infoSourceLabel = (src) => ({ downloader: "Drone Video Downloader", upload: "manual", path: "manual" }[src] || "manual");
export const tripLabel = (m) => (m === "round_trip" ? "Pergi dan kembali" : "Pergi saja");
export const parseTime = (v) => {
  // terima "75.5", "1:15.5", atau "0:01:15"
  if (typeof v === "number") return v;
  const parts = String(v).trim().split(":").map(Number);
  if (parts.some(isNaN)) return NaN;
  return parts.reduce((acc, x) => acc * 60 + x, 0);
};

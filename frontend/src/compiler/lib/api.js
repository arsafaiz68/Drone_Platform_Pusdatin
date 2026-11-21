// Klien API Drone Video Compiler (backend lokal FastAPI, prefix /api/compiler).
const BASE = "/api/compiler";

async function req(method, path, body) {
  const r = await fetch(BASE + path, {
    method, headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const j = await r.json(); msg = j.detail || msg; } catch { /* abaikan */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.status === 204 ? null : r.json();
}

export const api = {
  system: () => req("GET", "/system"),
  projects: () => req("GET", "/projects"),
  createProject: (name, settings) => req("POST", "/projects", { name, settings }),
  project: (id) => req("GET", `/projects/${id}`),
  saveProject: (p) => req("PUT", `/projects/${p.id}`, p),
  renameProject: (id, name) => req("POST", `/projects/${id}/rename`, { name }),
  duplicateProject: (id, name) => req("POST", `/projects/${id}/duplicate`, name ? { name } : undefined),
  deleteProject: (id) => req("DELETE", `/projects/${id}`),
  importProject: (data) => req("POST", "/projects/import", data),
  registerPaths: (paths) => req("POST", "/media/register", { paths }),
  mediaStatus: (ids) => req("POST", "/media/status", { ids }),
  forgetMedia: (id, projectId) => req("DELETE", `/media/${id}?project_id=${encodeURIComponent(projectId || "")}`),
  checkMedia: (media) => req("POST", "/media/check", { media: media.map((m) => ({ id: m.id, name: m.name, path: m.path, kind: m.kind, size: m.size })) }),
  relinkMedia: (mediaId, path, kind) => req("POST", "/media/relink", { media_id: mediaId, path, kind }),
  findMedia: (folder, items, recursive = true) => req("POST", "/media/find", { folder, items, recursive }),
  pickFile: (initial, name) => req("POST", "/pick-file", { initial, name }),
  pickFolder: (initial) => req("POST", "/pick-folder", { initial }),
  openLocation: (path) => req("POST", "/open-location", { path }),
  estimate: (id, exp) => req("POST", `/projects/${id}/estimate`, { export: exp }),
  render: (id, exp, textImages) => req("POST", `/projects/${id}/render`, { export: exp, text_images: textImages }),
  renders: (id) => req("GET", `/projects/${id}/renders`),
  renderJob: (jid) => req("GET", `/renders/${jid}`),
  cancelRender: (jid) => req("POST", `/renders/${jid}/cancel`),
  openFolder: (path) => fetch("/api/open-folder", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) }),
  fileUrl: (mid) => `${BASE}/media/${mid}/file`,
  thumbUrl: (mid) => `${BASE}/media/${mid}/thumb`,
  waveUrl: (mid) => `${BASE}/media/${mid}/wave`,
  downloadUrl: (jid) => `${BASE}/renders/${jid}/download`,
  streamUrl: (jid) => `${BASE}/renders/${jid}/stream`,

  /** Unggah satu file ke backend LOKAL (streaming, dengan progres). */
  upload(file, filename, onProgress) {
    return new Promise((resolve, reject) => {
      const x = new XMLHttpRequest();
      x.open("POST", `${BASE}/media/upload?filename=${encodeURIComponent(filename || file.name)}`);
      x.setRequestHeader("Content-Type", "application/octet-stream");
      x.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
      x.onload = () => {
        let j = null;
        try { j = JSON.parse(x.responseText); } catch { /* abaikan */ }
        if (x.status >= 200 && x.status < 300) resolve(j);
        else reject(new Error((j && j.detail) || `Unggah gagal (${x.status})`));
      };
      x.onerror = () => reject(new Error("Koneksi ke backend lokal terputus."));
      x.send(file);
    });
  },
};

/** SVG dikonversi ke PNG di browser (FFmpeg umumnya tidak dapat membaca SVG). */
export async function svgToPng(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error("SVG tidak dapat dibaca")); i.src = url; });
    let w = img.naturalWidth || 1024, h = img.naturalHeight || 1024;
    const k = 2048 / Math.max(w, h);
    if (k > 1) { w *= k; h *= k; }
    const cv = document.createElement("canvas");
    cv.width = Math.round(w); cv.height = Math.round(h);
    cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
    const blob = await new Promise((res) => cv.toBlob(res, "image/png"));
    return new File([blob], file.name.replace(/\.svg$/i, "") + ".png", { type: "image/png" });
  } finally { URL.revokeObjectURL(url); }
}

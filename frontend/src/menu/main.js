import "./menu.css";
import { initTheme } from "../shared/theme.js";

initTheme();

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function getJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function status() {
  const el = $("status");
  try {
    const [core, dl] = await Promise.all([getJson("/api/health"), getJson("/api/downloader/health").catch(() => null)]);
    const parts = [
      "Backend aktif",
      core.ffmpeg ? "FFmpeg ✓" : "FFmpeg ✗",
      core.mode === "cuda" ? "GPU (CUDA)" : "CPU",
      dl && dl.yt_dlp_version ? `yt-dlp ${dl.yt_dlp_version}` : "yt-dlp ✗",
    ];
    el.innerHTML = `<span class="dot ok"></span>${esc(parts.join(" · "))}`;
  } catch {
    el.innerHTML = `<span class="dot err"></span>Backend tidak terhubung — jalankan start.bat`;
  }
}

async function recent() {
  const el = $("recent");
  try {
    const list = (await getJson("/api/integration/downloads")).slice(0, 4);
    if (!list.length) {
      el.innerHTML = `<p class="muted">Belum ada unduhan. Mulai dari <a href="/downloader/">Drone Video Downloader</a>.</p>`;
      return;
    }
    el.innerHTML = list.map((b) => {
      const when = b.created_at ? new Date(b.created_at).toLocaleString("id-ID") : "–";
      const locs = [...new Set(b.videos.map((v) => v.fields.location_name).filter(Boolean))].slice(0, 4).join(", ");
      const action = b.available
        ? `<a href="/trimmer/#/batches?import=${encodeURIComponent(b.id)}">Proses ${b.available} video di Trimmer →</a>`
        : `<span class="muted">tidak ada file tersedia</span>`;
      return `<div class="recent-item"><div><b>${esc(when)}</b> · laporan ${esc(b.report_date || "–")}
        <div class="meta">${esc(locs || "–")} · ${esc(b.output_dir || "")}</div></div>${action}</div>`;
    }).join("");
  } catch {
    el.innerHTML = `<p class="muted">Riwayat unduhan belum dapat dimuat.</p>`;
  }
}

status();
recent();
setInterval(status, 15000);

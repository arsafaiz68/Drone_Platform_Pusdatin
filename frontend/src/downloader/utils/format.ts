export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatSpeed(bps: number | null | undefined): string {
  if (!bps) return "";
  return `${formatBytes(bps)}/s`;
}

export function formatEta(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || sec < 0) return "";
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h) return `${h}j ${m}m`;
  if (m) return `${m}m ${r}d`;
  return `${r}d`;
}

export function formatDateId(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

/** Menghitung URL YouTube secara cepat di sisi klien (indikator sebelum parsing). */
export function countYoutubeUrls(text: string): number {
  const re = /(?:https?:\/\/)?(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)\/[^\s*]+/gi;
  return (text.match(re) ?? []).length;
}

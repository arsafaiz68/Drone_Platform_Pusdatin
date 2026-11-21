import { Download, Film, LayoutGrid, Scissors, Settings } from "lucide-react";
import type { Health } from "../types";

interface Props {
  backendOnline: boolean | null;
  health: Health | null;
  onOpenSettings: () => void;
}

function Dot({ ok }: { ok: boolean | null }) {
  return (
    <span className={`h-2 w-2 rounded-full ${ok === null ? "bg-slate-400" : ok ? "bg-[#34c759]" : "bg-[#ff3b30]"}`} />
  );
}

export default function Header({ backendOnline, health, onOpenSettings }: Props) {
  const ffmpegOk = backendOnline ? (health?.ffmpeg ?? null) : null;
  const ytOk = backendOnline ? !!health?.yt_dlp_version : null;
  return (
    <header className="sticky top-3 z-30 mx-auto mt-3 max-w-7xl px-4">
      <div className="glass flex items-center justify-between gap-4 rounded-[26px] px-5 py-3 text-slate-900">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-[12px] bg-gradient-to-br from-[#5ac8fa] to-[#007aff] text-white shadow-[0_4px_12px_rgba(0,122,255,0.35)]">
            <Download className="h-5 w-5" />
          </div>
          <div>
            <h1 className="whitespace-nowrap text-[17px] font-semibold leading-tight tracking-tight">Drone Video Downloader</h1>
            <p className="hidden text-xs text-slate-500 2xl:block">Drone Video Platform · laporan WhatsApp → video YouTube di folder lokal</p>
          </div>
        </div>
        <nav className="flex shrink-0 items-center gap-1 rounded-full bg-[rgba(118,118,128,0.12)] p-1 text-sm font-medium">
          <a href="/" className="flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-slate-700 hover:bg-white/70">
            <LayoutGrid className="h-4 w-4 text-[#007aff]" /> Menu utama
          </a>
          <span className="flex items-center gap-1.5 whitespace-nowrap rounded-full bg-white px-3 py-1.5 text-slate-900 shadow-[0_3px_8px_rgba(0,0,0,0.12)]">
            <Download className="h-4 w-4 text-[#007aff]" /> Downloader
          </span>
          <a href="/trimmer/" className="flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-slate-700 hover:bg-white/70">
            <Scissors className="h-4 w-4 text-[#007aff]" /> Drone Video Trimmer
          </a>
          <a href="/compiler/" className="flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-slate-700 hover:bg-white/70">
            <Film className="h-4 w-4 text-[#007aff]" /> Compiler
          </a>
        </nav>
        <div className="flex shrink-0 items-center gap-2">
          <span className="badge whitespace-nowrap bg-[rgba(118,118,128,0.12)] text-slate-700">
            <Dot ok={backendOnline} />
            {backendOnline === false ? "Backend offline" : backendOnline ? "Backend aktif" : "Memeriksa…"}
          </span>
          <span className="badge whitespace-nowrap bg-[rgba(118,118,128,0.12)] text-slate-700" title={health?.ffmpeg_path ?? "FFmpeg tidak ditemukan"}>
            <Dot ok={ffmpegOk} /> FFmpeg
          </span>
          <span className="badge whitespace-nowrap bg-[rgba(118,118,128,0.12)] text-slate-700" title={health?.yt_dlp_version ?? "yt-dlp belum terpasang"}>
            <Dot ok={ytOk} /> yt-dlp
          </span>
          <button
            type="button"
            onClick={onOpenSettings}
            className="ml-1 rounded-full p-2 text-[#007aff] hover:bg-[rgba(118,118,128,0.12)]"
            title="Pengaturan & riwayat"
            aria-label="Pengaturan"
          >
            <Settings className="h-5 w-5" />
          </button>
        </div>
      </div>
    </header>
  );
}

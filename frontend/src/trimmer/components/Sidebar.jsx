const NAV = [
  { to: "/", key: "", label: "Dashboard", icon: "M3 13h8V3H3zm10 8h8V11h-8zM3 21h8v-6H3zm10-18v6h8V3z" },
  { to: "/projects", key: "projects", label: "Proyek", icon: "M3 7h6l2 2h10v10H3z" },
  { to: "/batches", key: "batches", label: "Batch Processing", icon: "M4 6h16M4 12h16M4 18h10" },
  { to: "/templates", key: "templates", label: "Template Pemantauan", icon: "M5 19l4-6 3 4 3-5 4 7z M12 5a2 2 0 1 0 0 .1" },
  { to: "/review", key: "review", label: "Review dan Editing", icon: "M4 5h16v10H4z M8 19h8" },
  { to: "/models", key: "models", label: "Model AI", icon: "M12 3l8 4v10l-8 4-8-4V7z M12 12l8-5 M12 12v9 M12 12L4 7" },
  { to: "/exports", key: "exports", label: "Riwayat Ekspor", icon: "M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" },
  { to: "/settings", key: "settings", label: "Pengaturan", icon: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M3 12h2m14 0h2M12 3v2m0 14v2" },
];

export default function Sidebar({ current, health }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo">
          {/* logo modul Drone Video Trimmer (sama dengan kartu Trimmer di menu utama) */}
          <svg viewBox="0 0 32 32" width="32" height="32" aria-label="Drone Video Trimmer">
            <defs><linearGradient id="trLogoGrad" x1="0.2" y1="0" x2="0.8" y2="1">
              <stop offset="0" stopColor="#64d2ff" /><stop offset="0.45" stopColor="#30b0c7" /><stop offset="1" stopColor="#0e7490" />
            </linearGradient></defs>
            <rect width="32" height="32" rx="9" fill="url(#trLogoGrad)" />
            <g transform="translate(4 4)" fill="none" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="6" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12" />
            </g></svg>
        </div>
        <div>
          <div className="brand-name">Drone Video Trimmer</div>
          <div className="brand-sub">Drone Video Platform</div>
        </div>
      </div>
      <nav>
        <a href="/" className="nav-item nav-platform">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round"><path d="M3 11l9-7 9 7v9H3z M9 20v-6h6v6" /></svg>
          <span>Menu utama</span>
        </a>
        <a href="/downloader/" className="nav-item nav-platform">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" /></svg>
          <span>Drone Video Downloader</span>
        </a>
        <a href="/compiler/" className="nav-item nav-platform">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round"><path d="M3 4h18v5H3zM3 11h11v4H3zM8 17h13v3H8z" /></svg>
          <span>Drone Video Compiler</span>
        </a>
        <div className="nav-sep">Drone Video Trimmer</div>
        {NAV.map((n) => (
          <a key={n.to} href={`#${n.to}`} className={`nav-item ${current === n.key ? "active" : ""}`}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"
              strokeLinecap="round" strokeLinejoin="round"><path d={n.icon} /></svg>
            <span>{n.label}</span>
          </a>
        ))}
      </nav>
      <div className="sidebar-foot">
        {health ? (
          <>
            <div><span className={`dot ${health.mode === "cuda" ? "dot-ok" : "dot-warn"}`} />
              {health.mode === "cuda" ? "GPU (CUDA)" : "CPU"}</div>
            <div className="muted small">FFmpeg {health.ffmpeg ? "✓" : "✗"} · Lokal / offline</div>
          </>
        ) : <div className="muted small"><span className="dot dot-err" />Backend tidak terhubung</div>}
      </div>
    </aside>
  );
}

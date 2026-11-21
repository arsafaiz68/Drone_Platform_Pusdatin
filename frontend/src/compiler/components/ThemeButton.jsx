// Tombol Terang / Gelap untuk Compiler (pilihan sama dengan menu utama, Downloader, dan Trimmer).
import { useEffect, useState } from "react";
import { currentTheme, onThemeChange, setTheme } from "../../shared/theme.js";

export default function ThemeButton() {
  const [t, setT] = useState(currentTheme());
  useEffect(() => onThemeChange(setT), []);
  return (
    <div className="theme-seg" role="group" aria-label="Tema tampilan">
      <button className={t === "light" ? "on" : ""} onClick={() => setTheme("light")} title="Mode terang">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="4.2" /><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6" /></svg>
        <span>Terang</span></button>
      <button className={t === "dark" ? "on" : ""} onClick={() => setTheme("dark")} title="Mode gelap">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M20.4 14.6A8.6 8.6 0 0 1 9.4 3.6a.6.6 0 0 0-.8-.7A9.6 9.6 0 1 0 21.1 15.4a.6.6 0 0 0-.7-.8Z" /></svg>
        <span>Gelap</span></button>
    </div>
  );
}

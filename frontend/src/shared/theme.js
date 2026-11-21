/**
 * Mode terang / gelap untuk seluruh Drone Video Platform (menu utama, Downloader, Trimmer, Compiler).
 * Pilihan disimpan di localStorage ("dvp-theme") sehingga berlaku di semua halaman.
 * Tombol mengambang (pojok kanan bawah) untuk berganti mode.
 */
const KEY = "dvp-theme";

const SUN = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6"/></svg>';
const MOON = '<svg viewBox="0 0 24 24" width="21" height="21" fill="currentColor"><path d="M20.4 14.6A8.6 8.6 0 0 1 9.4 3.6a.6.6 0 0 0-.8-.7A9.6 9.6 0 1 0 21.1 15.4a.6.6 0 0 0-.7-.8Z"/></svg>';

let fallback = "light"; // bawaan: mode terang (Compiler memakai gelap bila belum pernah dipilih)

export function currentTheme() {
  try {
    const t = localStorage.getItem(KEY);
    if (t === "dark" || t === "light") return t;
  } catch { /* penyimpanan tidak tersedia */ }
  return fallback;
}

/** Berlangganan perubahan tema (untuk tombol di dalam komponen React). */
export function onThemeChange(cb) {
  const f = () => cb(currentTheme());
  window.addEventListener("dvp-theme", f);
  return () => window.removeEventListener("dvp-theme", f);
}

export function toggleTheme() {
  const root = document.documentElement;
  root.classList.add("dvp-theme-anim");
  setTheme(currentTheme() === "dark" ? "light" : "dark");
  setTimeout(() => root.classList.remove("dvp-theme-anim"), 350);
}

export function applyTheme(t) {
  const root = document.documentElement;
  root.dataset.theme = t;
  root.style.colorScheme = t;
  const btn = document.getElementById("dvp-theme-toggle");
  if (btn) {
    btn.innerHTML = t === "dark" ? SUN : MOON;
    const label = t === "dark" ? "Ganti ke mode terang" : "Ganti ke mode gelap";
    btn.title = label;
    btn.setAttribute("aria-label", label);
  }
  window.dispatchEvent(new Event("dvp-theme"));
}

export function setTheme(t) {
  try { localStorage.setItem(KEY, t); } catch { /* abaikan */ }
  applyTheme(t);
}

const CSS = `
#dvp-theme-toggle { position: fixed; right: 20px; bottom: 20px; z-index: 9999; width: 52px; height: 52px; border-radius: 50%;
  display: grid; place-items: center; cursor: pointer; border: 1px solid rgba(255,255,255,.75);
  background: rgba(255,255,255,.72); color: #1c1c1e; -webkit-backdrop-filter: saturate(180%) blur(24px); backdrop-filter: saturate(180%) blur(24px);
  box-shadow: 0 1px 1px rgba(0,0,0,.04), 0 10px 30px rgba(31,45,90,.18), inset 0 1px 0 rgba(255,255,255,.9);
  transition: transform .18s cubic-bezier(.2,.8,.2,1), background .25s, color .25s; }
#dvp-theme-toggle:hover { transform: scale(1.06); }
#dvp-theme-toggle:active { transform: scale(.94); }
#dvp-theme-toggle:focus-visible { outline: 3px solid rgba(0,122,255,.45); outline-offset: 3px; }
html[data-theme="dark"] #dvp-theme-toggle { background: rgba(44,44,46,.78); color: #ffd60a; border-color: rgba(255,255,255,.12);
  box-shadow: 0 10px 30px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.08); }
html.dvp-theme-anim, html.dvp-theme-anim * { transition: background-color .3s ease, color .3s ease, border-color .3s ease !important; }
@media print { #dvp-theme-toggle { display: none; } }
`;

/**
 * @param {{floating?: boolean, defaultTheme?: "light"|"dark"}} [opts]
 *   floating=false: tanpa tombol mengambang (halaman menyediakan tombolnya sendiri, mis. toolbar Compiler).
 */
export function initTheme(opts = {}) {
  const { floating = true, defaultTheme = "light" } = opts;
  fallback = defaultTheme;
  applyTheme(currentTheme());
  if (!document.getElementById("dvp-theme-style")) {
    const st = document.createElement("style");
    st.id = "dvp-theme-style";
    st.textContent = CSS;
    document.head.appendChild(st);
  }
  if (floating && !document.getElementById("dvp-theme-toggle")) {
    const btn = document.createElement("button");
    btn.id = "dvp-theme-toggle";
    btn.type = "button";
    btn.addEventListener("click", toggleTheme);
    document.body.appendChild(btn);
    applyTheme(currentTheme());
  }
  // sinkron antar tab / halaman yang terbuka bersamaan
  window.addEventListener("storage", (e) => { if (e.key === KEY) applyTheme(currentTheme()); });
}

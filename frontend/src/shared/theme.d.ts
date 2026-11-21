export type Theme = "light" | "dark";
export function currentTheme(): Theme;
export function applyTheme(t: Theme): void;
export function setTheme(t: Theme): void;
export function initTheme(opts?: { floating?: boolean; defaultTheme?: Theme }): void;
export function toggleTheme(): void;
export function onThemeChange(cb: (t: Theme) => void): () => void;

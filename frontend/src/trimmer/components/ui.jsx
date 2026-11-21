import { createContext, useCallback, useContext, useEffect, useState } from "react";

// ---------------------------------------------------------------- status badge
const STATUS_TONE = {
  waiting: "muted", analyzing: "info", analyzed: "info", processing: "info", review: "warn",
  done: "ok", failed: "err", cancelled: "muted",
  draft: "muted", queued: "info", running: "info", paused: "warn", completed: "ok",
  exporting: "info", exported: "ok", ready: "ok",
};
export function StatusBadge({ status, label }) {
  return <span className={`badge badge-${STATUS_TONE[status] || "muted"}`}>{label || status}</span>;
}

export function Tag({ tone = "muted", children, title }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

// ---------------------------------------------------------------- progress
export function ProgressBar({ value = 0, tone = "info", label, small }) {
  const pct = Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
  return (
    <div className={`progress ${small ? "progress-sm" : ""}`} title={`${pct}%`}>
      <div className={`progress-fill tone-${tone}`} style={{ width: `${pct}%` }} />
      {label !== false && !small && <span className="progress-label">{label ?? `${pct}%`}</span>}
    </div>
  );
}

// ---------------------------------------------------------------- card / stat
export function Card({ title, actions, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          {title && <h3>{title}</h3>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function Notice({ tone = "info", title, children }) {
  return (
    <div className={`notice notice-${tone}`}>
      {title && <strong>{title}</strong>}
      <div>{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------- modal
export function Modal({ open, title, onClose, children, footer, wide }) {
  useEffect(() => {
    if (!open) return undefined;
    const on = (e) => e.key === "Escape" && onClose && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose && onClose()}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} role="dialog" aria-modal="true">
        <header className="modal-head">
          <h3>{title}</h3>
          <button className="btn-icon" onClick={onClose} aria-label="Tutup">×</button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  );
}

const ConfirmCtx = createContext(null);
const ToastCtx = createContext(null);

export function UIProvider({ children }) {
  const [confirm, setConfirm] = useState(null);
  const [toasts, setToasts] = useState([]);
  const ask = useCallback((opts) => new Promise((resolve) => setConfirm({ ...opts, resolve })), []);
  const toast = useCallback((message, tone = "ok") => {
    const id = Math.random();
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "err" ? 7000 : 3500);
  }, []);
  const close = (v) => { confirm.resolve(v); setConfirm(null); };
  return (
    <ConfirmCtx.Provider value={ask}>
      <ToastCtx.Provider value={toast}>
        {children}
        <Modal open={!!confirm} title={confirm?.title || "Konfirmasi"} onClose={() => close(false)}
          footer={<>
            <button className="btn" onClick={() => close(false)}>Batal</button>
            <button className={`btn ${confirm?.danger ? "btn-danger" : "btn-primary"}`} onClick={() => close(true)}>
              {confirm?.confirmText || "Ya, lanjutkan"}
            </button>
          </>}>
          <p>{confirm?.message}</p>
        </Modal>
        <div className="toasts">
          {toasts.map((t) => <div key={t.id} className={`toast toast-${t.tone}`}>{t.message}</div>)}
        </div>
      </ToastCtx.Provider>
    </ConfirmCtx.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmCtx);
export const useToast = () => useContext(ToastCtx);

/** Bungkus aksi async: tampilkan toast sukses/gagal. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (fn, okMsg) => {
    setBusy(true);
    try {
      const r = await fn();
      if (okMsg) toast(okMsg, "ok");
      return r;
    } catch (e) {
      toast(e.message || String(e), "err");
      return undefined;
    } finally {
      setBusy(false);
    }
  }, [toast]);
  return [run, busy];
}

// ---------------------------------------------------------------- form
export function Field({ label, hint, children, error }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </label>
  );
}

export function Segmented({ value, options, onChange, disabled }) {
  return (
    <div className="segmented" role="radiogroup">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} disabled={disabled}
          className={value === o.value ? "active" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Loading({ text = "Memuat…" }) {
  return <div className="loading"><span className="spinner" /> {text}</div>;
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <Notice tone="err" title="Terjadi kesalahan">
      {error} {onRetry && <button className="btn btn-sm" onClick={onRetry}>Coba lagi</button>}
    </Notice>
  );
}

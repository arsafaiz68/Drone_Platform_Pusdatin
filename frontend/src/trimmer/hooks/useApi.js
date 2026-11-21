import { useCallback, useEffect, useRef, useState } from "react";

/** Muat data sekali (dan saat deps berubah). Mengembalikan {data, error, loading, reload, setData}. */
export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const d = await fnRef.current();
      setData(d);
      setError(null);
      return d;
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, deps);
  return { data, error, loading, reload, setData };
}

/** Polling berkala selama `active` bernilai true. */
export function usePolling(fn, intervalMs, active = true) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (!active) return undefined;
    let stop = false;
    const tick = async () => {
      if (stop) return;
      try { await fnRef.current(); } catch { /* abaikan */ }
    };
    const h = setInterval(tick, intervalMs);
    return () => { stop = true; clearInterval(h); };
  }, [intervalMs, active]);
}

/** Router berbasis hash sederhana: #/batches/3?video=5 */
export function useHashRoute() {
  const parse = () => {
    const raw = window.location.hash.replace(/^#/, "") || "/";
    const [path, qs] = raw.split("?");
    const parts = path.split("/").filter(Boolean);
    const query = Object.fromEntries(new URLSearchParams(qs || ""));
    return { path, parts, query };
  };
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const navigate = (to) => { window.location.hash = to; };

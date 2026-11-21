// State editor: proyek + riwayat undo/redo + status simpan.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const MAX_HISTORY = 150;

export function useEditor(projectId) {
  const [project, setProject] = useState(null);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const past = useRef([]);
  const future = useRef([]);
  const [, force] = useState(0);
  const projRef = useRef(null);
  projRef.current = project;

  useEffect(() => {
    let alive = true;
    setProject(null); setError(null);
    api.project(projectId).then((p) => { if (alive) { past.current = []; future.current = []; setProject(p); setDirty(false); } })
      .catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [projectId]);

  /** Perubahan permanen (masuk riwayat undo). `fromSnapshot` dipakai setelah drag. */
  const commit = useCallback((updater, fromSnapshot) => {
    const cur = projRef.current;
    const next = typeof updater === "function" ? updater(cur) : updater;
    if (!next || next === cur && !fromSnapshot) return;
    past.current.push(fromSnapshot || cur);
    if (past.current.length > MAX_HISTORY) past.current.shift();
    future.current = [];
    projRef.current = next;
    setProject(next); setDirty(true); force((x) => x + 1);
  }, []);

  /** Perubahan sementara (saat drag) — tidak masuk riwayat sampai commit. */
  const live = useCallback((updater) => {
    const cur = projRef.current;
    const next = typeof updater === "function" ? updater(cur) : updater;
    projRef.current = next;
    setProject(next);
  }, []);

  const undo = useCallback(() => {
    if (!past.current.length) return;
    future.current.push(projRef.current);
    const prev = past.current.pop();
    projRef.current = prev; setProject(prev); setDirty(true); force((x) => x + 1);
  }, []);

  const redo = useCallback(() => {
    if (!future.current.length) return;
    past.current.push(projRef.current);
    const nxt = future.current.pop();
    projRef.current = nxt; setProject(nxt); setDirty(true); force((x) => x + 1);
  }, []);

  /** Pembaruan metadata media (thumbnail/proxy) tidak dianggap suntingan. */
  const patchMedia = useCallback((byId) => {
    const cur = projRef.current;
    if (!cur) return;
    let changed = false;
    const media = cur.media.map((m) => {
      const n = byId[m.id];
      if (n && (n.thumb !== m.thumb || n.wave !== m.wave || n.proxy !== m.proxy)) { changed = true; return { ...m, ...n }; }
      return m;
    });
    if (changed) { const next = { ...cur, media }; projRef.current = next; setProject(next); }
  }, []);

  const save = useCallback(async (override) => {
    const cur = projRef.current;
    if (!cur) return null;
    setSaving(true);
    try {
      const saved = await api.saveProject(override || cur);
      if (projRef.current === cur && !override) setDirty(false);
      return saved;
    } finally { setSaving(false); }
  }, []);

  return { project, error, dirty, saving, commit, live, undo, redo, save, patchMedia,
    canUndo: past.current.length > 0, canRedo: future.current.length > 0, getProject: () => projRef.current };
}

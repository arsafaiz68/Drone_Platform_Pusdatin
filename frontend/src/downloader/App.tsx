import { AlertCircle, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import BatchSummary from "./components/BatchSummary";
import DownloadQueue from "./components/DownloadQueue";
import DownloadSettings from "./components/DownloadSettings";
import Header from "./components/Header";
import LocalFolderBrowser from "./components/LocalFolderBrowser";
import PreviewTable from "./components/PreviewTable";
import ReportInput from "./components/ReportInput";
import SettingsPanel from "./components/SettingsPanel";
import { api } from "./services/api";
import { BatchSocket, type SocketState } from "./services/websocket";
import type { Batch, DownloadOptions, Entry, Health, WsMessage } from "./types";

const LS_KEY = "byd-state-v2";

interface Saved {
  text?: string;
  outputDir?: string | null;
  options?: DownloadOptions;
  batchId?: string | null;
}

function loadSaved(): Saved {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) ?? "{}") as Saved;
  } catch {
    return {};
  }
}

function save(s: Saved) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ ...loadSaved(), ...s }));
  } catch {
    /* penyimpanan browser tidak tersedia */
  }
}

const DEFAULT_OPTIONS: DownloadOptions = {
  quality: 1080,
  parallel: 3,
  conflict_behavior: "rename",
};

export default function App() {
  const saved = useRef(loadSaved()).current;

  const [health, setHealth] = useState<Health | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [text, setText] = useState(saved.text ?? "");
  const [parsing, setParsing] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [globalWarnings, setGlobalWarnings] = useState<string[]>([]);
  const [reportDate, setReportDate] = useState<string | null>(null);
  const [parsedOnce, setParsedOnce] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [outputDir, setOutputDir] = useState<string | null>(saved.outputDir ?? null);
  const [options, setOptions] = useState<DownloadOptions>(saved.options ?? DEFAULT_OPTIONS);
  const [starting, setStarting] = useState(false);

  const [batch, setBatch] = useState<Batch | null>(null);
  const [socketState, setSocketState] = useState<SocketState>("closed");
  const [busy, setBusy] = useState(false);
  const socketRef = useRef<BatchSocket | null>(null);

  const showError = (e: unknown) => setToast(e instanceof Error ? e.message : String(e));

  // ---------------------------------------------------------- status sistem
  const refreshHealth = useCallback(async () => {
    try {
      const h = await api.health();
      setHealth(h);
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  }, []);

  useEffect(() => {
    void refreshHealth();
    const t = window.setInterval(() => void refreshHealth(), 15000);
    return () => window.clearInterval(t);
  }, [refreshHealth]);

  useEffect(() => save({ text }), [text]);
  useEffect(() => save({ outputDir }), [outputDir]);
  useEffect(() => save({ options }), [options]);

  // ---------------------------------------------------------- parsing
  async function handleParse() {
    setParsing(true);
    try {
      const r = await api.parse(text);
      setEntries(r.entries);
      setGlobalWarnings(r.warnings);
      setReportDate(r.report_date);
      setParsedOnce(true);
    } catch (e) {
      showError(e);
    } finally {
      setParsing(false);
    }
  }

  function handleReset() {
    setText("");
    setEntries([]);
    setGlobalWarnings([]);
    setReportDate(null);
    setParsedOnce(false);
  }

  // Validasi ulang & penamaan ulang (debounce) setelah metadata diedit.
  const editVersion = useRef(0);
  const debounceRef = useRef<number | null>(null);
  function handleEntriesChange(next: Entry[]) {
    setEntries(next);
    const version = ++editVersion.current;
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(async () => {
      setRefreshing(true);
      try {
        const r = await api.previewNames(next);
        if (version !== editVersion.current) return; // ada editan yang lebih baru
        const byId = new Map(r.entries.map((e) => [e.id, e]));
        setEntries((cur) =>
          cur.map((e) => {
            const s = byId.get(e.id);
            if (!s) return e;
            return {
              ...e,
              filename: e.filename_manual ? e.filename : s.filename,
              url: s.url,
              video_id: s.video_id,
              url_valid: s.url_valid,
              url_error: s.url_error,
              warnings: s.warnings,
            };
          }),
        );
      } catch (e) {
        showError(e);
      } finally {
        if (version === editVersion.current) setRefreshing(false);
      }
    }, 400);
  }

  // ---------------------------------------------------------- monitoring
  const applyMessage = useCallback((msg: WsMessage) => {
    if (msg.type === "snapshot") {
      setBatch(msg.batch);
    } else if (msg.type === "job") {
      setBatch((b) => {
        if (!b || b.id !== msg.batch_id) return b;
        const jobs = (b.jobs ?? []).map((j) => (j.id === msg.job.id ? msg.job : j));
        return { ...b, jobs, summary: msg.summary, status: msg.status };
      });
    } else if (msg.type === "batch") {
      setBatch((b) => (b && b.id === msg.batch_id ? { ...b, summary: msg.summary, status: msg.status } : b));
      socketRef.current?.requestSnapshot();
    }
  }, []);

  const attachBatch = useCallback(
    (id: string) => {
      socketRef.current?.close();
      socketRef.current = new BatchSocket(id, applyMessage, setSocketState);
      save({ batchId: id });
    },
    [applyMessage],
  );

  useEffect(() => {
    if (saved.batchId) {
      api
        .getBatch(saved.batchId)
        .then((b) => {
          setBatch(b);
          attachBatch(b.id);
        })
        .catch(() => save({ batchId: null }));
    }
    return () => socketRef.current?.close();
  }, [attachBatch, saved.batchId]);

  // Cadangan: polling jika WebSocket terputus saat batch berjalan.
  useEffect(() => {
    if (!batch || batch.status !== "running" || socketState === "open") return;
    const t = window.setInterval(() => {
      api.getBatch(batch.id).then(setBatch).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(t);
  }, [batch, socketState]);

  async function handleStart() {
    setStarting(true);
    try {
      if (!outputDir) throw new Error("Folder tujuan belum dipilih.");
      const b = await api.createBatch(entries, options, outputDir, reportDate);
      setBatch(b);
      attachBatch(b.id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      showError(e);
    } finally {
      setStarting(false);
    }
  }

  async function withBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  }

  async function openBatch(id: string) {
    try {
      const b = await api.getBatch(id);
      setBatch(b);
      attachBatch(id);
    } catch (e) {
      showError(e);
    }
  }

  function newBatch() {
    socketRef.current?.close();
    socketRef.current = null;
    setBatch(null);
    save({ batchId: null });
  }

  const validCount = entries.filter((e) => e.url_valid).length;
  const invalidCount = entries.length - validCount;
  const batchRunning = batch?.status === "running";

  return (
    <div className="min-h-screen">
      <Header backendOnline={backendOnline} health={health} onOpenSettings={() => setSettingsOpen(true)} />

      {backendOnline === false && (
        <div className="mx-auto mt-4 max-w-7xl px-6">
          <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle className="h-4 w-4" />
            Backend tidak dapat dihubungi. Jalankan start.bat (Drone Video Platform) lalu buka http://127.0.0.1:8000.
          </div>
        </div>
      )}

      <main className="mx-auto max-w-7xl space-y-5 px-6 py-6">
        {batch && (
          <>
            <BatchSummary
              batch={batch}
              socketState={socketState}
              busy={busy}
              onCancel={() => withBusy(async () => setBatch(await api.cancelBatch(batch.id)))}
              onRetryFailed={() => withBusy(async () => setBatch((await api.retryBatch(batch.id)).batch))}
              onNewBatch={newBatch}
              onOpenFolder={() => withBusy(() => api.localOpen(batch.output_dir))}
            />
            <DownloadQueue
              jobs={batch.jobs ?? []}
              onCancelJob={(jid) => withBusy(() => api.cancelJob(batch.id, jid))}
              onRetryJob={(jid) => withBusy(async () => setBatch((await api.retryJob(batch.id, jid)).batch))}
            />
          </>
        )}

        {!batch && (
          <>
            <ReportInput
              text={text}
              onChange={setText}
              onParse={handleParse}
              onReset={handleReset}
              parsing={parsing}
              parsedCount={parsedOnce ? entries.length : null}
            />
            {parsedOnce && (
              <PreviewTable
                entries={entries}
                globalWarnings={globalWarnings}
                onChange={handleEntriesChange}
                refreshing={refreshing}
              />
            )}
            <LocalFolderBrowser value={outputDir} onChange={setOutputDir} disabled={batchRunning} />
            <DownloadSettings
              options={options}
              onChange={setOptions}
              onStart={handleStart}
              starting={starting}
              validCount={validCount}
              invalidCount={invalidCount}
              outputDir={outputDir}
              ffmpegOk={health ? health.ffmpeg : null}
              disabled={batchRunning || refreshing}
            />
          </>
        )}
      </main>

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        health={health}
        onOpenBatch={openBatch}
      />

      {toast && (
        <div className="fixed bottom-24 right-5 z-50 flex max-w-md items-start gap-3 rounded-2xl bg-[rgba(28,28,30,0.92)] p-4 text-sm text-white shadow-xl backdrop-blur-xl">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-300" />
          <p className="flex-1">{toast}</p>
          <button type="button" onClick={() => setToast(null)} aria-label="Tutup" className="text-slate-300 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

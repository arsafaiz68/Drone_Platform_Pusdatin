import { ClipboardPaste, FileText, Loader2, RotateCcw, ScanSearch } from "lucide-react";
import { useMemo, useState } from "react";
import { countYoutubeUrls } from "../utils/format";

interface Props {
  text: string;
  onChange: (text: string) => void;
  onParse: () => void;
  onReset: () => void;
  parsing: boolean;
  parsedCount: number | null;
  disabled?: boolean;
}

export default function ReportInput({ text, onChange, onParse, onReset, parsing, parsedCount, disabled }: Props) {
  const [pasteError, setPasteError] = useState<string | null>(null);
  const detected = useMemo(() => countYoutubeUrls(text), [text]);

  async function handlePaste() {
    setPasteError(null);
    try {
      const clip = await navigator.clipboard.readText();
      onChange(text ? `${text}\n${clip}` : clip);
    } catch {
      setPasteError("Browser menolak akses clipboard. Tekan Ctrl+V di area teks.");
    }
  }

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">
          <FileText className="h-5 w-5 text-navy-600" />
          1. Input Laporan
        </h2>
        <span className="badge bg-navy-50 text-navy-700">
          {detected} URL terdeteksi
          {parsedCount !== null && ` · ${parsedCount} entri diparsing`}
        </span>
      </div>
      <div className="space-y-3 p-5">
        <textarea
          value={text}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          spellCheck={false}
          placeholder={
            "Tempel laporan pemantauan dari WhatsApp di sini, contoh:\n\nHari/Tanggal : *Rabu, 1 April 2026*\n\n*Pel. Ketapang*\n*1 Apr 2026, 14:10 WIB*\nCuaca : Cerah, Tinggi Gelombang : 0.2 - 0.5 m (Selatan)\nLalin : Padat\nRekayasa Lalin : -\nhttps://www.youtube.com/live/…"
          }
          className="input h-72 resize-y font-mono text-[13px] leading-relaxed"
        />
        {pasteError && <p className="text-xs text-amber-700">{pasteError}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn-secondary" onClick={handlePaste} disabled={disabled}>
            <ClipboardPaste className="h-4 w-4" /> Tempel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={onParse}
            disabled={disabled || parsing || !text.trim()}
          >
            {parsing ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
            Parse Data
          </button>
          <button type="button" className="btn-ghost" onClick={onReset} disabled={disabled || parsing}>
            <RotateCcw className="h-4 w-4" /> Reset
          </button>
          <span className="ml-auto text-xs text-slate-500">
            {text.length.toLocaleString("id-ID")} karakter
          </span>
        </div>
      </div>
    </section>
  );
}

import { useEffect, useState } from "react";

export const DURATION_MIN = 10;
export const DURATION_MAX = 60;
export const DURATION_STEP = 5;
const TICKS = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60];

/**
 * Slider durasi video hasil: 10, 15, 20, … 60 detik (kelipatan 5).
 * `onChange` dipanggil saat slider dilepas (atau langsung bila `live`).
 */
export default function DurationSlider({ value, onChange, disabled = false, live = false }) {
  const [v, setV] = useState(Number(value) || 30);
  useEffect(() => { setV(Number(value) || 30); }, [value]);
  const clamp = (x) => Math.max(DURATION_MIN, Math.min(DURATION_MAX, Math.round(x / DURATION_STEP) * DURATION_STEP));
  const commit = (x) => { const c = clamp(x); setV(c); if (c !== Number(value)) onChange && onChange(c); };
  return (
    <div className={`dur-slider ${disabled ? "is-disabled" : ""}`}>
      <div className="dur-slider-row">
        <input type="range" min={DURATION_MIN} max={DURATION_MAX} step={DURATION_STEP} value={v} disabled={disabled}
          aria-label="Durasi tiap video hasil (detik)"
          onChange={(e) => { const c = clamp(Number(e.target.value)); setV(c); if (live) commit(c); }}
          onPointerUp={(e) => commit(Number(e.currentTarget.value))}
          onKeyUp={(e) => commit(Number(e.currentTarget.value))}
          onBlur={(e) => commit(Number(e.currentTarget.value))}
          style={{ "--fill": `${((v - DURATION_MIN) / (DURATION_MAX - DURATION_MIN)) * 100}%` }} />
        <span className="dur-slider-value mono">{v} dtk</span>
      </div>
      <div className="dur-slider-ticks">
        {TICKS.map((t) => (
          <button type="button" key={t} disabled={disabled} className={t === v ? "on" : ""}
            style={{ left: `${((t - DURATION_MIN) / (DURATION_MAX - DURATION_MIN)) * 100}%` }}
            onClick={() => commit(t)}>{t}</button>
        ))}
      </div>
    </div>
  );
}

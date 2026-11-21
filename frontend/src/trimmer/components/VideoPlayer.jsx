import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { fmtSec } from "../services/api.js";

/**
 * Pemutar video dengan kemampuan memutar rentang (segmen) tertentu.
 * ref: seek(t), playRange(a, b), currentTime()
 */
const VideoPlayer = forwardRef(function VideoPlayer({ src, onTime, markers = [], duration }, ref) {
  const v = useRef(null);
  const range = useRef(null);
  const [t, setT] = useState(0);
  const [err, setErr] = useState(null);

  useImperativeHandle(ref, () => ({
    seek: (s) => { if (v.current) { range.current = null; v.current.currentTime = s; } },
    playRange: (a, b) => {
      if (!v.current) return;
      range.current = { a, b };
      v.current.currentTime = a;
      v.current.play().catch(() => {});
    },
    currentTime: () => (v.current ? v.current.currentTime : 0),
    pause: () => v.current && v.current.pause(),
  }));

  useEffect(() => { setErr(null); range.current = null; }, [src]);

  const onTimeUpdate = () => {
    const cur = v.current.currentTime;
    setT(cur);
    onTime && onTime(cur);
    if (range.current && cur >= range.current.b) {
      v.current.pause();
      range.current = null;
    }
  };

  const total = duration || (v.current && v.current.duration) || 0;
  return (
    <div className="player">
      {src ? (
        <video ref={v} src={src} controls preload="metadata" onTimeUpdate={onTimeUpdate}
          onError={() => setErr("Video tidak dapat diputar di browser (codec tidak didukung). "
            + "Aktifkan pembuatan proxy preview di Pengaturan lalu analisis ulang.")} />
      ) : <div className="player-empty">Pilih video untuk preview</div>}
      {err && <div className="player-err">{err}</div>}
      {total > 0 && (
        <div className="player-track" onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const s = ((e.clientX - r.left) / r.width) * total;
          if (v.current) { range.current = null; v.current.currentTime = s; }
        }}>
          {markers.map((m, i) => (
            <div key={i} className={`track-mark ${m.className || ""}`} title={m.title}
              style={{ left: `${(m.start / total) * 100}%`, width: `${Math.max(0.4, ((m.end - m.start) / total) * 100)}%` }} />
          ))}
          <div className="track-head" style={{ left: `${(t / total) * 100}%` }} />
        </div>
      )}
      <div className="player-time mono">{fmtSec(t)} / {fmtSec(total)}</div>
    </div>
  );
});

export default VideoPlayer;

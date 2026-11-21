/** Grafik kurva skor kualitas & aktivitas hasil analisis, dengan zona titik dan putar balik. */
export default function ScoreChart({ curve, zones = [], events = [], duration, height = 90 }) {
  if (!curve || !curve.t || curve.t.length < 2) return null;
  const W = 1000, H = height;
  const dur = duration || curve.t[curve.t.length - 1] || 1;
  const x = (t) => (t / dur) * W;
  const line = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(curve.t[i]).toFixed(1)},${(H - 4 - v * (H - 18)).toFixed(1)}`).join("");
  return (
    <svg className="score-chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
      aria-label="Kurva skor kualitas dan aktivitas">
      {zones.map((z, i) => (
        <g key={i}>
          <rect x={x(z.start)} y={0} width={Math.max(1, x(z.end) - x(z.start))} height={12}
            className={z.direction === "return" ? "zone-ret" : "zone-out"} opacity={0.85} />
          <text x={x(z.start) + 3} y={9.5} className="zone-text">{z.point_code}</text>
          <line x1={x(z.start)} x2={x(z.start)} y1={0} y2={H} className="zone-line" />
        </g>
      ))}
      <path d={line(curve.quality)} className="curve-q" />
      <path d={line(curve.activity)} className="curve-a" />
      {events.map((e, i) => (
        <line key={i} x1={x(e.time)} x2={x(e.time)} y1={12} y2={H} className={e.main ? "turn-main" : "turn-sec"} />
      ))}
    </svg>
  );
}

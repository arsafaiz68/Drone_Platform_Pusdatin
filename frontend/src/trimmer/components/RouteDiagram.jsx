/** Diagram urutan titik pergi dan kembali beserta titik putar balik. */
export default function RouteDiagram({ outbound = [], ret = [], turnarounds = [], showReturn = true }) {
  const Step = ({ code, last, turn }) => (
    <>
      <span className={`route-pt ${code === "H" ? "route-home" : ""} ${turn ? "route-turn" : ""}`}
        title={turn ? "Titik putar balik" : undefined}>
        {code}{turn && <sup>↻</sup>}
      </span>
      {!last && <span className="route-arrow">→</span>}
    </>
  );
  return (
    <div className="route">
      <div className="route-line">
        <span className="route-tag">Pergi</span>
        {outbound.map((c, i) => <Step key={`o${i}`} code={c} last={i === outbound.length - 1} turn={turnarounds.includes(c)} />)}
      </div>
      {showReturn && (
        <div className="route-line">
          <span className="route-tag route-tag-ret">Kembali</span>
          {ret.map((c, i) => <Step key={`r${i}`} code={c} last={i === ret.length - 1} />)}
        </div>
      )}
    </div>
  );
}

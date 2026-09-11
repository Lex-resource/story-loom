import { EVALUATION_DIMS } from '../utils/streamingJsonParser';

const CX = 150;
const CY = 150;
const R = 100;

function polar(angle, radius) {
  const rad = (angle - 90) * (Math.PI / 180);
  return {
    x: CX + radius * Math.cos(rad),
    y: CY + radius * Math.sin(rad),
  };
}

export default function EvaluationRadar({ evaluations, streaming = false }) {
  const n = EVALUATION_DIMS.length;
  const step = 360 / n;

  const scores = EVALUATION_DIMS.map(({ key }) => {
    const dim = evaluations?.[key];
    return dim?.score ?? 0;
  });

  const hasAny = scores.some((s) => s > 0);

  const gridLevels = [2, 4, 6, 8, 10];
  const dataPoints = scores.map((score, i) => polar(i * step, (score / 10) * R));
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';

  return (
    <div className="eval-radar-wrap">
      <svg viewBox="0 0 300 300" className="eval-radar-svg">
        {gridLevels.map((level) => {
          const pts = Array.from({ length: n }, (_, i) => polar(i * step, (level / 10) * R));
          const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';
          return <path key={level} d={d} fill="none" stroke="rgba(44,24,16,0.12)" strokeWidth="1" />;
        })}

        {EVALUATION_DIMS.map((_, i) => {
          const outer = polar(i * step, R);
          return (
            <line key={i} x1={CX} y1={CY} x2={outer.x} y2={outer.y} stroke="rgba(44,24,16,0.15)" strokeWidth="1" />
          );
        })}

        {hasAny && (
          <path
            d={dataPath}
            fill="rgba(194, 58, 43, 0.2)"
            stroke="var(--vermilion)"
            strokeWidth="2"
            strokeLinejoin="round"
          />
        )}

        {hasAny && dataPoints.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r="4" fill="var(--vermilion)" />)}

        {EVALUATION_DIMS.map(({ label }, i) => {
          const pos = polar(i * step, R + 22);
          return (
            <text
              key={label}
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="eval-radar-label"
            >
              {label}
            </text>
          );
        })}
      </svg>

      {streaming && !hasAny && <div className="eval-radar-placeholder">编辑智能体评分生成中…</div>}

      {hasAny && (
        <div className="eval-radar-scores">
          {EVALUATION_DIMS.map(({ key, label }) => {
            const dim = evaluations?.[key];
            const score = dim?.score;
            if (score === undefined || score === null) return null;
            const color = score >= 8 ? '#10b981' : score >= 6 ? '#f59e0b' : '#ef4444';
            return (
              <div key={key} className="eval-radar-score-row">
                <span className="eval-radar-score-label">{label}</span>
                <span className="eval-radar-score-value" style={{ color }}>
                  {score}/10
                </span>
                {dim?.reason && <p className="eval-radar-score-reason">{dim.reason}</p>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

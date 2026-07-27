import { useState } from 'react';

export default function CostChart({ data }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);

  if (!data || data.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
        暂无成本数据。系统在生成新的章节后将自动累积并在此展示。
      </div>
    );
  }

  // Max value for scaling
  const maxCost = Math.max(...data.map(d => d.total || 0.0001), 0.0001) * 1.1;
  const minCost = 0;

  // Chart dimensions
  const width = 600;
  const height = 250;
  const paddingLeft = 55;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 40;

  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;

  // Generate SVG coordinates
  const getCoords = (index, val) => {
    const x = paddingLeft + (index / (data.length - 1 || 1)) * chartWidth;
    const y = paddingTop + chartHeight - ((val - minCost) / (maxCost - minCost)) * chartHeight;
    return { x, y };
  };

  // Build line paths
  const makePath = (key) => {
    const points = data.map((d, idx) => getCoords(idx, d[key] || 0));
    if (points.length === 0) return '';
    return points.reduce((acc, p, idx) => {
      return idx === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`;
    }, '');
  };

  const makeAreaPath = (key) => {
    const points = data.map((d, idx) => getCoords(idx, d[key] || 0));
    if (points.length === 0) return '';
    const linePath = makePath(key);
    const startX = points[0].x;
    const endX = points[points.length - 1].x;
    const baseY = paddingTop + chartHeight;
    return `${linePath} L ${endX} ${baseY} L ${startX} ${baseY} Z`;
  };

  return (
    <div className="glass-panel" style={{ padding: '20px', borderRadius: '12px', background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-muted)', marginBottom: '20px' }}>
      <h3 style={{ marginTop: 0, marginBottom: '16px', fontSize: '15px', color: 'var(--text-primary)' }}>API 创作成本变化趋势折线图 (每章节)</h3>
      <div style={{ position: 'relative' }}>
        <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="auto">
          <defs>
            <linearGradient id="totalGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--vermilion, #ff4e50)" stopOpacity="0.2" />
              <stop offset="100%" stopColor="var(--vermilion, #ff4e50)" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((r, idx) => {
            const y = paddingTop + r * chartHeight;
            const val = maxCost - r * (maxCost - minCost);
            return (
              <g key={idx}>
                <line x1={paddingLeft} y1={y} x2={width - paddingRight} y2={y} stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
                <text x={paddingLeft - 8} y={y + 4} textAnchor="end" fill="var(--text-secondary, #94a3b8)" fontSize="10">{`$${val.toFixed(4)}`}</text>
              </g>
            );
          })}

          {/* X axis labels */}
          {data.map((d, idx) => {
            const p = getCoords(idx, 0);
            const labelY = paddingTop + chartHeight + 18;
            const rotate = data.length > 8;
            return (
              <text
                key={idx}
                x={p.x}
                y={labelY}
                textAnchor={rotate ? 'end' : 'middle'}
                fill="var(--text-secondary, #94a3b8)"
                fontSize="10"
                transform={rotate ? `rotate(-45 ${p.x} ${labelY})` : undefined}
              >
                {d.label}
              </text>
            );
          })}

          {/* Area under total */}
          <path d={makeAreaPath('total')} fill="url(#totalGrad)" />

          {/* Lines */}
          <path d={makePath('total')} fill="none" stroke="var(--vermilion, #ff4e50)" strokeWidth="2.5" />
          <path d={makePath('writer')} fill="none" stroke="#10b981" strokeWidth="1.5" strokeDasharray="3 3" />
          <path d={makePath('editor')} fill="none" stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="3 3" />
          <path d={makePath('validator')} fill="none" stroke="#ef4444" strokeWidth="1.5" strokeDasharray="3 3" />

          {/* Hover indicator line & dot */}
          {hoveredIdx !== null && hoveredIdx < data.length && (() => {
            const d = data[hoveredIdx];
            const p = getCoords(hoveredIdx, d.total);
            return (
              <g>
                <line x1={p.x} y1={paddingTop} x2={p.x} y2={paddingTop + chartHeight} stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
                <circle cx={p.x} cy={p.y} r="5" fill="var(--vermilion, #ff4e50)" stroke="#fff" strokeWidth="1.5" />
              </g>
            );
          })()}

          {/* Interactive hover overlays */}
          {data.map((d, idx) => {
            const p = getCoords(idx, 0);
            const colWidth = chartWidth / (data.length - 1 || 1);
            return (
              <rect
                key={idx}
                x={p.x - colWidth / 2}
                y={paddingTop}
                width={colWidth}
                height={chartHeight}
                fill="transparent"
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoveredIdx(idx)}
                onMouseLeave={() => setHoveredIdx(null)}
              />
            );
          })}
        </svg>

        {/* Floating Tooltip */}
        {hoveredIdx !== null && hoveredIdx < data.length && (() => {
          const d = data[hoveredIdx];
          return (
            <div style={{
              position: 'absolute',
              top: '10px',
              right: '10px',
              background: '#1f2937',
              border: '1px solid #374151',
              borderRadius: '8px',
              padding: '10px 14px',
              boxShadow: '0 4px 6px -1px rgba(0,0,0,0.5)',
              fontSize: '11px',
              color: '#fff',
              zIndex: 10,
              width: '180px'
            }}>
              <div style={{ fontWeight: 'bold', borderBottom: '1px solid #374151', paddingBottom: '4px', marginBottom: '6px' }}>{d.label} 成本明细</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span>总开销:</span>
                <strong style={{ color: 'var(--vermilion, #ff4e50)' }}>${d.total.toFixed(4)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px', color: '#a7f3d0' }}>
                <span>执笔 (Writer):</span>
                <span>${(d.writer || 0).toFixed(4)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px', color: '#fde047' }}>
                <span>精修 (Editor):</span>
                <span>${(d.editor || 0).toFixed(4)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#fca5a5' }}>
                <span>审计 (Validator):</span>
                <span>${(d.validator || 0).toFixed(4)}</span>
              </div>
            </div>
          );
        })()}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: '16px', justifyContent: 'center', marginTop: '12px', fontSize: '11px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <div style={{ width: '12px', height: '3px', background: 'var(--vermilion, #ff4e50)' }} />
          <span>总成本 (Total)</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <div style={{ width: '12px', height: '1px', borderTop: '1px dashed #10b981' }} />
          <span style={{ color: '#10b981' }}>执笔 (Writer)</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <div style={{ width: '12px', height: '1px', borderTop: '1px dashed #f59e0b' }} />
          <span style={{ color: '#f59e0b' }}>精修 (Editor)</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <div style={{ width: '12px', height: '1px', borderTop: '1px dashed #ef4444' }} />
          <span style={{ color: '#ef4444' }}>天道 (Validator)</span>
        </div>
      </div>
    </div>
  );
}

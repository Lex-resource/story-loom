import { useState, useCallback } from 'react';
import { useVisNetwork } from './useVisNetwork';

export default function KnowledgeGraphCanvas({
  data,
  options,
  onNodeClick,
  loading = false,
  error = null,
  emptyMessage = '暂无图谱数据',
  stats = null,
  controls,
  freezeAfterStabilization = false,
}) {
  const [container, setContainer] = useState(null);
  const setRef = useCallback((node) => setContainer(node), []);

  const { fit, zoomIn, zoomOut } = useVisNetwork(container, data, options, onNodeClick, { freezeAfterStabilization });

  return (
    <div className="kg-canvas-wrapper">
      <div className="kg-canvas-toolbar">
        {stats && (
          <div className="kg-stats">
            <span className="kg-stat-badge">{stats.nodeCount} 节点</span>
            <span className="kg-stat-badge">{stats.edgeCount} 关系</span>
          </div>
        )}
        <div className="kg-zoom-controls">
          <button type="button" className="kg-zoom-btn" onClick={zoomIn} title="放大">
            +
          </button>
          <button type="button" className="kg-zoom-btn" onClick={zoomOut} title="缩小">
            −
          </button>
          <button type="button" className="kg-zoom-btn" onClick={fit} title="适应画布">
            ⊡
          </button>
        </div>
        {controls}
      </div>

      <div className="kg-canvas-body">
        {loading && (
          <div className="kg-overlay">
            <div className="kg-spinner" />
            <span>加载图谱中…</span>
          </div>
        )}
        {error && !loading && (
          <div className="kg-overlay kg-overlay--error">
            <span>{error}</span>
          </div>
        )}
        {!loading && !error && data?.nodes?.length === 0 && (
          <div className="kg-overlay">
            <span>{emptyMessage}</span>
          </div>
        )}
        <div ref={setRef} className="kg-canvas" />
      </div>
    </div>
  );
}

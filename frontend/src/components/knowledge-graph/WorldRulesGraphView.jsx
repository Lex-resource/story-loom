import { useState, useEffect, useMemo, useCallback } from 'react';
import KnowledgeGraphCanvas from './KnowledgeGraphCanvas';
import GraphDetailPanel from './GraphDetailPanel';
import GraphToolbar from './GraphToolbar';
import { WORLD_PHYSICS_OPTIONS, TAG_COLORS } from './graphTheme';
import { filterBySearch, toVisWorldData, graphStats } from './graphTransforms';
import { knowledgeGraphApi } from '../../services/novelApi';
import { createRequestGuard } from '../../utils/requestLifecycle';

const LEGEND_ITEMS = [
  { key: 'rule', label: '编译法则' },
  { key: 'location', label: '运行空间' },
  { key: 'faction', label: '活动线程' },
  { key: 'restriction', label: '限制禁忌' },
  { key: 'confirmed', label: '已验真理' },
];

export default function WorldRulesGraphView({ projectId }) {
  const [rawData, setRawData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!projectId) return;
    const requestGuard = createRequestGuard();
    const request = requestGuard.start();
    setLoading(true);
    setError(null);

    knowledgeGraphApi
      .worldRulesTree(projectId, { signal: request.signal })
      .then((data) => {
        if (request.isCurrent()) setRawData(data);
      })
      .catch((err) => {
        if (request.isCurrent() && err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => {
        if (request.isCurrent()) setLoading(false);
      });

    return () => {
      requestGuard.cancel();
    };
  }, [projectId]);

  const { visData, stats } = useMemo(() => {
    if (!rawData) return { visData: null, stats: null };
    const filtered = filterBySearch(rawData.nodes || [], rawData.edges || [], search, ['title']);
    const subset = { ...rawData, nodes: filtered.nodes, edges: filtered.edges };
    return {
      visData: toVisWorldData(subset),
      stats: graphStats(filtered.nodes, filtered.edges),
    };
  }, [rawData, search]);

  const handleNodeClick = useCallback(
    (params) => {
      if (!params.nodes.length || !rawData) {
        setDetail(null);
        return;
      }
      const nodeId = params.nodes[0];
      if (rawData.details?.[nodeId]) {
        setDetail({
          title: rawData.details[nodeId].tag_display || '天地法则',
          content: rawData.details[nodeId].content,
        });
        return;
      }
      const node = (rawData.nodes || []).find((n) => n.id === nodeId);
      setDetail(node ? { title: node.label, content: node.title || '世界观编译节点' } : null);
    },
    [rawData],
  );

  return (
    <div className="kg-view">
      <header className="kg-view-header">
        <div>
          <h3 className="kg-view-title">天地法则编译网</h3>
          <p className="kg-view-desc">分类展示世界观核心法则、空间地理、势力组织及禁忌设定。</p>
        </div>
        <GraphToolbar searchValue={search} onSearchChange={setSearch} searchPlaceholder="搜索法则或势力…" />
      </header>

      <div className="kg-legend">
        {LEGEND_ITEMS.map((item) => (
          <span key={item.key} className="kg-legend-item">
            <span className="kg-legend-dot" style={{ background: TAG_COLORS[item.key] }} />
            {item.label}
          </span>
        ))}
      </div>

      <div className="kg-split-layout">
        <KnowledgeGraphCanvas
          data={visData}
          options={WORLD_PHYSICS_OPTIONS}
          onNodeClick={handleNodeClick}
          loading={loading}
          error={error}
          stats={stats}
          emptyMessage="天地界定为空，撰写世界观设定后将自动生成编译网"
        />
        <GraphDetailPanel
          title={detail?.title}
          content={detail?.content}
          placeholder="点击左侧图谱节点查看天地法则详情"
        />
      </div>
    </div>
  );
}

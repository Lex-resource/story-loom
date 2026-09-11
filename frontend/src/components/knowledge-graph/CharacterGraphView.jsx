import { useState, useEffect, useMemo, useCallback } from 'react';
import KnowledgeGraphCanvas from './KnowledgeGraphCanvas';
import GraphDetailPanel from './GraphDetailPanel';
import GraphToolbar from './GraphToolbar';
import { GRAPH_PHYSICS_OPTIONS } from './graphTheme';
import { knowledgeGraphApi } from '../../services/novelApi';
import { filterBySearch, transformCharacterGraph, toVisCharacterData, graphStats } from './graphTransforms';
import { createRequestGuard } from '../../utils/requestLifecycle';

const FILTER_OPTIONS = [
  { id: 'hybrid', label: '混合鸟瞰' },
  { id: 'characters', label: '纯人际关系' },
  { id: 'factions', label: '宗门分布' },
];

const LEGEND_ITEMS = [
  { color: '#c23a2b', label: '主角' },
  { color: '#2c1810', label: '反派' },
  { color: '#b8860b', label: '势力枢纽' },
  { color: '#2d6a4f', label: '其他势力' },
];

export default function CharacterGraphView({ projectId }) {
  const [rawData, setRawData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterMode, setFilterMode] = useState('hybrid');
  const [search, setSearch] = useState('');
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!projectId) return;
    const requestGuard = createRequestGuard();
    const request = requestGuard.start();
    setLoading(true);
    setError(null);

    knowledgeGraphApi
      .characterGraph(projectId, { signal: request.signal })
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

  const { visData, stats, sourceNodes } = useMemo(() => {
    if (!rawData) return { visData: null, stats: null, sourceNodes: [] };
    const transformed = transformCharacterGraph(rawData, filterMode);
    const filtered = filterBySearch(transformed.nodes, transformed.edges, search, ['group']);
    return {
      visData: toVisCharacterData(filtered.nodes, filtered.edges),
      stats: graphStats(filtered.nodes, filtered.edges),
      sourceNodes: filtered.nodes,
    };
  }, [rawData, filterMode, search]);

  const handleNodeClick = useCallback(
    (params) => {
      if (!params.nodes.length || !rawData) {
        setDetail(null);
        return;
      }
      const node = sourceNodes.find((n) => n.id === params.nodes[0]);
      if (node && node.group !== 'faction_hub') {
        setDetail({
          title: node.label,
          content: rawData.details?.[node.label] || '暂无详细背景记录',
        });
      } else {
        setDetail(null);
      }
    },
    [rawData, sourceNodes],
  );

  return (
    <div className="kg-view">
      <header className="kg-view-header">
        <div>
          <h3 className="kg-view-title">人物势力图谱</h3>
          <p className="kg-view-desc">展示小说中出场人物及其关联关系。可切换人际、势力分布或混合视图。</p>
        </div>
        <GraphToolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder="搜索人物或势力…"
          filters={FILTER_OPTIONS}
          activeFilter={filterMode}
          onFilterChange={setFilterMode}
        />
      </header>

      <div className="kg-legend">
        {LEGEND_ITEMS.map((item) => (
          <span key={item.label} className="kg-legend-item">
            <span className="kg-legend-dot" style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
      </div>

      <div className="kg-split-layout">
        <KnowledgeGraphCanvas
          data={visData}
          options={GRAPH_PHYSICS_OPTIONS}
          onNodeClick={handleNodeClick}
          loading={loading}
          error={error}
          stats={stats}
          emptyMessage="人物志为空，撰写人物设定后将自动生成关系图谱"
        />
        <GraphDetailPanel
          title={detail?.title}
          content={detail?.content}
          placeholder="点击左侧图谱节点查看人物志详情"
        />
      </div>
    </div>
  );
}

import { useMemo, useState } from 'react';
import { Globe, HelpCircle, Layers, User } from 'lucide-react';
import CharacterGraphView from '../components/knowledge-graph/CharacterGraphView';
import WorldRulesGraphView from '../components/knowledge-graph/WorldRulesGraphView';
import ForeshadowingTimelineView from '../components/knowledge-graph/ForeshadowingTimelineView';
import PlotTracksView from '../components/knowledge-graph/PlotTracksView';

const graphTabs = {
  characters: ['人物关系', User],
  world: ['世界规则', Globe],
  foreshadowing: ['伏笔时间线', HelpCircle],
  plot: ['剧情主线', Layers],
};

export default function LivingDocs({ activeProject }) {
  const [tab, setTab] = useState('characters');
  const projectId = activeProject?.id;

  const graph = useMemo(
    () => ({
      characters: projectId && <CharacterGraphView projectId={projectId} />,
      world: projectId && <WorldRulesGraphView projectId={projectId} />,
      foreshadowing: projectId && <ForeshadowingTimelineView projectId={projectId} />,
      plot: projectId && <PlotTracksView projectId={projectId} />,
    }),
    [projectId],
  );

  return (
    <div className="living-docs-grid">
      <aside className="living-docs-sidebar">
        <div className="living-docs-section-label">知识视图</div>
        {Object.entries(graphTabs).map(([key, [label, Icon]]) => (
          <button
            type="button"
            className={`nav-item ${tab === key ? 'active' : ''}`}
            key={key}
            onClick={() => setTab(key)}
          >
            <Icon size={16} />
            <span>{label}</span>
          </button>
        ))}
      </aside>
      <main className="living-docs-content">{graph[tab]}</main>
    </div>
  );
}

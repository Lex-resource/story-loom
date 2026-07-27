import { useState, useEffect } from 'react';
import {
  User,
  Globe,
  HelpCircle,
  Layers,
  BookOpen,
  GitMerge,
  Clock,
  RefreshCw,
  Loader2,
  Save,
} from 'lucide-react';
import CostChart from '../components/CostChart';
import { simpleDiff } from '../utils/simpleDiff';
import CharacterGraphView from '../components/knowledge-graph/CharacterGraphView';
import WorldRulesGraphView from '../components/knowledge-graph/WorldRulesGraphView';
import ForeshadowingTimelineView from '../components/knowledge-graph/ForeshadowingTimelineView';
import PlotTracksView from '../components/knowledge-graph/PlotTracksView';
import { API_BASE } from '../services/api';
import { livingDocsApi } from '../services/novelApi';

const DiffViewComponent = ({ oldText, newText }) => {
  const diffs = simpleDiff(oldText || '', newText || '');
  return (
    <div className="diff-view">
      {diffs.map((line, idx) => {
        let backgroundColor = 'transparent';
        let color = '#ccc';
        let prefix = '  ';
        if (line.type === 'added') {
          backgroundColor = 'rgba(16, 185, 129, 0.15)';
          color = '#a7f3d0';
          prefix = '+ ';
        } else if (line.type === 'removed') {
          backgroundColor = 'rgba(239, 68, 68, 0.15)';
          color = '#fca5a5';
          prefix = '- ';
        }
        return (
          <div key={idx} className="diff-line" style={{ backgroundColor, color }}>
            {prefix}{line.value}
          </div>
        );
      })}
    </div>
  );
};

const EDITOR_TABS = [
  'global_outline', 'act_outline', 'character_state',
  'world_state', 'foreshadowing', 'plot_threads',
];

const DOC_TYPE_MAP = {
  character: 'character_state',
  world: 'world_state',
  foreshadowing: 'foreshadowing',
  plot: 'plot_threads',
};

export default function LivingDocs({
  activeProject,
  livingDocs,
  loadLivingDocs,
  docVersions,
  tokenStats,
  loadTokenStats,
  addLog,
  showToast,
}) {
  const [docsTab, setDocsTab] = useState('character');
  const [selectedStatsModel, setSelectedStatsModel] = useState('All Models');

  const [diffActive, setDiffActive] = useState(false);
  const [diffVersionIndex, setDiffVersionIndex] = useState(null);
  const [diffOldText, setDiffOldText] = useState('');
  const [diffNewText, setDiffNewText] = useState('');
  const [loadingDiff, setLoadingDiff] = useState(false);

  const [editingDocContent, setEditingDocContent] = useState('');
  const [savingDoc, setSavingDoc] = useState(false);

  const getDocTypeString = () => DOC_TYPE_MAP[docsTab] || 'world_state';

  const handleCompareDiff = async (chapterIndex) => {
    setLoadingDiff(true);
    setDiffVersionIndex(chapterIndex);
    const targetDocType = getDocTypeString();
    try {
      const [version, current] = await Promise.all([
        livingDocsApi.getVersion(activeProject.id, chapterIndex, targetDocType),
        livingDocsApi.get(activeProject.id, targetDocType),
      ]);
      setDiffOldText(version.content || '');
      setDiffNewText(current.content || '');
      setDiffActive(true);
    } catch (err) {
      showToast(`对比加载失败: ${err.message}`);
    } finally {
      setLoadingDiff(false);
    }
  };

  useEffect(() => {
    if (livingDocs && EDITOR_TABS.includes(docsTab)) {
      setEditingDocContent(livingDocs[docsTab] || '');
    }
  }, [docsTab, livingDocs]);

  const handleSaveDoc = async () => {
    if (!activeProject) return;
    setSavingDoc(true);
    try {
      await livingDocsApi.update(activeProject.id, docsTab, editingDocContent);
      addLog('系统', `设定大纲文档【${docsTab}】成功修改并更新至数据库！`, 'system');
      loadLivingDocs(activeProject.id);
    } catch (e) {
      showToast(e.message);
    } finally {
      setSavingDoc(false);
    }
  };

  const handleRollbackDoc = async (chapterIndex) => {
    if (!activeProject) return;
    if (confirm(`确认要将活文档回滚到生成第 ${chapterIndex} 章之后的版本吗？`)) {
      try {
        await livingDocsApi.rollback(activeProject.id, chapterIndex);
        addLog('系统', `活文档已成功回滚至第 ${chapterIndex} 章的状态。`, 'system');
        loadLivingDocs(activeProject.id);
      } catch (e) {
        showToast(e.message);
      }
    }
  };

  const isEditorTab = EDITOR_TABS.includes(docsTab);
  const projectId = activeProject?.id;

  const navItem = (tab, icon, label) => (
    <div
      key={tab}
      className={`nav-item ${docsTab === tab ? 'active' : ''}`}
      onClick={() => setDocsTab(tab)}
    >
      {icon}
      <span>{label}</span>
    </div>
  );

  return (
    <div className="living-docs-grid">
      <div className="living-docs-sidebar">
        <div className="living-docs-section-label">可视化图景</div>
        {navItem('character', <User size={16} />, '人物势力图谱')}
        {navItem('world', <Globe size={16} />, '天地法则编译网')}
        {navItem('foreshadowing_timeline', <HelpCircle size={16} />, '因果时空卷轴')}
        {navItem('plot_timeline', <Layers size={16} />, '剧情主脉演进图')}

        <div className="living-docs-section-label living-docs-section-label--bordered">设定</div>
        {navItem('global_outline', <BookOpen size={16} />, '全书大纲')}
        {navItem('act_outline', <GitMerge size={16} />, '分幕大纲')}
        {navItem('character_state', <User size={16} />, '人物志')}
        {navItem('world_state', <Globe size={16} />, '天地界定')}
        {navItem('foreshadowing', <HelpCircle size={16} />, '因果线索')}
        {navItem('plot_threads', <Layers size={16} />, '剧情主脉')}

        <div className="living-docs-section-label living-docs-section-label--bordered">分析工具</div>
        {navItem('timeline', <Clock size={16} />, '因果时光机及开销')}
      </div>

      <div className="living-docs-content">
        {docsTab === 'character' && projectId && (
          <CharacterGraphView projectId={projectId} apiBase={API_BASE} />
        )}
        {docsTab === 'world' && projectId && (
          <WorldRulesGraphView projectId={projectId} apiBase={API_BASE} />
        )}
        {docsTab === 'foreshadowing_timeline' && projectId && (
          <ForeshadowingTimelineView projectId={projectId} apiBase={API_BASE} />
        )}
        {docsTab === 'plot_timeline' && projectId && (
          <PlotTracksView projectId={projectId} apiBase={API_BASE} />
        )}

        {['global_outline', 'act_outline', 'character_state', 'world_state', 'foreshadowing', 'plot_threads'].includes(docsTab) && (
          <div className="kg-view">
            <header className="kg-view-header">
              <div>
                <h3 className="kg-view-title">
                  {{
                    global_outline: '全书整体大纲',
                    act_outline: '分幕大纲与情节设计',
                    character_state: '人物志',
                    world_state: '天地界定',
                    foreshadowing: '因果线索',
                    plot_threads: '剧情主脉',
                  }[docsTab]}
                </h3>
                <p className="kg-view-desc">
                  {{
                    global_outline: '规划并记录小说全书的全局核心梗概、核心矛盾冲突与长远走向蓝图。',
                    act_outline: '设计小说的分幕情节节点图、起承转合结构与各卷高潮节拍器。',
                    character_state: '记录出场人物的修仙道体、法宝灵根、立场派别、前尘往事与成长线索。',
                    world_state: '详细定义修仙世界的境界划分、法则编译限制、天地运行规则与地理空间边界。',
                    foreshadowing: '编写与维护小说各个主支线伏笔的预埋、爆发与闭合回收线索。',
                    plot_threads: '编写与维护全书各条故事主脉演进、核心支线的阶段状态与切分逻辑。',
                  }[docsTab]}
                </p>
              </div>
            </header>
          </div>
        )}

        {isEditorTab && (
          <div className="doc-editor-container">
            <div className="doc-editor-header">
              <h3>活字法书编译 (Live Markdown)</h3>
              <button className="btn btn-primary" onClick={handleSaveDoc} disabled={savingDoc}>
                {savingDoc ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                保存设定
              </button>
            </div>
            <textarea
              className="editor-textarea doc-editor-textarea"
              value={editingDocContent}
              onChange={(e) => setEditingDocContent(e.target.value)}
            />
          </div>
        )}

        {docsTab === 'timeline' && (
          <div className="timeline-grid">
            <div className="glass-panel timeline-panel">
              <h3 className="text-gradient">因果回溯时光机 (Living Versions)</h3>
              <p className="text-secondary text-xs mb-4">
                随时可以点击任意快照节点，将全书的活文档一键倒回至指定章节的节点。
              </p>
              <div className="doc-versions-panel">
                {docVersions.map((v, idx) => (
                  <div key={idx} className="timeline-node">
                    <div className="timeline-dot" />
                    <h4>生成第 {v.chapter_index} 章之后的版本快照</h4>
                    <p className="text-xs text-secondary">
                      文档类型: {v.doc_type} | 校验码: {v.checksum?.substring(0, 8)}
                    </p>
                    <div className="timeline-actions">
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleCompareDiff(v.chapter_index)}
                        disabled={loadingDiff}
                      >
                        {loadingDiff && diffVersionIndex === v.chapter_index
                          ? '加载中...'
                          : '对比差异 (Diff)'}
                      </button>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => handleRollbackDoc(v.chapter_index)}
                      >
                        因果回溯 (Rollback)
                      </button>
                    </div>
                  </div>
                ))}
                {docVersions.length === 0 && (
                  <p className="text-secondary text-sm">暂无历史快照节点。</p>
                )}
              </div>
              {diffActive && (
                <div className="diff-panel">
                  <div className="diff-panel-header">
                    <h4>
                      快照对比: 第 {diffVersionIndex} 章版本 (旧) vs 当前在线版本 (新)
                    </h4>
                    <button className="btn btn-secondary btn-sm" onClick={() => setDiffActive(false)}>
                      关闭对比
                    </button>
                  </div>
                  <DiffViewComponent oldText={diffOldText} newText={diffNewText} />
                </div>
              )}
            </div>

            <div className="glass-panel timeline-panel">
              <div className="token-stats-header">
                <h3 className="text-gradient">大模型开销及统计 (Token Costs)</h3>
                <div className="token-stats-controls">
                  <select
                    className="form-input"
                    value={selectedStatsModel}
                    onChange={(e) => {
                      setSelectedStatsModel(e.target.value);
                      loadTokenStats(activeProject.id, e.target.value);
                    }}
                  >
                    <option value="All Models">所有模型</option>
                    {tokenStats?.model_stats?.map((m, idx) => (
                      <option key={idx} value={m.model_name}>{m.model_name}</option>
                    ))}
                  </select>
                  <button
                    className="btn btn-secondary"
                    onClick={() => loadTokenStats(activeProject.id, selectedStatsModel)}
                  >
                    <RefreshCw size={12} />
                  </button>
                </div>
              </div>
              {tokenStats ? (
                <div className="token-stats-body">
                  <div className="token-stats-grid">
                    <div className="stat-card">
                      <div className="stat-value" style={{ color: 'var(--jade)' }}>
                        ${tokenStats.total_cost?.toFixed(5)}
                      </div>
                      <div className="stat-label">总耗费金额</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value">
                        {(tokenStats.total_input_tokens + tokenStats.total_output_tokens)?.toLocaleString()}
                      </div>
                      <div className="stat-label">总耗费 Tokens</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value">
                        {((tokenStats.cache_hit_ratio || 0) * 100).toFixed(2)}%
                      </div>
                      <div className="stat-label">缓存击中率</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value">{tokenStats.total_input_tokens?.toLocaleString()}</div>
                      <div className="stat-label">输入 Tokens</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value">{tokenStats.total_output_tokens?.toLocaleString()}</div>
                      <div className="stat-label">输出 Tokens</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value">{tokenStats.total_embedding_tokens?.toLocaleString()}</div>
                      <div className="stat-label">向量嵌入 Tokens</div>
                    </div>
                  </div>
                  <div>
                    <h4 className="agent-breakdown-title">各智能体开销比例</h4>
                    <div className="agent-breakdown-list">
                      {tokenStats.agent_stats?.map((ag, idx) => (
                        <div key={idx} className="agent-breakdown-row">
                          <span className="capitalize">
                            {{
                              planner: '大纲策划',
                              writer: '作家执笔',
                              editor: '编辑润色',
                              validator: '法则校验',
                            }[ag.agent_name] || ag.agent_name}
                          </span>
                          <span className="font-semibold">
                            ${ag.cost?.toFixed(5)} ({ag.input_tokens + ag.output_tokens} tokens)
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                  {tokenStats.chapter_stats?.length > 0 && (
                    <CostChart
                      data={tokenStats.chapter_stats.map((c) => ({
                        label: `第 ${c.chapter_index} 章`,
                        total: c.cost,
                        writer: c.writer_cost,
                        editor: c.editor_cost,
                        validator: c.validator_cost,
                      }))}
                    />
                  )}
                </div>
              ) : (
                <p style={{ color: 'var(--text-secondary)' }}>暂无代币统计数据。</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

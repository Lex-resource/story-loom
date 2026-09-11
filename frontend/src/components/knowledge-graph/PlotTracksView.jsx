import { useState, useEffect } from 'react';
import GraphToolbar from './GraphToolbar';
import { knowledgeGraphApi } from '../../services/novelApi';
import { createRequestGuard } from '../../utils/requestLifecycle';

export default function PlotTracksView({ projectId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedThread, setSelectedThread] = useState('All');

  useEffect(() => {
    if (!projectId) return;
    const requestGuard = createRequestGuard();
    const request = requestGuard.start();

    const loadData = async () => {
      setLoading(true);
      try {
        const json = await knowledgeGraphApi.plotTracks(projectId, { signal: request.signal });
        if (request.isCurrent()) setData(json);
      } catch (err) {
        if (request.isCurrent() && err.name !== 'AbortError') {
          console.error('Failed to load plot tracks:', err);
        }
      } finally {
        if (request.isCurrent()) setLoading(false);
      }
    };

    loadData();

    return () => {
      requestGuard.cancel();
    };
  }, [projectId]);

  const q = search.toLowerCase().trim();
  const events = (data?.events || [])
    .filter((ev) => selectedThread === 'All' || ev.thread === selectedThread)
    .filter((ev) => {
      if (!q) return true;
      return ev.thread.toLowerCase().includes(q) || ev.progress.toLowerCase().includes(q);
    });

  return (
    <div className="kg-view">
      <header className="kg-view-header">
        <div>
          <h3 className="kg-view-title">剧情主脉演进图</h3>
          <p className="kg-view-desc">分线索显示各故事主脉及支线随章节向前推进的历史记录。</p>
        </div>
        <GraphToolbar searchValue={search} onSearchChange={setSearch} searchPlaceholder="搜索剧情事件…">
          <select
            className="form-input kg-thread-select"
            value={selectedThread}
            onChange={(e) => setSelectedThread(e.target.value)}
          >
            <option value="All">全部线索</option>
            {data?.threads?.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </GraphToolbar>
      </header>

      {loading ? (
        <div className="kg-timeline-loading">加载中…</div>
      ) : (
        <div className="timeline-container-scroll">
          {events.length === 0 ? (
            <p className="kg-empty-text">暂无剧情演进记录</p>
          ) : (
            <div className="plot-timeline-vertical">
              {events.map((ev, idx) => (
                <div key={idx} className="plot-timeline-node">
                  <div className="plot-node-badge">第 {ev.chapter} 章</div>
                  <div className="plot-node-content">
                    <div className="plot-node-thread">{ev.thread}</div>
                    <div className="plot-node-progress">{ev.progress}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

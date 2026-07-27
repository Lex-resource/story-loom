import { useState, useEffect } from 'react';
import { HelpCircle } from 'lucide-react';
import GraphToolbar from './GraphToolbar';

const EVENT_TYPE_LABEL = {
  plant: '埋',
  strengthen: '强',
  resolve: '收',
  cancel: '转',
};

export default function ForeshadowingTimelineView({ projectId, apiBase }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setLoading(true);

    fetch(`${apiBase}/writing/${projectId}/foreshadowing-timeline`)
      .then((res) => (res.ok ? res.json() : { chains: [] }))
      .then((json) => {
        if (!cancelled) setData(json);
      })
      .catch(() => {
        if (!cancelled) setData({ chains: [] });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [projectId, apiBase]);

  const q = search.toLowerCase().trim();
  const chains = (data?.chains || []).filter((chain) => {
    if (!q) return true;
    if (chain.title.toLowerCase().includes(q)) return true;
    return chain.events?.some((ev) => ev.desc.toLowerCase().includes(q));
  });

  return (
    <div className="kg-view">
      <header className="kg-view-header">
        <div>
          <h3 className="kg-view-title">因果时空卷轴</h3>
          <p className="kg-view-desc">
            追踪各主线伏笔在各章节的埋设、增强与回收生命周期。
          </p>
        </div>
        <GraphToolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder="搜索伏笔线索…"
        />
      </header>

      {loading ? (
        <div className="kg-timeline-loading">加载中…</div>
      ) : (
        <div className="timeline-container-scroll">
          {chains.length === 0 ? (
            <p className="kg-empty-text">暂无伏笔演变记录</p>
          ) : (
            chains.map((chain) => {
              const isResolved = chain.events?.some((ev) => ev.type === 'resolve');
              const isCancelled = chain.events?.some((ev) => ev.type === 'cancel');
              return (
                <div key={chain.id || chain.title} className="foreshadow-chain-card">
                  <h4 className="chain-title">
                    <HelpCircle size={16} />
                    <span>{chain.title}</span>
                    {isResolved && (
                      <span style={{
                        fontSize: '11px',
                        padding: '1px 6px',
                        borderRadius: '4px',
                        backgroundColor: 'rgba(16, 185, 129, 0.15)',
                        color: '#34d399',
                        border: '1px solid rgba(16, 185, 129, 0.3)',
                        fontWeight: 'normal',
                        marginLeft: '6px'
                      }}>
                        已回收/已完成
                      </span>
                    )}
                    {isCancelled && (
                      <span style={{
                        fontSize: '11px',
                        padding: '1px 6px',
                        borderRadius: '4px',
                        backgroundColor: 'rgba(239, 68, 68, 0.15)',
                        color: '#f87171',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        fontWeight: 'normal',
                        marginLeft: '6px'
                      }}>
                        已作废
                      </span>
                    )}
                  </h4>
                <div className="foreshadow-timeline-line">
                  {chain.events?.map((ev, idx) => (
                    <div key={idx} className="foreshadow-timeline-event">
                      <div className="event-chapter-badge">第 {ev.chapter} 章</div>
                      <div className={`event-type-dot ${ev.type}`}>
                        {EVENT_TYPE_LABEL[ev.type] || ev.type}
                      </div>
                      <div className="event-description">
                        <strong>[{ev.type.toUpperCase()}]</strong> {ev.desc}
                      </div>
                    </div>
                  ))}
                  {(!chain.events || chain.events.length === 0) && (
                    <p className="text-secondary text-xs" style={{ padding: '10px' }}>
                      暂无演变记录
                    </p>
                  )}
                </div>
              </div>
            );
          })
          )}
        </div>
      )}
    </div>
  );
}

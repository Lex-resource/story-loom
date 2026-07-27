import { useState, useEffect } from 'react';
import { Loader2, BookOpen, X } from 'lucide-react';

export default function ChapterOutlinesOverview({ project, API_BASE, onClose }) {
  const [outlines, setOutlines] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!project) return;
    setLoading(true);
    fetch(`${API_BASE}/writing/${project.id}/chapter-outlines`)
      .then(res => res.json())
      .then(data => {
        // Sort by chapter index ascending
        const sorted = (data || []).sort((a, b) => a.chapter_index - b.chapter_index);
        setOutlines(sorted);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [project, API_BASE]);

  // O-12: Lock body scroll and enable Escape key to close
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  return (
    <div className="overview-modal-overlay" onClick={onClose}>
      <div className="overview-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="overview-modal-header">
          <h2 className="overview-modal-title">
            <BookOpen size={20} style={{ color: 'var(--vermilion)' }} />
            全书分章大纲编排总览
          </h2>
          <button onClick={onClose} className="overview-modal-close" title="关闭">
            <X size={20} />
          </button>
        </div>

        <div className="overview-modal-body">
          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100%', gap: '12px', color: 'var(--text-secondary)' }}>
              <Loader2 className="animate-spin" size={32} style={{ color: 'var(--vermilion)' }} />
              <span>正在展开小说分章大纲卷轴...</span>
            </div>
          ) : outlines.length === 0 ? (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', color: 'var(--text-secondary)', fontSize: '14px' }}>
              <span>书案空空如也，暂未生成任何章节大纲设定。</span>
            </div>
          ) : (
            <div className="overview-timeline">
              {outlines.map((item) => {
                let out;
                if (typeof item.outline === 'string') {
                  try {
                    out = JSON.parse(item.outline);
                  } catch {
                    out = { summary: item.outline };
                  }
                } else {
                  out = item.outline || {};
                }

                // Bilingual key compatibility
                const title = out['本章标题'] || out.title || `第 ${item.chapter_index} 章`;
                const summary = out['本章梗概'] || out.summary || out['概要'] || out['梗概'] || '暂无梗概描述';
                const plotPts = out['核心情节'] || out.key_events || out.plot_points || out['情节'] || [];

                return (
                  <div key={item.chapter_index} className="overview-chapter-item">
                    <div className="overview-chapter-node">
                      {item.chapter_index}
                    </div>
                    <div className="overview-chapter-card">
                      <h3 className="overview-chapter-title">
                        第 {item.chapter_index} 章：{title}
                      </h3>
                      <p className="overview-chapter-summary">{summary}</p>
                      
                      {Array.isArray(plotPts) ? (
                        plotPts.length > 0 && (
                          <ul className="overview-chapter-events">
                            {plotPts.map((p, i) => (
                              <li key={i} className="overview-chapter-event-item">
                                {typeof p === 'string' ? p : p.description || JSON.stringify(p)}
                              </li>
                            ))}
                          </ul>
                        )
                      ) : typeof plotPts === 'string' && plotPts.trim() ? (
                        <ul className="overview-chapter-events">
                          <li className="overview-chapter-event-item">{plotPts}</li>
                        </ul>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

import { Plus, Trash2 } from 'lucide-react';
import EmptyState from '../components/ui/EmptyState';
import StatusBadge from '../components/ui/StatusBadge';
import { DEFAULT_TARGET_CHAPTERS } from '../utils/constants';

export default function ProjectShelf({ projects, loading, onSelectProject, setShowCreateModal, handleDeleteProject }) {
  return (
    <section className="shelf-page" aria-labelledby="shelf-title">
      <div className="shelf-header">
        <div>
          <p className="page-eyebrow">创作项目</p>
          <h1 id="shelf-title">我的作品</h1>
          <p>从大纲、章节到世界设定，继续最近的创作进度。</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
          <Plus size={18} /> 新建作品
        </button>
      </div>

      <div className="projects-grid">
        {loading ? (
          // O-04: Skeleton placeholder cards while loading
          <>
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="project-card project-card--loading" aria-hidden="true">
                <div>
                  <div className="skeleton" style={{ height: '20px', width: '60%', marginBottom: '12px' }} />
                  <div className="skeleton" style={{ height: '14px', width: '40%', marginBottom: '8px' }} />
                  <div
                    className="skeleton"
                    style={{ height: '6px', width: '100%', borderRadius: '4px', marginBottom: '8px' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <div className="skeleton" style={{ height: '12px', width: '30%' }} />
                    <div className="skeleton" style={{ height: '12px', width: '30%' }} />
                  </div>
                </div>
                <div
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}
                >
                  <div className="skeleton" style={{ height: '22px', width: '60px', borderRadius: '4px' }} />
                  <div className="skeleton" style={{ height: '28px', width: '28px', borderRadius: '4px' }} />
                </div>
              </div>
            ))}
          </>
        ) : projects.length === 0 ? (
          <EmptyState onCreate={() => setShowCreateModal(true)} />
        ) : (
          projects.map((p) => {
            const target = p.target_chapters || DEFAULT_TARGET_CHAPTERS;
            const progress = Math.min(100, Math.round(((p.current_chapter || 0) / target) * 100));
            return (
              <article key={p.id} className="project-card">
                <button
                  className="project-card__open"
                  onClick={() => onSelectProject(p)}
                  aria-label={`打开作品：${p.title}`}
                >
                  <div className="project-card__heading">
                    <span className="project-card__index">{String(p.current_chapter || 0).padStart(2, '0')}</span>
                    <StatusBadge status={p.status} pulse={p.status === 'generating'} />
                  </div>
                  <h3 className="card-title">{p.title}</h3>
                  <div className="card-meta">
                    <span>{p.author || '智能体作家'}</span>
                    <span>目标 {target} 章</span>
                  </div>
                  <div className="project-progress" aria-label={`已完成 ${progress}%`}>
                    <span style={{ width: `${progress}%` }} />
                  </div>
                  <div className="project-card__stats">
                    <span>
                      {p.current_chapter || 0} / {target} 章
                    </span>
                    <span>{p.total_chars?.toLocaleString() || 0} 字</span>
                  </div>
                </button>
                <button
                  className="icon-btn project-card__delete"
                  onClick={(e) => handleDeleteProject(p.id, e)}
                  title="删除作品"
                  aria-label={`删除作品：${p.title}`}
                >
                  <Trash2 size={15} />
                </button>
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}

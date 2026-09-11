import { useState, useEffect } from 'react';
import { Sparkles, Loader2 } from 'lucide-react';

export default function ContinueModal({
  isOpen,
  onClose,
  activeProject,
  continueChaptersCount,
  setContinueChaptersCount,
  continueWordCount,
  setContinueWordCount,
  onSubmit,
  actionLoading,
  onUpdateProjectConfig,
}) {
  const [newTargetChapters, setNewTargetChapters] = useState(30);

  useEffect(() => {
    if (isOpen && activeProject?.target_chapters) {
      setNewTargetChapters(activeProject.target_chapters + 10);
    }
  }, [activeProject?.target_chapters, isOpen]);

  // O-12: Lock body scroll and enable Escape key to close
  useEffect(() => {
    if (!isOpen) return;
    document.body.style.overflow = 'hidden';
    const handleEscape = (e) => {
      if (e.key === 'Escape' && !actionLoading) onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, onClose, actionLoading]);

  if (!isOpen) return null;

  const remainingChapters = activeProject
    ? Math.max(0, activeProject.target_chapters - (activeProject.current_chapter || 0))
    : 1;
  const isCompleted = remainingChapters <= 0;

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '400px' }}>
        <h2 className="text-gradient font-bold" style={{ margin: 0 }}>
          续写章节配置
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
          {isCompleted ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <p className="text-sm" style={{ color: 'var(--text-warning)', lineHeight: '1.5', margin: 0 }}>
                本书已达到设定的目标章数 <strong>{activeProject?.target_chapters}</strong> 章（当前已写{' '}
                {activeProject?.current_chapter} 章）。
              </p>
              <div
                className="form-group"
                style={{ display: 'flex', flexDirection: 'column', gap: '6px', margin: '8px 0' }}
              >
                <label className="form-label" style={{ margin: 0 }}>
                  调整目标章数至：
                </label>
                <input
                  type="number"
                  min={(activeProject?.current_chapter || 0) + 1}
                  className="form-input"
                  value={newTargetChapters}
                  onChange={(e) => {
                    const val = parseInt(e.target.value) || 1;
                    setNewTargetChapters(Math.max((activeProject?.current_chapter || 0) + 1, val));
                  }}
                />
                <p className="text-xs text-secondary" style={{ margin: 0 }}>
                  调大目标章数即可继续续写本作品。
                </p>
              </div>
              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={onClose} disabled={actionLoading}>
                  取消
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={actionLoading}
                  onClick={async () => {
                    if (onUpdateProjectConfig) {
                      const success = await onUpdateProjectConfig({
                        word_count_per_chapter:
                          activeProject?.word_count_per_chapter !== undefined
                            ? activeProject.word_count_per_chapter
                            : 3000,
                        mode: activeProject?.mode || 'step',
                        optimize_interval:
                          activeProject?.optimize_interval !== undefined ? activeProject.optimize_interval : 10,
                        target_chapters: newTargetChapters,
                      });
                      if (success) {
                        setContinueChaptersCount(1);
                        onSubmit();
                      }
                    }
                  }}
                >
                  {actionLoading ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />}{' '}
                  修改并继续续写
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="form-group">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '6px',
                  }}
                >
                  <label className="form-label" style={{ margin: 0 }}>
                    续写章数
                  </label>
                  <button
                    className="btn btn-secondary"
                    style={{ padding: '2px 8px', fontSize: '11px', height: '24px', lineHeight: '20px' }}
                    onClick={() => setContinueChaptersCount(remainingChapters)}
                  >
                    直接完结本书 (余 {remainingChapters} 章)
                  </button>
                </div>
                <input
                  type="number"
                  min="1"
                  max={remainingChapters}
                  className="form-input"
                  value={continueChaptersCount}
                  onChange={(e) => {
                    const val = parseInt(e.target.value) || 1;
                    setContinueChaptersCount(Math.min(remainingChapters, Math.max(1, val)));
                  }}
                />
                <p className="text-xs text-secondary" style={{ marginTop: '4px' }}>
                  最大限制为完结本书所需的剩余章数（最多续写 {remainingChapters} 章）。
                </p>
              </div>

              <div className="form-group">
                <label className="form-label">每章字数 (输入0为无限制)</label>
                <input
                  type="number"
                  className="form-input"
                  value={continueWordCount}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    setContinueWordCount(isNaN(val) ? 0 : val);
                  }}
                  placeholder="例如：3000"
                />
              </div>

              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={onClose}>
                  取消
                </button>
                <button type="button" className="btn btn-primary" onClick={onSubmit} disabled={actionLoading}>
                  {actionLoading ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />} 开始续写
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

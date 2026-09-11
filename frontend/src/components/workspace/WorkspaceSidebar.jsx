import { useState, memo, useCallback } from 'react';
import { AlertTriangle, Info } from 'lucide-react';
import { useProjectStore, useUIStore } from '../../store/useStore';
import { getReviewFlags, getMaxSeverity, chapterDisplayTitle } from '../../utils/chapterHelpers';

const REVIEW_FLAG_LABELS = {
  backup_model: '备用模型',
  force_corrected: '强制发布',
  editor_force_revised: '编辑强制精修',
  validator_auto_force_saved: '法则自动放行',
  pending_review: '待人工审核',
  short_story_full_review: '全文审校',
};

function getReviewFlagLabel(type) {
  return REVIEW_FLAG_LABELS[type] || type || '审计标记';
}

function getFlagIconColor(severity) {
  if (severity === 'error') return 'var(--color-red, #ef4444)';
  if (severity === 'warning') return 'var(--color-amber, #f59e0b)';
  return 'var(--color-blue, #3b82f6)';
}

function getFlagTextColor(severity) {
  if (severity === 'error') return '#fca5a5';
  if (severity === 'warning') return '#fcd34d';
  return '#93c5fd';
}

const ChapterListItem = memo(function ChapterListItem({ ch, isActive, onSelectChapter }) {
  const [isHovered, setIsHovered] = useState(false);

  const flags = getReviewFlags(ch);
  const sev = getMaxSeverity(flags);
  const ReviewFlagIcon = sev === 'info' ? Info : AlertTriangle;

  return (
    <button
      type="button"
      className={`chapter-item ${isActive ? 'active' : ''}`}
      onClick={() => onSelectChapter(ch.chapter_index)}
    >
      <div style={{ maxWidth: '180px', minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span className="font-semibold text-sm truncate" style={{ minWidth: 0 }}>
            第{ch.chapter_index}章
          </span>
          {flags.length > 0 && (
            <div
              style={{ position: 'relative', display: 'inline-flex', flex: '0 0 auto' }}
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
            >
              <ReviewFlagIcon
                size={14}
                style={{
                  color: getFlagIconColor(sev),
                  cursor: 'pointer',
                }}
              />
              {isHovered && (
                <div
                  style={{
                    position: 'absolute',
                    left: '20px',
                    top: '-10px',
                    zIndex: 9999,
                    width: '320px',
                    maxWidth: 'min(320px, calc(100vw - 48px))',
                    backgroundColor: '#1f2937',
                    color: '#fff',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.2)',
                    border: '1px solid #374151',
                    fontSize: '11px',
                    lineHeight: '1.4',
                    textAlign: 'left',
                    whiteSpace: 'normal',
                    overflowWrap: 'break-word',
                  }}
                >
                  <div
                    style={{
                      fontWeight: 'bold',
                      borderBottom: '1px solid #374151',
                      paddingBottom: '4px',
                      marginBottom: '6px',
                      color: '#f3f4f6',
                    }}
                  >
                    章节审计与警告标记
                  </div>
                  <ul style={{ listStyleType: 'disc', paddingLeft: '14px', margin: 0 }}>
                    {flags.map((flag, fIdx) => (
                      <li key={fIdx} style={{ marginBottom: '4px' }}>
                        <span
                          style={{
                            color: getFlagTextColor(flag.severity),
                            fontWeight: 500,
                          }}
                        >
                          [{getReviewFlagLabel(flag.type)}]
                        </span>{' '}
                        {flag.detail}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
        <p className="text-xs text-secondary truncate">{chapterDisplayTitle(ch.title)}</p>
      </div>
    </button>
  );
});

export default function WorkspaceSidebar({
  loadChapterDetails,
  openContinueModal,
  onOpenChapterOverview,
  setAutoFollowGeneration,
  onNavigateToEditor,
}) {
  const chapters = useProjectStore((state) => state.chapters);
  const activeChapter = useProjectStore((state) => state.activeChapter);
  const activeProject = useProjectStore((state) => state.activeProject);

  const handleSelectChapter = useCallback(
    (chapterIndex) => {
      setAutoFollowGeneration?.(false);
      loadChapterDetails(activeProject.id, chapterIndex);
      onNavigateToEditor?.();
    },
    [loadChapterDetails, activeProject, setAutoFollowGeneration, onNavigateToEditor],
  );

  return (
    <div className="workspace-left">
      <div style={{ padding: '16px', borderBottom: '1px solid var(--border-muted)', background: 'rgba(0,0,0,0.1)' }}>
        <h3 style={{ margin: 0, fontSize: '16px' }}>章节目录</h3>
      </div>
      <div className="chapters-list">
        <button
          type="button"
          className={`chapter-item ${!activeChapter ? 'active' : ''}`}
          onClick={() => {
            setAutoFollowGeneration?.(false);
            useProjectStore.getState().setActiveChapter(null);
            useProjectStore.getState().setEditedOutline('');
            useUIStore.getState().setWorkspaceStep('structure');
            useUIStore.getState().setOutlineMode('visual');
            onNavigateToEditor?.();
          }}
          style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', marginBottom: '4px', paddingBottom: '8px' }}
        >
          <div className="truncate" style={{ maxWidth: '180px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span
                className="font-semibold text-sm"
                style={{ color: !activeChapter ? 'var(--color-blue, #3b82f6)' : 'var(--text-primary)' }}
              >
                📚 全书骨架大纲
              </span>
            </div>
            <p className="text-xs text-secondary truncate">全局世界观与剧情设定</p>
          </div>
        </button>
        <button
          type="button"
          className="chapter-item"
          onClick={() => {
            setAutoFollowGeneration?.(false);
            onOpenChapterOverview?.();
          }}
          style={{
            borderBottom: '1px solid rgba(255,255,255,0.05)',
            marginBottom: '8px',
            paddingBottom: '12px',
            cursor: 'pointer',
          }}
        >
          <div className="truncate" style={{ maxWidth: '180px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span className="font-semibold text-sm" style={{ color: 'var(--gold)' }}>
                📖 分章大纲总览
              </span>
            </div>
            <p className="text-xs text-secondary truncate">查看全书各章节的大纲摘要</p>
          </div>
        </button>
        {chapters.map((ch) => (
          <ChapterListItem
            key={ch.chapter_index}
            ch={ch}
            isActive={activeChapter?.chapter_index === ch.chapter_index}
            onSelectChapter={handleSelectChapter}
          />
        ))}
      </div>
      <div style={{ padding: '16px', borderTop: '1px solid var(--border-muted)', background: 'rgba(0,0,0,0.1)' }}>
        <button className="btn btn-primary" style={{ width: '100%' }} onClick={openContinueModal}>
          续写
        </button>
      </div>
    </div>
  );
}

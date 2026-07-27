import { Loader2, Info } from 'lucide-react';
import EvaluationRadar from '../EvaluationRadar';

export default function WorkspaceEditor({
  workspaceStep,
  writerSubTab,
  setWriterSubTab,
  activeChapter,
  editedTitle,
  setEditedTitle,
  editedContent,
  setEditedContent,
  isEditorStreaming,
  hasEvaluations,
  mergedEvaluations
}) {
  if (workspaceStep !== 'writer') return null;

  const finalContent = editedContent || activeChapter?.edited_content || activeChapter?.content || activeChapter?.draft_content || '';
  const finalPlaceholder = activeChapter?.draft_content ? '精修稿正在生成中...' : '正文正在生成中...';
  const draftContent = activeChapter?.draft_content || '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0, gap: '12px' }}>
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-muted)', paddingBottom: '12px' }}>
        <button className={`btn ${writerSubTab === 'compare' ? 'btn-primary' : 'btn-secondary'}`} style={{ padding: '4px 12px', fontSize: '13px' }} onClick={() => setWriterSubTab('compare')}>
          双屏对比
        </button>
        <button className={`btn ${writerSubTab === 'draft' ? 'btn-primary' : 'btn-secondary'}`} style={{ padding: '4px 12px', fontSize: '13px' }} onClick={() => setWriterSubTab('draft')}>
          仅看初稿
        </button>
        <button className={`btn ${writerSubTab === 'final' ? 'btn-primary' : 'btn-secondary'}`} style={{ padding: '4px 12px', fontSize: '13px' }} onClick={() => setWriterSubTab('final')}>
          仅看终稿
        </button>
        <button className={`btn ${writerSubTab === 'evaluations' ? 'btn-primary' : 'btn-secondary'}`} style={{ padding: '4px 12px', fontSize: '13px' }} onClick={() => setWriterSubTab('evaluations')}>
          AI 润色打分 {isEditorStreaming && <Loader2 className="animate-spin" size={12} style={{ marginLeft: 4 }} />}
        </button>
      </div>

      {writerSubTab === 'compare' && (
        <div className="comparative-editor">
          <div className="editor-box">
            <div className="editor-box-header">
              <span>初稿 (Draft Content)</span>
              <span className="text-xs text-secondary">字数: {draftContent.length}</span>
            </div>
            <textarea
              className="editor-textarea"
              readOnly
              value={draftContent || '初稿正在执笔生成中...'}
            />
          </div>

          <div className="editor-box">
            <div className="editor-box-header">
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <span>精修稿 (Edited Content)</span>
                <input
                  value={editedTitle}
                  onChange={(e) => setEditedTitle(e.target.value)}
                  className="form-input"
                  style={{ padding: '2px 6px', fontSize: '13px', width: '180px' }}
                />
              </div>
              <span className="text-xs text-secondary">字数: {finalContent.length}</span>
            </div>
            <textarea
              className="editor-textarea"
              value={finalContent}
              placeholder={finalPlaceholder}
              onChange={(e) => setEditedContent(e.target.value)}
            />
          </div>
        </div>
      )}

      {writerSubTab === 'draft' && (
        <div className="editor-box" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minHeight: 0, height: 'auto' }}>
          <div className="editor-box-header">
            <span>初稿 (Draft Content)</span>
            <span className="text-xs text-secondary">字数: {draftContent.length}</span>
          </div>
          <textarea
            className="editor-textarea"
            readOnly
            style={{ flexGrow: 1, minHeight: 0 }}
            value={draftContent || '初稿正在执笔生成中...'}
          />
        </div>
      )}

      {writerSubTab === 'final' && (
        <div className="editor-box" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minHeight: 0, height: 'auto' }}>
          <div className="editor-box-header">
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <span>精修终稿 (Edited Content)</span>
              <input
                value={editedTitle}
                onChange={(e) => setEditedTitle(e.target.value)}
                className="form-input"
                style={{ padding: '2px 6px', fontSize: '13px', width: '180px' }}
              />
            </div>
            <span className="text-xs text-secondary">字数: {finalContent.length}</span>
          </div>
          <textarea
            className="editor-textarea"
            style={{ flexGrow: 1, minHeight: 0 }}
            value={finalContent}
            placeholder={finalPlaceholder}
            onChange={(e) => setEditedContent(e.target.value)}
          />
        </div>
      )}

      {writerSubTab === 'evaluations' && (
        <div style={{ flexGrow: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px', padding: '20px', borderRadius: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-muted)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '15px', fontWeight: 600 }}>编辑智能体 5 维度润色打分表</span>
            {activeChapter?.editor_decision && (
              <span className={`warning-badge ${activeChapter.editor_decision === 'proceed' ? 'info' : activeChapter.editor_decision === 'revise' ? 'warning' : 'error'}`}>
                判定结果: {activeChapter.editor_decision === 'proceed' ? '直接采纳 (Proceed)' : activeChapter.editor_decision === 'revise' ? '精修润色 (Revise)' : '重写初稿 (Rewrite)'}
              </span>
            )}
          </div>

          {hasEvaluations || isEditorStreaming ? (
            <EvaluationRadar
              evaluations={mergedEvaluations}
              streaming={isEditorStreaming}
            />
          ) : (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
              <Info size={40} style={{ color: 'var(--color-blue, #3b82f6)', marginBottom: '10px' }} />
              <p>暂无打分数据</p>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>本章尚未由编辑智能体进行五维润色打分评估。</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

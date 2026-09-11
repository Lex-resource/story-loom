import { AlertTriangle, Loader2, Info, Check, RefreshCw, Sparkles } from 'lucide-react';

export default function WorkspaceValidator({
  workspaceStep,
  isValidatorStreaming,
  validatorStreamLog,
  validationResult,
  setWorkspaceStep,
  setWriterSubTab,
  handleRewriteChapter,
  handleForcePublish,
  activeChapter,
}) {
  if (workspaceStep !== 'validator') return null;

  const storyIssues = validationResult?.story_issues || [];
  const hasHardIssues =
    validationResult?.errors?.length > 0 ||
    validationResult?.warnings?.length > 0 ||
    validationResult?.infos?.length > 0;
  const hasStoryIssues = storyIssues.length > 0;
  const hasVisibleIssues = hasHardIssues || hasStoryIssues;

  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', gap: '20px', overflowY: 'auto', flexGrow: 1, minHeight: 0 }}
    >
      <div className="glass-panel" style={{ padding: '20px', borderRadius: '8px' }}>
        <h3 style={{ marginTop: 0 }} className="text-gradient">
          天道法则自动审计
        </h3>
        <p className="text-secondary text-sm">
          此审查对比了当前章节正文与活文档中已编译的设定（如林枫境界、死伤状态、法术规则等）。如有逻辑严重偏离，将阻止流程自动进入下一章。
        </p>
        {isValidatorStreaming && (
          <div
            className="warning-badge warning pulsing-border"
            style={{ marginTop: '12px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <Loader2 className="animate-spin" size={14} />
            法则审查流式输出中…
          </div>
        )}
      </div>

      {(isValidatorStreaming || validatorStreamLog) && (
        <div className="validator-stream-panel">
          <div className="validator-stream-header">审计过程实时日志</div>
          <pre className="validator-stream-log">{validatorStreamLog || '等待审计输出…'}</pre>
        </div>
      )}

      {validationResult ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {validationResult.errors?.map((err, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'flex-start',
                padding: '12px',
                borderRadius: '8px',
                background: 'rgba(244, 63, 94, 0.1)',
                border: '1px solid rgba(244, 63, 94, 0.3)',
              }}
            >
              <AlertTriangle className="text-red-500" style={{ color: 'var(--color-red)', flexShrink: 0 }} />
              <div>
                <span className="font-semibold text-sm">【拦截级 (Blocker)】 逻辑错乱/吃设定</span>
                <p className="text-sm text-secondary mt-1">{err}</p>
              </div>
            </div>
          ))}
          {validationResult.warnings?.map((warn, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'flex-start',
                padding: '12px',
                borderRadius: '8px',
                background: 'rgba(245, 158, 11, 0.1)',
                border: '1px solid rgba(245, 158, 11, 0.3)',
              }}
            >
              <AlertTriangle className="text-amber-500" style={{ color: 'var(--color-amber)', flexShrink: 0 }} />
              <div>
                <span className="font-semibold text-sm">【警告级 (Warning)】 潜在设定出入</span>
                <p className="text-sm text-secondary mt-1">{warn}</p>
              </div>
            </div>
          ))}
          {validationResult.infos?.map((info, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'flex-start',
                padding: '12px',
                borderRadius: '8px',
                background: 'rgba(59, 130, 246, 0.1)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
              }}
            >
              <Info className="text-blue-500" style={{ color: 'var(--color-blue)', flexShrink: 0 }} />
              <div>
                <span className="font-semibold text-sm">【提示级 (Info)】 细节与文笔优化提示</span>
                <p className="text-sm text-secondary mt-1">{info}</p>
              </div>
            </div>
          ))}
          {storyIssues.map((issue, idx) => (
            <div
              key={`story-${idx}`}
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'flex-start',
                padding: '12px',
                borderRadius: '8px',
                background: 'rgba(168, 85, 247, 0.08)',
                border: '1px solid rgba(168, 85, 247, 0.28)',
              }}
            >
              <Sparkles style={{ color: '#a855f7', flexShrink: 0 }} />
              <div>
                <span className="font-semibold text-sm">
                  【故事与文笔优化提示】 {issue.category ? issue.category : 'story'}
                </span>
                <p className="text-sm text-secondary mt-1">{issue.message || issue.description}</p>
              </div>
            </div>
          ))}
          {!hasVisibleIssues && !validationResult.streaming && (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
              <Check style={{ color: 'var(--color-emerald)' }} size={48} />
              <p className="mt-2 font-semibold" style={{ color: 'var(--text-primary)' }}>
                未发现逻辑冲突与设定矛盾
              </p>
              <p className="text-xs text-secondary mt-1">本章设定符合编译法则。</p>
            </div>
          )}
          {validationResult.streaming && !hasVisibleIssues && (
            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)', fontSize: '13px' }}>
              <Loader2 className="animate-spin" size={24} style={{ marginBottom: '8px', color: 'var(--vermilion)' }} />
              <p>深度逻辑审计进行中，问题将实时解析展示…</p>
            </div>
          )}

          {validationResult.errors?.length > 0 && (
            <div
              className="glass-panel"
              style={{
                padding: '16px',
                borderRadius: '8px',
                border: '1px dashed var(--color-red, #ef4444)',
                background: 'rgba(244, 63, 94, 0.05)',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                marginTop: '10px',
              }}
            >
              <span
                style={{
                  fontWeight: 'bold',
                  color: 'var(--color-red, #ef4444)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <AlertTriangle size={16} /> 发现阻断级设定矛盾，天道已拦截并暂停创作流。请选择处理方式：
              </span>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    setWorkspaceStep('writer');
                    setWriterSubTab('final');
                  }}
                  style={{ fontSize: '13px', padding: '6px 12px' }}
                >
                  前往【精修终稿】修改正文
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={handleRewriteChapter}
                  style={{ fontSize: '13px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                >
                  <RefreshCw size={14} /> AI 重新写本章
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => {
                    if (
                      confirm('确认强制发布放行吗？这会忽略本章的逻辑报错，强制将该章标记为已发布并继续后面的生成。')
                    ) {
                      handleForcePublish(activeChapter.chapter_index);
                    }
                  }}
                  style={{ fontSize: '13px', padding: '6px 12px' }}
                >
                  强制发布放行（天道强制通过）
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
          <Info size={40} style={{ color: 'var(--color-blue, #3b82f6)', marginBottom: '10px' }} />
          <p>暂无审计数据</p>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>本章尚未由天道智能体进行逻辑审查。</p>
        </div>
      )}
    </div>
  );
}

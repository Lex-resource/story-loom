import { AlertTriangle, Info, Check, Loader2, Sparkles } from 'lucide-react';

export default function ValidatorStreamPanel({
  phase,
  streamText,
  validationResult,
  isStreaming,
}) {
  const hasResult = validationResult && (
    validationResult.errors?.length > 0 ||
    validationResult.warnings?.length > 0 ||
    validationResult.infos?.length > 0 ||
    validationResult.story_issues?.length > 0
  );

  return (
    <div className="validator-stream-panel">
      {isStreaming && (
        <div className="validator-stream-status">
          <Loader2 className="animate-spin" size={16} />
          <span>
            {phase === 'quick' && '快速语法与词汇合规检测中…'}
            {phase === 'llm' && '天道法则 LLM 深度审计流式输出中…'}
            {!phase && '天道法则校验进行中…'}
          </span>
        </div>
      )}

      {hasResult ? (
        <div className="validator-stream-issues">
          {validationResult.errors?.map((err, idx) => (
            <div key={`e-${idx}`} className="validator-issue validator-issue--error">
              <AlertTriangle size={16} />
              <div>
                <strong>【拦截级】</strong>
                <p>{err}</p>
              </div>
            </div>
          ))}
          {validationResult.warnings?.map((warn, idx) => (
            <div key={`w-${idx}`} className="validator-issue validator-issue--warning">
              <AlertTriangle size={16} />
              <div>
                <strong>【警告级】</strong>
                <p>{warn}</p>
              </div>
            </div>
          ))}
          {validationResult.infos?.map((info, idx) => (
            <div key={`i-${idx}`} className="validator-issue validator-issue--info">
              <Info size={16} />
              <div>
                <strong>【提示级】</strong>
                <p>{info}</p>
              </div>
            </div>
          ))}
          {validationResult.story_issues?.map((issue, idx) => (
            <div key={`s-${idx}`} className="validator-issue validator-issue--story">
              <Sparkles size={16} />
              <div>
                <strong>【故事与文笔优化提示】</strong>
                <p>{issue.message || issue.description}</p>
              </div>
            </div>
          ))}
        </div>
      ) : isStreaming ? (
        <div className="validator-stream-raw">
          <div className="validator-stream-raw-header">审计流式输出</div>
          <pre>{streamText || '等待校验器响应…'}</pre>
        </div>
      ) : (
        <div className="validator-stream-empty">
          <Check size={40} style={{ color: 'var(--jade)' }} />
          <p>未发现逻辑冲突与设定矛盾</p>
        </div>
      )}
    </div>
  );
}

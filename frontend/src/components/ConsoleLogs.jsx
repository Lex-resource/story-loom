import { useEffect, useRef, useState } from 'react';
import { Activity, Pause, Play, RefreshCw, Send, Search, Eye, X } from 'lucide-react';

export default function ConsoleLogs({
  wsLogs,
  streamingText,
  handlePause,
  handleResume,
  handleRewriteChapter,
  customPrompt,
  setCustomPrompt,
  handleInsertPrompt,
  elapsedSeconds,
  isGenerating,
  actionLoading
}) {
  const consoleEndRef = useRef(null);
  const [inspectedLog, setInspectedLog] = useState(null);

  // O-07: Limit rendered DOM nodes — only show the last 200 log entries
  const MAX_VISIBLE_LOGS = 200;
  const visibleLogs = wsLogs.slice(-MAX_VISIBLE_LOGS);
  const logOffset = wsLogs.length - visibleLogs.length;
  const hasTruncatedLogs = wsLogs.length > MAX_VISIBLE_LOGS;

  // O-03: Only scroll the console container itself, not the entire page.
  // Auto-follow the latest log only when the user is already at (or near) the
  // bottom; if they've scrolled up to read history, don't yank them back down.
  useEffect(() => {
    const container = consoleEndRef.current?.parentElement;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceFromBottom <= 80) {
      container.scrollTop = container.scrollHeight;
    }
  }, [wsLogs, streamingText]);

  return (
    <div className="floating-console">
      <div className="pane-header console-header">
        <div className="console-title">
          <Activity size={16} />
          <span className="font-semibold text-sm">生成日志</span>
          {isGenerating && (
            <span style={{ fontSize: '12px', color: 'var(--vermilion)', fontWeight: 500, marginLeft: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <RefreshCw className="spin-slow" size={12} />
              已运行 {elapsedSeconds} 秒
            </span>
          )}
        </div>
        
        <div className="console-actions">
          <button className="btn btn-secondary console-action" onClick={handlePause} title="暂停生成" aria-label="暂停生成">
            <Pause size={14} /> <span>暂停</span>
          </button>
          <button className="btn btn-secondary console-action" onClick={handleResume} title="继续生成" aria-label="继续生成">
            <Play size={14} /> <span>继续</span>
          </button>
          <button className="btn btn-danger console-action" onClick={handleRewriteChapter} disabled={actionLoading} title="重写本章" aria-label="重写本章">
            <RefreshCw size={14} /> <span>重写本章</span>
          </button>
        </div>
      </div>

      <div className="console-logs">
        {hasTruncatedLogs && (
          <div style={{ padding: '4px 8px', fontSize: '11px', color: 'var(--text-secondary)', background: 'rgba(184, 134, 11, 0.08)', borderBottom: '1px solid var(--border-muted)' }}>
            仅显示最近 {MAX_VISIBLE_LOGS} 条日志（共 {wsLogs.length} 条）
          </div>
        )}
        {visibleLogs.map((log, idx) => (
          <div key={logOffset + idx} className={`log-entry ${log.styleClass}`}>
            <span style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
              <span style={{ flex: 1 }}>
                <span>[{log.time}] </span>
                <span className="font-bold">[{log.source}]: </span>
                <span>{log.text}</span>
              </span>
              {log.llm_payload && (
                <button 
                  onClick={() => setInspectedLog({ type: 'request', data: log.llm_payload })}
                  className="btn btn-secondary" 
                  style={{ padding: '2px 6px', fontSize: '11px', flexShrink: 0, height: '22px' }}
                >
                  <Search size={12} style={{ marginRight: '4px' }}/> 查看请求明细
                </button>
              )}
              {log.llm_response && (
                <button 
                  onClick={() => setInspectedLog({ type: 'response', data: log.llm_response })}
                  className="btn btn-secondary" 
                  style={{ padding: '2px 6px', fontSize: '11px', flexShrink: 0, height: '22px' }}
                >
                  <Eye size={12} style={{ marginRight: '4px' }}/> 查看原始响应
                </button>
              )}
            </span>
          </div>
        ))}
          <div ref={consoleEndRef} />
        </div>

      {/* Manual prompt intervention bar */}
      <div className="intervention-bar" style={{ display: 'flex', gap: '8px', padding: '8px', borderTop: '1px solid var(--border-muted)', background: 'rgba(0,0,0,0.2)' }}>
        <input 
          className="form-input"
          style={{ flex: 1, margin: 0, padding: '4px 8px', fontSize: '13px' }}
          value={customPrompt}
          onChange={(e) => setCustomPrompt(e.target.value)}
          placeholder="发送天道干预插话（例如：“下一章让主角陷入险境”、“让配角A说一句...”）..."
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleInsertPrompt();
          }}
        />
        <button className="btn btn-primary" style={{ padding: '4px 12px' }} onClick={handleInsertPrompt}>
          <Send size={14} /> 发送干预
        </button>
      </div>

      {/* LLM Inspector Modal */}
      {inspectedLog && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
          zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border-muted)',
            borderRadius: '12px', width: '80vw', height: '80vh',
            display: 'flex', flexDirection: 'column', boxShadow: '0 8px 32px rgba(0,0,0,0.3)'
          }}>
            <div style={{
              padding: '16px 20px', borderBottom: '1px solid var(--border-muted)',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              background: 'rgba(255,255,255,0.02)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {inspectedLog.type === 'request' ? <Search size={18} className="text-gold" /> : <Eye size={18} className="text-gold" />}
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>
                  {inspectedLog.type === 'request' ? `AI 请求明细 (${inspectedLog.data.model})` : 'AI 原始响应'}
                </h3>
              </div>
              <button className="icon-btn" onClick={() => setInspectedLog(null)} aria-label="关闭检查器">
                <X size={20} />
              </button>
            </div>
            
            <div style={{ flex: 1, overflow: 'auto', padding: '20px', background: 'var(--bg-primary)' }}>
              {inspectedLog.type === 'request' && (
                <>
                  <div style={{ marginBottom: '12px', fontSize: '12px', color: 'var(--text-secondary)' }}>模型: {inspectedLog.data.model}</div>
                  <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '8px' }}>完整 Prompt:</div>
                  <pre style={{ 
                    whiteSpace: 'pre-wrap', background: 'rgba(0,0,0,0.2)', padding: '16px', 
                    borderRadius: '8px', border: '1px solid var(--border-muted)', fontSize: '13px',
                    lineHeight: 1.5, fontFamily: 'monospace', margin: 0
                  }}>
                    {inspectedLog.data.prompt}
                  </pre>
                </>
              )}
              {inspectedLog.type === 'response' && (
                <>
                  <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
                    <span className="info-badge">耗时: {inspectedLog.data.latency_ms} ms</span>
                    <span className="info-badge">输入 Tokens: {inspectedLog.data.tokens?.input}</span>
                    <span className="info-badge">输出 Tokens: {inspectedLog.data.tokens?.output}</span>
                    {inspectedLog.data.tokens?.cache_hit > 0 && (
                      <span className="info-badge">缓存命中 Tokens: {inspectedLog.data.tokens?.cache_hit}</span>
                    )}
                  </div>
                  <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '8px' }}>原始 Response (JSON / Text):</div>
                  <pre style={{ 
                    whiteSpace: 'pre-wrap', background: 'rgba(0,0,0,0.2)', padding: '16px', 
                    borderRadius: '8px', border: '1px solid var(--border-muted)', fontSize: '13px',
                    lineHeight: 1.5, fontFamily: 'monospace', margin: 0
                  }}>
                    {inspectedLog.data.response}
                  </pre>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

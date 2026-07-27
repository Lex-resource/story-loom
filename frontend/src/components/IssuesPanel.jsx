import { useState, useEffect } from 'react';
import { Loader2, Bug, CheckCircle2, AlertTriangle, AlertCircle, RefreshCw } from 'lucide-react';

export default function IssuesPanel({ project, API_BASE }) {
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState({});

  const fetchIssues = async () => {
    if (!project) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/writing/${project.id}/issue-summaries`);
      if (res.ok) {
        const data = await res.json();
        setIssues(data || []);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchIssues();
  }, [project]);

  const toggleIssue = async (id, currentEnabled) => {
    setToggling(prev => ({ ...prev, [id]: true }));
    try {
      const res = await fetch(`${API_BASE}/writing/${project.id}/issue-summaries/${id}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !currentEnabled })
      });
      if (res.ok) {
        setIssues(prev => prev.map(i => i.id === id ? { ...i, enabled: !i.enabled } : i));
      }
    } catch (e) {
      console.error(e);
    }
    setToggling(prev => ({ ...prev, [id]: false }));
  };

  if (loading) {
    return (
      <div className="panel-loading">
        <Loader2 className="animate-spin" size={24} />
        正在加载全局漏洞与诊断数据...
      </div>
    );
  }

  const activeIssues = issues.filter(i => i.enabled);
  const resolvedIssues = issues.filter(i => !i.enabled);

  const getSeverityIcon = (sev) => {
    if (sev === 'error') return <AlertCircle size={16} className="issues-sev-error" />;
    if (sev === 'warning') return <AlertTriangle size={16} className="issues-sev-warning" />;
    return <Bug size={16} className="issues-sev-info" />;
  };

  const renderIssue = (issue) => (
    <div key={issue.id} className={`issues-card ${issue.enabled ? '' : 'resolved'}`}>
      <div className="issues-card-header">
        <div className="issues-card-title-wrap">
          {issue.enabled ? getSeverityIcon(issue.severity) : <CheckCircle2 size={16} className="issues-sev-resolved" />}
          <span className={`issues-card-title ${issue.enabled ? '' : 'resolved'}`}>{issue.category}</span>
        </div>
        <button
          onClick={() => toggleIssue(issue.id, issue.enabled)}
          disabled={toggling[issue.id]}
          className={`issues-toggle-btn ${issue.enabled ? 'active' : 'resolved'}`}
        >
          {toggling[issue.id] ? <Loader2 className="animate-spin" size={12} /> : (issue.enabled ? '标记为已解决' : '重新开启')}
        </button>
      </div>
      <p className={`issues-card-summary ${issue.enabled ? '' : 'resolved'}`}>{issue.summary}</p>
      {issue.examples && issue.examples.length > 0 && (
        <div className="issues-card-examples">
          <strong>示例:</strong> {issue.examples.join('; ')}
        </div>
      )}
    </div>
  );

  return (
    <div className="issues-panel">
      <div className="issues-panel-header">
        <h2 className="issues-panel-title">
          <Bug size={16} />
          全局 Bug 追踪面板
        </h2>
        <button onClick={fetchIssues} className="issues-refresh-btn" title="刷新列表">
          <RefreshCw size={16} />
        </button>
      </div>
      
      <div className="issues-panel-body">
        {issues.length === 0 ? (
          <div className="issues-panel-empty">暂无任何未修复的剧情或逻辑漏洞，干得漂亮！</div>
        ) : (
          <>
            {activeIssues.length > 0 && (
              <div className="issues-section">
                <h3 className="issues-section-title active">待修复问题 ({activeIssues.length})</h3>
                {activeIssues.map(renderIssue)}
              </div>
            )}
            {resolvedIssues.length > 0 && (
              <div>
                <h3 className="issues-section-title resolved">已解决 ({resolvedIssues.length})</h3>
                {resolvedIssues.map(renderIssue)}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

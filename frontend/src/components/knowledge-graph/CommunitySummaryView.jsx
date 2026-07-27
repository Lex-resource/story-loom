import { useState, useEffect } from 'react';
import { Loader2, Users } from 'lucide-react';

export default function CommunitySummaryView({ project, API_BASE }) {
  const [summaries, setSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!project) return;
    setLoading(true);
    fetch(`${API_BASE}/writing/${project.id}/community-summary`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch community summaries');
        return res.json();
      })
      .then((data) => {
        setSummaries(data || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setError(err.message);
        setLoading(false);
      });
  }, [project, API_BASE]);

  if (loading) {
    return (
      <div className="panel-loading">
        <Loader2 className="animate-spin" size={24} />
        正在让大模型梳理势力圈子，请稍候...
      </div>
    );
  }

  if (error) {
    return (
      <div className="community-summary-error">
        {error}
      </div>
    );
  }

  if (summaries.length === 0) {
    return (
      <div className="community-summary-empty">
        没有发现明显的社群势力划分。
      </div>
    );
  }

  return (
    <div className="community-summary-list">
      {summaries.map((s, idx) => (
        <div key={idx} className="community-summary-card">
          <div className="community-summary-header">
            <Users size={20} />
            <h3 className="community-summary-title">{s.label}</h3>
          </div>
          <p className="community-summary-text">
            {s.summary}
          </p>
          <div className="community-summary-tags">
            {s.nodes.map((node, i) => (
              <span key={i} className="community-summary-tag">
                {node}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

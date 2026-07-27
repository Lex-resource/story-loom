const STATUS_LABELS = {
  generating: '创作中',
  completed: '已完结',
  paused: '已暂停',
  failed: '异常',
  pending_review: '待审阅',
};

export default function StatusBadge({ status, label, pulse = false }) {
  return (
    <span className={`status-badge status-badge--${status || 'neutral'}${pulse ? ' status-badge--pulse' : ''}`}>
      <span className="status-badge__dot" aria-hidden="true" />
      {label || STATUS_LABELS[status] || '未开始'}
    </span>
  );
}

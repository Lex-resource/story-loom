/** SystemConfigs 页共享的小控件(主组件与两个 system 视图都用)。 */

export function Meta({ label, value, hint }) {
  return (
    <span style={{ color: 'var(--ink-light)' }}>
      {label}：<strong style={{ color: 'var(--ink)' }}>{value}</strong>
      {hint ? <span style={{ color: 'var(--ink-lighter)' }}> （{hint}）</span> : null}
    </span>
  );
}

export function Toggle({ checked, onChange, label, hint }) {
  return (
    <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
      <input
        type="checkbox"
        checked={Boolean(checked)}
        onChange={(e) => onChange(e.target.checked)}
        style={{ marginTop: '3px' }}
      />
      <span>
        {label}
        {hint && <div style={{ fontSize: '11px', color: 'var(--ink-lighter)' }}>{hint}</div>}
      </span>
    </label>
  );
}

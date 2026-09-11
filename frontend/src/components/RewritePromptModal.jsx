import { Loader2, RefreshCw, X } from 'lucide-react';

export default function RewritePromptModal({
  isOpen,
  title,
  value,
  onChange,
  onClose,
  onSubmit,
  actionLoading,
  required = false,
  placeholder,
  submitLabel,
}) {
  if (!isOpen) return null;

  const canSubmit = !actionLoading && (!required || value.trim());

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="rewrite-prompt-title">
      <div className="modal-content" style={{ maxWidth: '560px', width: 'calc(100% - 32px)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
          <h2 id="rewrite-prompt-title" className="text-gradient font-bold" style={{ margin: 0 }}>
            {title}
          </h2>
          <button type="button" className="icon-btn" onClick={onClose} disabled={actionLoading} aria-label="关闭">
            <X size={18} />
          </button>
        </div>

        <div className="form-group" style={{ marginTop: '16px' }}>
          <label className="form-label" htmlFor="rewrite-prompt-input">
            补充要求{required ? '' : '（可选）'}
          </label>
          <textarea
            id="rewrite-prompt-input"
            className="form-textarea"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            autoFocus
            rows={6}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && canSubmit) {
                event.preventDefault();
                onSubmit();
              }
            }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={actionLoading}>
            取消
          </button>
          <button type="button" className="btn btn-primary" onClick={onSubmit} disabled={!canSubmit}>
            {actionLoading ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
            {submitLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

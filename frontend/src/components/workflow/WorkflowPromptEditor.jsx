import { useState } from 'react';
import { Loader2, Plus, Save, Trash2 } from 'lucide-react';

/**
 * 提示词编辑。
 *
 * 数据库是运行时权威来源（`agents/prompt_templates.load_prompt_template` 直接查库），
 * 磁盘上的 JSON 只在缺失行时做种子。所以在这里改就是改生产行为。
 *
 * 新建能力是自定义节点的前提：节点靠 prompt_name 指向一条提示词，没有新建入口，
 * 节点指定的名字就无处创建。
 */

const NEW_PROMPT = {
  name: '',
  name_zh: '',
  type: 'writing',
  system_prompt: '',
  user_prompt_template: '',
};

export default function WorkflowPromptEditor({ category, prompts, onCreate, onUpdate, onDelete }) {
  const [selectedId, setSelectedId] = useState(null);
  const [typeFilter, setTypeFilter] = useState('all');
  const [draft, setDraft] = useState(null);
  const [creating, setCreating] = useState(null);
  const [busy, setBusy] = useState(false);

  const scoped = (prompts || []).filter((p) => p.category === category);
  const types = ['all', ...new Set(scoped.map((p) => p.type).filter(Boolean))];
  const visible = typeFilter === 'all' ? scoped : scoped.filter((p) => p.type === typeFilter);
  const selected = visible.find((p) => p.id === selectedId) || visible[0];

  const editing = draft && selected && draft.id === selected.id ? draft : selected;
  const dirty = Boolean(
    editing &&
    selected &&
    editing.id === selected.id &&
    (editing.system_prompt !== selected.system_prompt ||
      editing.user_prompt_template !== selected.user_prompt_template),
  );

  const patch = (field, value) => {
    if (!selected) return;
    const base = draft && draft.id === selected.id ? draft : selected;
    setDraft({ ...base, [field]: value });
  };

  const run = async (fn) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '12px', color: 'var(--ink-light)' }}>
          分类 <strong style={{ fontFamily: 'monospace' }}>{category}</strong>
          <span style={{ color: 'var(--ink-lighter)' }}> · 共 {scoped.length} 条 · 数据库为运行时权威</span>
        </span>
        <div style={{ display: 'flex', gap: '4px', marginLeft: 'auto' }}>
          {types.map((type) => (
            <button
              key={type}
              className={`btn ${typeFilter === type ? 'btn-primary' : ''}`}
              onClick={() => setTypeFilter(type)}
              style={{
                padding: '3px 11px',
                fontSize: '12px',
                ...(typeFilter !== type
                  ? { background: 'var(--bg-muted)', color: 'var(--ink-light)', border: 'none' }
                  : {}),
              }}
            >
              {type === 'all' ? '全部' : type}
            </button>
          ))}
          <button
            className="btn btn-primary"
            onClick={() => setCreating({ ...NEW_PROMPT })}
            style={{ padding: '3px 11px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '5px' }}
          >
            <Plus size={13} /> 新建
          </button>
        </div>
      </div>

      {creating && (
        <div
          style={{
            border: '1px solid var(--border-muted)',
            borderRadius: '10px',
            padding: '14px',
            background: 'var(--bg-muted)',
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 120px', gap: '12px' }}>
            <div className="form-group">
              <label className="form-label">name（代码引用它）</label>
              <input
                className="form-input"
                style={{ fontFamily: 'monospace' }}
                placeholder="polish_colloquial"
                value={creating.name}
                onChange={(e) => setCreating({ ...creating, name: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">中文名</label>
              <input
                className="form-input"
                value={creating.name_zh}
                onChange={(e) => setCreating({ ...creating, name_zh: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">类型</label>
              <select
                className="form-input"
                value={creating.type}
                onChange={(e) => setCreating({ ...creating, type: e.target.value })}
              >
                {['writing', 'planning', 'validation', 'extraction'].map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
            <button
              className="btn btn-primary"
              disabled={busy || !creating.name}
              onClick={() =>
                run(async () => {
                  await onCreate({ ...creating, category });
                  setCreating(null);
                })
              }
              style={{ padding: '5px 16px', fontSize: '13px' }}
            >
              {busy ? <Loader2 className="spin-slow" size={14} /> : '创建'}
            </button>
            <button className="btn" onClick={() => setCreating(null)} style={{ padding: '5px 16px', fontSize: '13px' }}>
              取消
            </button>
          </div>
        </div>
      )}

      {scoped.length === 0 ? (
        <div style={{ padding: '20px', textAlign: 'center', color: 'var(--ink-lighter)', fontSize: '13px' }}>
          该分类下还没有提示词。
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {visible.map((prompt) => (
              <button
                key={prompt.id}
                className={`btn ${selected?.id === prompt.id ? 'btn-primary' : ''}`}
                onClick={() => setSelectedId(prompt.id)}
                style={{
                  padding: '5px 11px',
                  fontSize: '12px',
                  ...(selected?.id === prompt.id
                    ? {}
                    : { background: 'var(--bg-muted)', color: 'var(--ink)', border: '1px solid var(--border-muted)' }),
                }}
              >
                {prompt.name_zh || prompt.name}
              </button>
            ))}
          </div>

          {selected && (
            <div style={{ border: '1px solid var(--border-muted)', borderRadius: '8px', overflow: 'hidden' }}>
              <div
                style={{
                  background: 'var(--bg-muted)',
                  padding: '8px 14px',
                  borderBottom: '1px solid var(--border-muted)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <span style={{ fontSize: '13px', fontWeight: 600 }}>
                  {selected.name_zh || selected.name}
                  <span
                    style={{ fontFamily: 'monospace', fontWeight: 400, fontSize: '11px', color: 'var(--ink-lighter)' }}
                  >
                    {' '}
                    {selected.name} · {selected.type || '未知'}
                  </span>
                </span>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button
                    className="btn btn-primary"
                    disabled={!dirty || busy}
                    onClick={() =>
                      run(() =>
                        onUpdate(editing.id, {
                          system_prompt: editing.system_prompt,
                          user_prompt_template: editing.user_prompt_template,
                        }),
                      )
                    }
                    style={{
                      padding: '4px 11px',
                      fontSize: '12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      opacity: dirty && !busy ? 1 : 0.5,
                    }}
                  >
                    {busy ? <Loader2 className="spin-slow" size={13} /> : <Save size={13} />} 保存
                  </button>
                  <button
                    className="btn"
                    disabled={busy}
                    onClick={() => run(() => onDelete(selected.id))}
                    style={{ padding: '4px 9px', background: 'transparent', border: '1px solid var(--border-muted)' }}
                    title="流水线必需的模板与被节点引用的模板会被拒绝删除"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
              <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div className="form-group">
                  <label className="form-label">System Prompt</label>
                  <textarea
                    className="form-input"
                    rows={Math.min(28, Math.max(4, (editing?.system_prompt || '').split('\n').length + 1))}
                    value={editing?.system_prompt || ''}
                    onChange={(e) => patch('system_prompt', e.target.value)}
                    style={{ fontFamily: 'monospace', fontSize: '12.5px', resize: 'vertical' }}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">User Prompt Template</label>
                  <textarea
                    className="form-input"
                    rows={Math.min(24, Math.max(4, (editing?.user_prompt_template || '').split('\n').length + 1))}
                    value={editing?.user_prompt_template || ''}
                    onChange={(e) => patch('user_prompt_template', e.target.value)}
                    style={{ fontFamily: 'monospace', fontSize: '12.5px', resize: 'vertical' }}
                  />
                </div>
                <div style={{ fontSize: '11px', color: 'var(--ink-lighter)' }}>
                  模板里的 {'{占位符}'} 是运行时注入的变量，改文字时请保留。
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

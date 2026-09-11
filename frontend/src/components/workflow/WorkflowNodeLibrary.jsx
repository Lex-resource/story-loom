import { useState } from 'react';
import { Loader2, Plus, Save, Trash2 } from 'lucide-react';

/**
 * 节点库。
 *
 * 一个节点 = 角色 + 提示词 + 名称。**执行器由角色推导**，所以这里只读展示 ——
 * 角色决定跑哪段 Python，存一份可写的执行器副本只会让两者不一致。
 *
 * 内置节点只能改中文名与说明：它们被所有工作流共用，改提示词会连带改掉冻结在
 * A28/V43 的长篇。要换提示词就新建一个自定义节点，在拓扑里替换掉那一步。
 */

const EMPTY_DRAFT = {
  id: '',
  name_zh: '',
  role: '',
  prompt_name: '',
  description: '',
  always_run: false,
};

export default function WorkflowNodeLibrary({ nodes, vocabulary, prompts, onCreate, onUpdate, onDelete }) {
  const [draft, setDraft] = useState(null);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  const roles = (vocabulary?.roles || []).filter((r) => !r.is_system);
  const roleLabel = (role) => (vocabulary?.roles || []).find((r) => r.role === role)?.label || role;

  const startNew = () => {
    setEditing(null);
    setDraft({ ...EMPTY_DRAFT, role: roles[0]?.role || '' });
  };

  const startEdit = (node) => {
    setDraft(null);
    setEditing({
      id: node.id,
      name_zh: node.name_zh,
      role: node.role,
      prompt_name: node.prompt_name || '',
      description: node.description || '',
      always_run: Boolean(node.options?.always_run),
      builtin: node.builtin,
    });
  };

  const submit = async (payload, isNew) => {
    setBusy(true);
    try {
      if (isNew) await onCreate(payload);
      else await onUpdate(payload.id, payload);
      setDraft(null);
      setEditing(null);
    } finally {
      setBusy(false);
    }
  };

  const form = draft || editing;
  const isNew = Boolean(draft);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: '12px', color: 'var(--ink-lighter)', lineHeight: 1.7, maxWidth: '640px' }}>
          节点可被任意工作流复用。自定义节点能换的是<strong>提示词</strong>与<strong>名称</strong> ——
          执行器由角色决定，那是写死的程序。 文风修复类节点可以勾「无条件执行」绕过检测门控。
        </div>
        <button
          className="btn btn-primary"
          onClick={startNew}
          style={{ padding: '5px 14px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Plus size={14} /> 新建节点
        </button>
      </div>

      {form && (
        <div
          style={{
            border: '1px solid var(--border-muted)',
            borderRadius: '10px',
            padding: '16px',
            background: 'var(--bg-muted)',
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
            <div className="form-group">
              <label className="form-label">节点 id</label>
              <input
                className="form-input"
                style={{ fontFamily: 'monospace' }}
                value={form.id}
                disabled={!isNew}
                placeholder="editor.style_repair.colloquial"
                onChange={(e) => (isNew ? setDraft({ ...form, id: e.target.value }) : null)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">中文名</label>
              <input
                className="form-input"
                value={form.name_zh}
                placeholder="口语化重写"
                onChange={(e) =>
                  isNew
                    ? setDraft({ ...form, name_zh: e.target.value })
                    : setEditing({ ...form, name_zh: e.target.value })
                }
              />
            </div>
            <div className="form-group">
              <label className="form-label">角色</label>
              <select
                className="form-input"
                value={form.role}
                disabled={form.builtin}
                onChange={(e) =>
                  isNew ? setDraft({ ...form, role: e.target.value }) : setEditing({ ...form, role: e.target.value })
                }
              >
                {roles.map((role) => (
                  <option key={role.role} value={role.role}>
                    {role.label} · {role.agent}
                  </option>
                ))}
              </select>
              <div style={{ fontSize: '11px', color: 'var(--ink-lighter)', marginTop: '4px' }}>
                内置提示词：{roles.find((r) => r.role === form.role)?.primary_prompt || '—'}
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">提示词（留空 = 用内置）</label>
              <select
                className="form-input"
                value={form.prompt_name}
                disabled={form.builtin}
                title={form.builtin ? '内置节点被所有工作流共用，改提示词会连带改掉长篇' : ''}
                onChange={(e) =>
                  isNew
                    ? setDraft({ ...form, prompt_name: e.target.value })
                    : setEditing({ ...form, prompt_name: e.target.value })
                }
              >
                <option value="">（内置提示词）</option>
                {Array.from(new Set((prompts || []).map((p) => p.name)))
                  .sort()
                  .map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
              </select>
            </div>
            <div className="form-group" style={{ gridColumn: '1 / -1' }}>
              <label className="form-label">说明</label>
              <input
                className="form-input"
                value={form.description}
                onChange={(e) =>
                  isNew
                    ? setDraft({ ...form, description: e.target.value })
                    : setEditing({ ...form, description: e.target.value })
                }
              />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={form.always_run}
                disabled={form.builtin}
                onChange={(e) =>
                  isNew
                    ? setDraft({ ...form, always_run: e.target.checked })
                    : setEditing({ ...form, always_run: e.target.checked })
                }
              />
              无条件执行（绕过文风检测门控）
            </label>
          </div>

          <div style={{ display: 'flex', gap: '8px', marginTop: '14px' }}>
            <button
              className="btn btn-primary"
              disabled={busy || !form.id || !form.name_zh || !form.role}
              onClick={() =>
                submit(
                  {
                    id: form.id,
                    name_zh: form.name_zh,
                    role: form.role,
                    prompt_name: form.prompt_name || null,
                    description: form.description || null,
                    options: form.always_run ? { always_run: true } : null,
                  },
                  isNew,
                )
              }
              style={{ padding: '5px 16px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              {busy ? <Loader2 className="spin-slow" size={14} /> : <Save size={14} />}
              {isNew ? '创建' : '保存'}
            </button>
            <button
              className="btn"
              onClick={() => {
                setDraft(null);
                setEditing(null);
              }}
              style={{ padding: '5px 16px', fontSize: '13px' }}
            >
              取消
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {(nodes || []).map((node) => (
          <div
            key={node.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '9px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border-muted)',
              background: node.is_system ? 'var(--bg-muted)' : 'transparent',
              fontSize: '13px',
            }}
          >
            <span style={{ minWidth: '150px', fontWeight: 600 }}>{node.name_zh}</span>
            <span style={{ minWidth: '210px', fontFamily: 'monospace', fontSize: '11px', color: 'var(--ink-lighter)' }}>
              {node.id}
            </span>
            <span style={{ minWidth: '130px', color: 'var(--ink-light)' }}>{roleLabel(node.role)}</span>
            <span style={{ minWidth: '80px', color: 'var(--ink-lighter)', fontSize: '11px' }}>
              {node.agent || '系统'}
            </span>
            <span style={{ flex: 1, fontFamily: 'monospace', fontSize: '11px', color: 'var(--ink-light)' }}>
              {node.effective_prompt || '—'}
              {node.prompt_name ? ' （自定义）' : ''}
              {node.options?.always_run ? ' · 无条件执行' : ''}
            </span>
            {node.builtin ? (
              <span
                style={{
                  fontSize: '11px',
                  color: 'var(--ink-lighter)',
                  padding: '2px 8px',
                  background: 'var(--bg-muted)',
                  borderRadius: '4px',
                }}
              >
                内置
              </span>
            ) : null}
            <button
              className="btn"
              onClick={() => startEdit(node)}
              style={{
                padding: '3px 10px',
                fontSize: '12px',
                background: 'transparent',
                border: '1px solid var(--border-muted)',
              }}
            >
              编辑
            </button>
            <button
              className="btn"
              disabled={node.builtin}
              title={node.builtin ? '内置节点不可删除' : '删除'}
              onClick={() => onDelete(node.id)}
              style={{
                padding: '3px 8px',
                background: 'transparent',
                border: '1px solid var(--border-muted)',
                opacity: node.builtin ? 0.3 : 1,
              }}
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

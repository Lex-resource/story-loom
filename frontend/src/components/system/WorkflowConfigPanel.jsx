import { Loader2, Save, Trash2 } from 'lucide-react';
import { Meta, Toggle } from './FormControls';
import WorkflowGraphEditor, { ResetGraphButton } from '../workflow/WorkflowGraphEditor';
import WorkflowNodeLibrary from '../workflow/WorkflowNodeLibrary';
import PromptConfigPanel from './PromptConfigPanel';

const TABS = [
  { key: 'graph', label: '拓扑' },
  { key: 'settings', label: '策略参数' },
  { key: 'prompts', label: '提示词' },
  { key: 'nodes', label: '节点库' },
];

const STRATEGY_LABELS = {
  frozen_v43: '长篇冻结表面 (A28/V43)',
  short_form: '短篇表面',
  custom: '自定义表面',
};

export default function WorkflowConfigPanel({
  draft,
  promptCategory,
  sharesPrompts,
  tab,
  setTab,
  setDraft,
  saving,
  onSave,
  onDelete,
  onResetGraph,
  vocabulary,
  nodes,
  prompts,
  errors,
  guard,
  reloadPrompts,
  reloadNodes,
  api,
}) {
  return (
    <>
      <div className="glass-panel" style={{ padding: '18px', borderRadius: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px' }}>
          <div style={{ flex: 1 }}>
            <input
              className="form-input"
              value={draft.name_zh || ''}
              onChange={(e) => setDraft({ ...draft, name_zh: e.target.value })}
              style={{ fontSize: '17px', fontWeight: 600, border: 'none', background: 'transparent', padding: 0 }}
            />
            <input
              className="form-input"
              value={draft.description || ''}
              placeholder="给这个工作流写一句说明…"
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              style={{
                fontSize: '12.5px',
                color: 'var(--ink-light)',
                border: 'none',
                background: 'transparent',
                padding: '4px 0 0',
                width: '100%',
              }}
            />
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="btn btn-primary"
              onClick={onSave}
              disabled={saving}
              style={{ padding: '5px 15px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              {saving ? <Loader2 size={14} className="spin-slow" /> : <Save size={14} />} {saving ? '保存中…' : '保存'}
            </button>
            <button
              className="btn"
              onClick={onDelete}
              disabled={draft.builtin}
              title={draft.builtin ? '内置工作流不可删除' : '删除工作流'}
              style={{
                padding: '5px 10px',
                background: 'transparent',
                border: '1px solid var(--border-muted)',
                opacity: draft.builtin ? 0.3 : 1,
              }}
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
        <div
          style={{
            display: 'flex',
            gap: '18px',
            flexWrap: 'wrap',
            marginTop: '14px',
            paddingTop: '12px',
            borderTop: '1px solid var(--border-muted)',
            fontSize: '12px',
          }}
        >
          <Meta
            label="表面策略"
            value={STRATEGY_LABELS[draft.surface_strategy] || draft.surface_strategy || '（未设置）'}
          />
          <Meta label="提示词分类" value={promptCategory} hint={sharesPrompts ? '共享自其他工作流' : '自有一套'} />
          <Meta label="拓扑" value={draft.graph_is_custom ? '已自定义' : '默认拓扑'} />
          <Meta
            label="质量维度"
            value={`${draft.quality_dims?.length || 0} 维`}
            hint={(draft.quality_dims || []).slice(5).join('、')}
          />
          <Meta label="重写上限" value={draft.policy?.max_rewrites_override ?? draft.max_rewrite} />
        </div>
        <div style={{ display: 'flex', gap: '4px', marginTop: '14px' }}>
          {TABS.map((item) => (
            <button
              key={item.key}
              className={`btn ${tab === item.key ? 'btn-primary' : ''}`}
              onClick={() => setTab(item.key)}
              style={{
                padding: '5px 14px',
                fontSize: '13px',
                ...(tab !== item.key
                  ? { background: 'var(--bg-muted)', color: 'var(--ink-light)', border: 'none' }
                  : {}),
              }}
            >
              {item.label}
            </button>
          ))}
          {tab === 'graph' && (
            <div style={{ marginLeft: 'auto' }}>
              <ResetGraphButton onReset={onResetGraph} />
            </div>
          )}
        </div>
      </div>

      <div className="glass-panel" style={{ padding: '18px', borderRadius: '12px' }}>
        {tab === 'graph' && (
          <WorkflowGraphEditor
            graph={draft.graph}
            vocabulary={vocabulary}
            nodes={nodes}
            errors={errors}
            onChange={(graph) => setDraft({ ...draft, graph })}
          />
        )}
        {tab === 'settings' && <WorkflowSettings draft={draft} setDraft={setDraft} />}
        {tab === 'prompts' && (
          <PromptConfigPanel
            category={promptCategory}
            prompts={prompts}
            api={api}
            guard={guard}
            reloadPrompts={reloadPrompts}
          />
        )}
        {tab === 'nodes' && (
          <WorkflowNodeLibrary
            nodes={nodes}
            vocabulary={vocabulary}
            prompts={prompts.filter((prompt) => prompt.category === promptCategory)}
            onCreate={async (payload) => {
              await guard(() => api.createNode(payload), '节点已创建');
              await reloadNodes();
            }}
            onUpdate={async (id, payload) => {
              await guard(() => api.updateNode(id, payload), '节点已保存');
              await reloadNodes();
            }}
            onDelete={async (id) => {
              await guard(() => api.deleteNode(id), '节点已删除');
              await reloadNodes();
            }}
          />
        )}
        {tab !== 'graph' && errors.length > 0 && (
          <div
            style={{
              marginTop: '14px',
              border: '1px solid var(--color-red)',
              background: 'rgba(220,38,38,0.06)',
              borderRadius: '8px',
              padding: '12px',
              fontSize: '13px',
              color: 'var(--color-red)',
              whiteSpace: 'pre-wrap',
            }}
          >
            {errors.join('\n')}
          </div>
        )}
      </div>
    </>
  );
}

function WorkflowSettings({ draft, setDraft }) {
  const policy = draft.policy || {};
  const patchPolicy = (key, value) => setDraft({ ...draft, policy: { ...policy, [key]: value } });
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ fontSize: '12px', color: 'var(--ink-lighter)', lineHeight: 1.7 }}>
        这些开关不影响拓扑，只被拓扑里的预算边和上下文装配读取。<strong>表面策略</strong>与<strong>质量维度</strong>
        不在这里改：前者决定提示词表面，后者由前者派生。
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px' }}>
        <div className="form-group">
          <label className="form-label">最大重写次数（rewrite 预算上限）</label>
          <input
            type="number"
            min="1"
            className="form-input"
            value={draft.max_rewrite}
            onChange={(e) => setDraft({ ...draft, max_rewrite: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label className="form-label">重写上限覆盖（policy）</label>
          <input
            type="number"
            min="1"
            className="form-input"
            placeholder="留空 = 不覆盖"
            value={policy.max_rewrites_override ?? ''}
            onChange={(e) =>
              patchPolicy('max_rewrites_override', e.target.value === '' ? null : parseInt(e.target.value, 10))
            }
          />
        </div>
        <div
          className="form-group"
          style={{ display: 'flex', flexDirection: 'column', gap: '10px', justifyContent: 'center' }}
        >
          <Toggle
            checked={draft.enable_editor_loop}
            onChange={(value) => setDraft({ ...draft, enable_editor_loop: value })}
            label="启用编辑打回重写循环"
            hint="关掉等于把重写回边直接禁用"
          />
          <Toggle
            checked={draft.enable_force_correction}
            onChange={(value) => setDraft({ ...draft, enable_force_correction: value })}
            label="重写用尽后强制修正"
            hint="关掉则暂停等人工"
          />
        </div>
        <div
          className="form-group"
          style={{ display: 'flex', flexDirection: 'column', gap: '10px', justifyContent: 'center' }}
        >
          <Toggle
            checked={Boolean(policy.bypass_short_term_memory_window)}
            onChange={(value) => patchPolicy('bypass_short_term_memory_window', value)}
            label="携带全文上下文"
            hint="不按窗口截取历史章节"
          />
          <Toggle
            checked={Boolean(policy.enable_light_polish)}
            onChange={(value) => patchPolicy('enable_light_polish', value)}
            label="轻度润色"
            hint="给没有编辑步骤的流程补一个编辑"
          />
        </div>
      </div>
      <div className="form-group">
        <label className="form-label">提示词分类（prompt_category）</label>
        <input
          className="form-input"
          style={{ fontFamily: 'monospace' }}
          value={draft.prompt_category || draft.name}
          onChange={(e) => setDraft({ ...draft, prompt_category: e.target.value })}
        />
        <div style={{ fontSize: '11px', color: 'var(--ink-lighter)', marginTop: '4px' }}>
          指向别的工作流即「共享它的提示词」。
        </div>
      </div>
    </div>
  );
}

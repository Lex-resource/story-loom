import { useMemo } from 'react';
import { ArrowDown, ArrowUp, RotateCcw, Trash2 } from 'lucide-react';

/**
 * 拓扑编辑器。
 *
 * 编辑的是 pipeline_configs.graph：步骤 + 裁决边 + 预算。词表（角色、裁决、特殊目标）
 * 全部来自后端 /system-configs/graph-vocabulary —— 前端不重写一份规则，后端加一个角色
 * 这里自动跟上。
 *
 * 校验也只在后端做（环守卫、悬空目标、必需角色与裁决、节点引用一致性），保存失败时
 * 把后端返回的错误原样显示。前端再实现一遍规则只会两边不一致。
 */

const SPECIAL_LABELS = {
  '@done': '结束（正常完成）',
  '@retry_chapter': '整章重跑（消耗 attempt 预算）',
  '@pause:planner': '暂停 · 恢复时回到策划',
  '@pause:writer': '暂停 · 恢复时回到初稿',
  '@pause:editor': '暂停 · 恢复时回到编辑',
  '@pause:validator': '暂停 · 恢复时回到校验',
  '@pause:extractor': '暂停 · 恢复时回到提取',
};

const VERDICT_LABELS = {
  ok: '通过',
  rewrite: '要求重写',
  fail: '未通过',
  blocked: '需人工介入',
  empty: '产出为空',
  skipped: '未触发/跳过',
};

const edgeOf = (raw) => {
  if (typeof raw === 'string') return { goto: raw };
  if (raw && typeof raw === 'object') return { ...raw };
  return { goto: '@done' };
};

export default function WorkflowGraphEditor({ graph, vocabulary, nodes, onChange, errors }) {
  const steps = graph?.steps || [];
  const budgets = graph?.budgets || {};

  const roleMap = useMemo(() => {
    const map = new Map();
    (vocabulary?.roles || []).forEach((role) => map.set(role.role, role));
    return map;
  }, [vocabulary]);

  const nodesByRole = useMemo(() => {
    const map = new Map();
    (nodes || []).forEach((node) => {
      if (!map.has(node.role)) map.set(node.role, []);
      map.get(node.role).push(node);
    });
    return map;
  }, [nodes]);

  const targets = useMemo(() => {
    const stepTargets = steps.map((s) => ({ value: s.id, label: `步骤 · ${s.id}` }));
    const specials = (vocabulary?.special_targets || []).map((value) => ({
      value,
      label: SPECIAL_LABELS[value] || value,
    }));
    return [...stepTargets, ...specials];
  }, [steps, vocabulary]);

  const writeSteps = (nextSteps) => onChange({ ...graph, steps: nextSteps });

  const patchStep = (index, patch) => {
    const next = steps.map((step, i) => (i === index ? { ...step, ...patch } : step));
    writeSteps(next);
  };

  const patchEdge = (index, verdict, patch) => {
    const step = steps[index];
    if (verdict === 'ok') {
      patchStep(index, { next: { ...edgeOf(step.next), ...patch } });
      return;
    }
    const on = { ...(step.on || {}) };
    on[verdict] = { ...edgeOf(on[verdict]), ...patch };
    patchStep(index, { on });
  };

  const removeEdge = (index, verdict) => {
    const on = { ...(steps[index].on || {}) };
    delete on[verdict];
    patchStep(index, { on });
  };

  const moveStep = (index, delta) => {
    const target = index + delta;
    if (target < 0 || target >= steps.length) return;
    const next = [...steps];
    [next[index], next[target]] = [next[target], next[index]];
    writeSteps(next);
  };

  const removeStep = (index) => writeSteps(steps.filter((_, i) => i !== index));

  const addStep = (role) => {
    if (!role) return;
    // id 唯一即可；用 role 加序号，用户看得懂又不会撞。
    const used = new Set(steps.map((s) => s.id));
    let candidate = role;
    let n = 2;
    while (used.has(candidate)) candidate = `${role}_${n++}`;
    const nextTarget = steps.length ? steps[steps.length - 1].id : '@done';
    writeSteps([...steps, { id: candidate, role, next: { goto: nextTarget } }]);
  };

  const availableRoles = (vocabulary?.roles || []).filter((r) => !r.is_system);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ fontSize: '12px', color: 'var(--ink-lighter)', lineHeight: 1.7 }}>
        每个步骤跑一个<strong>角色</strong>（决定执行哪段程序）与一个<strong>节点</strong>
        （决定用哪份提示词）。步骤产出一个<strong>裁决</strong>，裁决决定走哪条边。 回边（指向前面的步骤）
        <strong>必须带预算</strong>，否则会无限循环 —— 保存时后端会拒。
        <br />
        新增一种程序行为需要写 Python：五个执行器各有自己的输出结构，主循环按固定语义
        消费它们的裁决。前端能自由组合的是「角色 × 节点 × 顺序 × 边」。
      </div>

      {errors?.length > 0 && (
        <div
          style={{
            border: '1px solid var(--color-red)',
            background: 'rgba(220,38,38,0.06)',
            borderRadius: '8px',
            padding: '12px 14px',
            fontSize: '13px',
            color: 'var(--color-red)',
            whiteSpace: 'pre-wrap',
          }}
        >
          {errors.join('\n')}
        </div>
      )}

      {steps.map((step, index) => {
        const roleInfo = roleMap.get(step.role);
        const roleNodes = nodesByRole.get(step.role) || [];
        const mustHandle = roleInfo?.must_handle || [];
        const presentVerdicts = Object.keys(step.on || {});
        const shownVerdicts = Array.from(new Set([...mustHandle, ...presentVerdicts]));
        const addableVerdicts = (vocabulary?.verdicts || []).filter((v) => v !== 'ok' && !shownVerdicts.includes(v));
        const nextEdge = edgeOf(step.next);

        return (
          <div
            key={`${step.id}-${index}`}
            style={{
              border: '1px solid var(--border-muted)',
              borderRadius: '10px',
              padding: '14px',
              background: roleInfo?.is_system ? 'var(--bg-muted)' : 'transparent',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <span
                style={{
                  minWidth: '24px',
                  height: '24px',
                  borderRadius: '12px',
                  background: 'var(--bg-muted)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '12px',
                  color: 'var(--ink-light)',
                }}
              >
                {index + 1}
              </span>

              <input
                className="form-input"
                style={{ width: '140px', fontFamily: 'monospace', fontSize: '12px' }}
                value={step.id}
                onChange={(e) => patchStep(index, { id: e.target.value.trim() })}
                title="步骤 id，边通过它互相引用"
              />

              <select
                className="form-input"
                style={{ width: '170px', fontSize: '13px' }}
                value={step.role}
                onChange={(e) => patchStep(index, { role: e.target.value, node: undefined })}
              >
                {(vocabulary?.roles || []).map((role) => (
                  <option key={role.role} value={role.role}>
                    {role.label}
                    {role.required ? '（必需）' : ''}
                  </option>
                ))}
              </select>

              <select
                className="form-input"
                style={{ width: '210px', fontSize: '13px' }}
                value={step.node || ''}
                onChange={(e) => patchStep(index, { node: e.target.value || undefined })}
                disabled={roleInfo?.is_system}
                title={roleInfo?.is_system ? '系统步骤没有提示词，无可选节点' : '选一个节点决定用哪份提示词'}
              >
                <option value="">（该角色的内置节点）</option>
                {roleNodes
                  .filter((node) => !node.builtin)
                  .map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.name_zh} · {node.effective_prompt || '无提示词'}
                    </option>
                  ))}
              </select>

              <div style={{ marginLeft: 'auto', display: 'flex', gap: '4px' }}>
                <IconBtn disabled={index === 0} onClick={() => moveStep(index, -1)}>
                  <ArrowUp size={13} />
                </IconBtn>
                <IconBtn disabled={index === steps.length - 1} onClick={() => moveStep(index, 1)}>
                  <ArrowDown size={13} />
                </IconBtn>
                <IconBtn
                  onClick={() => removeStep(index)}
                  title={roleInfo?.required ? '这是必需角色，删掉保存会被拒' : '删除步骤'}
                >
                  <Trash2 size={13} />
                </IconBtn>
              </div>
            </div>

            {roleInfo?.description && (
              <div style={{ fontSize: '11px', color: 'var(--ink-lighter)', margin: '8px 0 0 34px' }}>
                {roleInfo.description}
                {roleInfo.agent ? ` · 执行者：${roleInfo.agent}` : ' · 系统步骤'}
                {roleInfo.primary_prompt ? ` · 内置提示词：${roleInfo.primary_prompt}` : ''}
              </div>
            )}

            <div
              style={{ marginTop: '10px', marginLeft: '34px', display: 'flex', flexDirection: 'column', gap: '6px' }}
            >
              <EdgeRow
                verdict="ok"
                edge={nextEdge}
                targets={targets}
                budgets={budgets}
                onPatch={(patch) => patchEdge(index, 'ok', patch)}
              />
              {shownVerdicts.map((verdict) => (
                <EdgeRow
                  key={verdict}
                  verdict={verdict}
                  edge={edgeOf((step.on || {})[verdict])}
                  targets={targets}
                  budgets={budgets}
                  required={mustHandle.includes(verdict)}
                  onPatch={(patch) => patchEdge(index, verdict, patch)}
                  onRemove={mustHandle.includes(verdict) ? undefined : () => removeEdge(index, verdict)}
                />
              ))}
              {addableVerdicts.length > 0 && (
                <select
                  className="form-input"
                  style={{ width: '190px', fontSize: '12px' }}
                  value=""
                  onChange={(e) => patchEdge(index, e.target.value, { goto: nextEdge.goto })}
                >
                  <option value="">+ 添加裁决分支…</option>
                  {addableVerdicts.map((v) => (
                    <option key={v} value={v}>
                      {VERDICT_LABELS[v] || v}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>
        );
      })}

      <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
        <select
          className="form-input"
          style={{ width: '210px', fontSize: '13px' }}
          value=""
          onChange={(e) => addStep(e.target.value)}
        >
          <option value="">+ 添加步骤…</option>
          {availableRoles.map((role) => (
            <option key={role.role} value={role.role}>
              {role.label}
            </option>
          ))}
        </select>
        <span style={{ fontSize: '11px', color: 'var(--ink-lighter)' }}>
          同一个角色可以出现多次 —— 例如串两个文风修复节点，各用不同提示词。
        </span>
      </div>
    </div>
  );
}

function IconBtn({ children, onClick, disabled, title }) {
  return (
    <button
      className="btn"
      title={title}
      disabled={disabled}
      onClick={onClick}
      style={{
        padding: '3px 8px',
        background: 'transparent',
        border: '1px solid var(--border-muted)',
        opacity: disabled ? 0.35 : 1,
      }}
    >
      {children}
    </button>
  );
}

function EdgeRow({ verdict, edge, targets, budgets, onPatch, onRemove, required }) {
  const budgetNames = Object.keys(budgets || {});
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', fontSize: '12px' }}>
      <span
        style={{
          minWidth: '86px',
          color: verdict === 'ok' ? 'var(--ink)' : 'var(--ink-light)',
          fontWeight: verdict === 'ok' ? 600 : 400,
        }}
      >
        {VERDICT_LABELS[verdict] || verdict}
        {required ? ' *' : ''}
      </span>
      <span style={{ color: 'var(--ink-lighter)' }}>→</span>
      <select
        className="form-input"
        style={{ width: '210px', fontSize: '12px' }}
        value={edge.goto || ''}
        onChange={(e) => onPatch({ goto: e.target.value })}
      >
        {targets.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>

      <select
        className="form-input"
        style={{ width: '120px', fontSize: '12px' }}
        value={edge.budget || ''}
        onChange={(e) => onPatch({ budget: e.target.value || undefined })}
        title="回边必须带预算，否则无限循环"
      >
        <option value="">不限次数</option>
        {budgetNames.map((name) => (
          <option key={name} value={name}>
            预算 {name}
          </option>
        ))}
      </select>

      {edge.budget && (
        <>
          <span style={{ color: 'var(--ink-lighter)' }}>用尽 →</span>
          <select
            className="form-input"
            style={{ width: '190px', fontSize: '12px' }}
            value={edge.on_exhausted || ''}
            onChange={(e) => onPatch({ on_exhausted: e.target.value || undefined })}
          >
            <option value="">（必填）</option>
            {targets.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </>
      )}

      {onRemove && (
        <button
          className="btn"
          onClick={onRemove}
          style={{ padding: '2px 6px', background: 'transparent', border: '1px solid var(--border-muted)' }}
        >
          <Trash2 size={11} />
        </button>
      )}
    </div>
  );
}

export function ResetGraphButton({ onReset, disabled }) {
  return (
    <button
      className="btn"
      onClick={onReset}
      disabled={disabled}
      style={{ padding: '4px 12px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
    >
      <RotateCcw size={13} /> 重置为默认拓扑
    </button>
  );
}

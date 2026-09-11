import { Toggle } from './FormControls';
import { useEffect, useRef, useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import { systemConfigApi } from '../../services/novelApi';
import { asErrorList } from '../../utils/errorFormat';
import { createRequestGuard } from '../../utils/requestLifecycle';

/**
 * 运行参数(runtime_tunables)视图。
 *
 * 元数据(类型/范围/默认/说明/生效时机)全部由后端 vocabulary 下发,前端不写死
 * 任何参数 —— 后端加一项,界面自动跟上。数字渲染成带 min/max 的输入框,
 * bool 渲染成开关,与 WorkflowSettings 的控件风格一致。
 */
export default function RuntimeTunablesView({ showToast }) {
  const [loading, setLoading] = useState(true);
  const [groups, setGroups] = useState([]);
  const [saved, setSaved] = useState({});
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState([]);
  const draftRef = useRef(draft);
  const loadGuardRef = useRef(null);
  const saveGuardRef = useRef(null);
  if (!loadGuardRef.current) loadGuardRef.current = createRequestGuard();
  if (!saveGuardRef.current) saveGuardRef.current = createRequestGuard();
  draftRef.current = draft;

  const reload = async () => {
    const request = loadGuardRef.current.start();
    setLoading(true);
    try {
      const [vocab, current] = await Promise.all([
        systemConfigApi.loadTunablesVocabulary({ signal: request.signal }),
        systemConfigApi.loadTunables({ signal: request.signal }),
      ]);
      if (!request.isCurrent()) return;
      setGroups(vocab);
      setSaved(current.values || {});
      setDraft(structuredClone(current.values || {}));
      setErrors([]);
    } catch (e) {
      if (!request.isCurrent() || e.name === 'AbortError') return;
      showToast(`加载失败: ${e.message}`, 'error');
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  };

  useEffect(() => {
    reload();
    return () => {
      loadGuardRef.current.cancel();
      saveGuardRef.current.cancel();
    };
  }, []);

  const dirtyKeys = Object.keys(draft).filter((key) => draft[key] !== saved[key]);

  const handleSave = async () => {
    if (dirtyKeys.length === 0) return;
    const draftAtStart = { ...draft };
    const dirtyKeysAtStart = [...dirtyKeys];
    const request = saveGuardRef.current.start();
    setSaving(true);
    try {
      const changed = Object.fromEntries(dirtyKeysAtStart.map((key) => [key, draftAtStart[key]]));
      const result = await systemConfigApi.updateTunables(changed, { signal: request.signal });
      if (!request.isCurrent()) return;
      const values = result.values || { ...draftAtStart };
      const latestDraft = draftRef.current;
      const nextDraft = { ...values };
      for (const [key, value] of Object.entries(latestDraft)) {
        if (value !== draftAtStart[key]) nextDraft[key] = value;
      }
      setSaved({ ...values });
      setDraft(nextDraft);
      setErrors([]);
      showToast('运行参数已保存,按各项「生效时机」指示生效', 'success');
    } catch (e) {
      if (!request.isCurrent() || e.name === 'AbortError') return;
      setErrors(asErrorList(e.message));
      showToast('保存被拒绝，详见错误列表', 'error');
    } finally {
      if (request.isCurrent()) setSaving(false);
    }
  };

  if (loading) {
    return (
      <div
        className="glass-panel"
        style={{
          padding: '24px',
          borderRadius: '12px',
          display: 'flex',
          justifyContent: 'center',
          color: 'var(--ink-light)',
        }}
      >
        <Loader2 className="spin-slow" size={22} />
        <span style={{ marginLeft: '10px' }}>正在加载运行参数...</span>
      </div>
    );
  }

  return (
    <>
      <div className="glass-panel" style={{ padding: '18px', borderRadius: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '15px' }}>运行参数</h3>
            <div style={{ fontSize: '12px', color: 'var(--ink-lighter)', marginTop: '2px' }}>
              存数据库、改动即生效的运维参数。提示词缓存、chroma 超时、轮询间隔都在这里调。
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="btn"
              onClick={reload}
              disabled={saving}
              style={{ padding: '5px 14px', fontSize: '13px' }}
            >
              重置
            </button>
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={saving || dirtyKeys.length === 0}
              style={{
                padding: '5px 15px',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                opacity: dirtyKeys.length === 0 ? 0.5 : 1,
              }}
            >
              {saving ? <Loader2 size={14} className="spin-slow" /> : <Save size={14} />}
              {saving ? '保存中…' : `保存${dirtyKeys.length ? `（${dirtyKeys.length} 项修改）` : ''}`}
            </button>
          </div>
        </div>
      </div>

      {errors.length > 0 && (
        <div
          style={{
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

      {groups.map((group) => (
        <div key={group.group} className="glass-panel" style={{ padding: '18px', borderRadius: '12px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
            {group.items.map((item) => (
              <div key={item.key} className="form-group" style={{ margin: 0 }}>
                {item.type === 'bool' ? (
                  <Toggle
                    checked={Boolean(draft[item.key])}
                    onChange={(v) => setDraft((current) => ({ ...current, [item.key]: v }))}
                    label={item.description || item.key}
                    hint={item.effective ? `生效：${item.effective}` : ''}
                  />
                ) : (
                  <>
                    <label className="form-label" style={{ fontFamily: 'monospace', fontSize: '11.5px' }}>
                      {item.key}
                      <span style={{ color: 'var(--ink-lighter)', fontFamily: 'inherit', marginLeft: '6px' }}>
                        {item.type === 'float' ? '小数' : '整数'}
                        {item.min != null ? `，≥ ${item.min}` : ''}
                        {item.max != null ? `，≤ ${item.max}` : ''}
                      </span>
                    </label>
                    <input
                      type="number"
                      className="form-input"
                      min={item.min ?? undefined}
                      max={item.max ?? undefined}
                      step={item.type === 'float' ? '0.1' : '1'}
                      value={draft[item.key] ?? ''}
                      onChange={(e) =>
                        setDraft((current) => ({
                          ...current,
                          [item.key]: e.target.value === '' ? '' : Number(e.target.value),
                        }))
                      }
                    />
                    <div style={{ fontSize: '11px', color: 'var(--ink-lighter)', marginTop: '4px' }}>
                      {item.description}（默认 {item.default}；生效：{item.effective}）
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Copy, Loader2, Plus, Save } from 'lucide-react';
import { systemConfigApi } from '../services/novelApi';
import { asErrorList } from '../utils/errorFormat';
import { createRequestGuard } from '../utils/requestLifecycle';
import RuntimeTunablesPanel from '../components/system/RuntimeTunablesPanel';
import WorkerRuntimeView from '../components/system/WorkerRuntimeView';
import WorkflowConfigPanel from '../components/system/WorkflowConfigPanel';

export default function SystemConfigs() {
  const [loading, setLoading] = useState(true);
  const [configs, setConfigs] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [vocabulary, setVocabulary] = useState(null);
  const [selectedName, setSelectedName] = useState('');
  const [draft, setDraft] = useState(null);
  const [tab, setTab] = useState('graph');
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState([]);
  const [toast, setToast] = useState(null);
  const [creating, setCreating] = useState(null);
  const [view, setView] = useState('workflow');
  const reloadGuardRef = useRef(null);
  if (!reloadGuardRef.current) reloadGuardRef.current = createRequestGuard();

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4500);
  };

  const reload = async (initial = false) => {
    if (initial) setLoading(true);
    const request = reloadGuardRef.current.start();
    try {
      const [confData, promptData, nodeData, vocab] = await systemConfigApi.load({ signal: request.signal });
      if (!request.isCurrent()) return;
      setConfigs(confData);
      setPrompts(promptData);
      setNodes(nodeData);
      setVocabulary(vocab);
      if (initial && confData.length) {
        setSelectedName(confData[0].name);
        setDraft(structuredClone(confData[0]));
      }
    } catch (error) {
      if (!request.isCurrent() || error.name === 'AbortError') return;
      showToast(`加载失败: ${error.message}`, 'error');
    } finally {
      if (initial && request.isCurrent()) setLoading(false);
    }
  };

  useEffect(() => {
    reload(true);
    return () => reloadGuardRef.current.cancel();
  }, []);

  useEffect(() => {
    if (!selectedName) return;
    const selected = configs.find((config) => config.name === selectedName);
    if (selected) {
      setDraft(structuredClone(selected));
      setErrors([]);
    }
  }, [selectedName, configs]);

  const guard = async (operation, successMessage) => {
    try {
      const result = await operation();
      setErrors([]);
      if (successMessage) showToast(successMessage, 'success');
      return result;
    } catch (error) {
      setErrors(asErrorList(error.message));
      showToast('操作被拒绝，详见上方错误', 'error');
      return null;
    }
  };

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const result = await guard(
        () =>
          systemConfigApi.updatePipeline(draft.name, {
            name_zh: draft.name_zh,
            description: draft.description,
            enable_editor_loop: draft.enable_editor_loop,
            max_rewrite: parseInt(draft.max_rewrite, 10) || 1,
            enable_force_correction: draft.enable_force_correction,
            policy: draft.policy,
            prompt_category: draft.prompt_category,
            graph: draft.graph,
          }),
        '工作流已保存。提示词改动对 Worker 立即热生效（无需重启）。',
      );
      if (result) await reload();
    } finally {
      setSaving(false);
    }
  };

  const handleCreate = async () => {
    if (!creating?.name) return;
    const result = await guard(() => systemConfigApi.createPipeline(creating), '工作流已创建');
    if (!result) return;
    setCreating(null);
    await reload();
    setSelectedName(result.name);
    showToast(
      result.prompts_copied
        ? `已创建，并复制了 ${result.prompts_copied} 条提示词`
        : `已创建，提示词复用分类 ${result.prompt_category}`,
      'success',
    );
  };

  const handleDelete = async () => {
    if (!draft) return;
    const result = await guard(() => systemConfigApi.deletePipeline(draft.name), '工作流已删除');
    if (!result) return;
    const remaining = configs.filter((config) => config.name !== draft.name);
    setSelectedName(remaining[0]?.name || '');
    await reload();
  };

  const resetGraph = async () => {
    const graph = await guard(() =>
      systemConfigApi.defaultGraph({
        has_editor: true,
        has_style_repair: true,
        validation_before_editor: draft?.validation_before_editor,
      }),
    );
    if (graph) setDraft({ ...draft, graph });
  };

  if (loading)
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100%',
          color: 'var(--ink-light)',
        }}
      >
        <Loader2 className="spin-slow" size={32} />
        <span style={{ marginLeft: '12px' }}>正在加载工作流配置...</span>
      </div>
    );

  const promptCategory = draft?.prompt_category || draft?.name;
  const sharesPrompts = promptCategory && promptCategory !== draft?.name;
  const refreshPrompts = async () => setPrompts(await systemConfigApi.listPrompts());
  const refreshNodes = async () => setNodes(await systemConfigApi.listNodes());

  return (
    <div style={{ maxWidth: '1500px', margin: '0 auto', padding: '0 20px 40px', display: 'flex', gap: '20px' }}>
      <aside
        className="glass-panel"
        style={{
          width: '250px',
          flexShrink: 0,
          padding: '16px',
          borderRadius: '12px',
          alignSelf: 'flex-start',
          position: 'sticky',
          top: '16px',
        }}
      >
        <div style={{ display: 'flex', gap: '4px', marginBottom: '12px' }}>
          {[
            ['workflow', '工作流配置'],
            ['tunables', '运行参数'],
            ['runtime', '运行时'],
          ].map(([key, label]) => (
            <button
              key={key}
              className={`btn ${view === key ? 'btn-primary' : ''}`}
              onClick={() => setView(key)}
              style={{
                flex: 1,
                padding: '5px 8px',
                fontSize: '13px',
                ...(view !== key ? { background: 'var(--bg-muted)', color: 'var(--ink-light)', border: 'none' } : {}),
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {view === 'workflow' && (
          <>
            <div
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}
            >
              <h3 style={{ margin: 0, fontSize: '15px' }}>工作流</h3>
              <button
                className="btn btn-primary"
                onClick={() =>
                  setCreating({ name: '', name_zh: '', clone_from: draft?.name || '', prompt_mode: 'copy' })
                }
                style={{ padding: '3px 9px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}
              >
                <Plus size={13} /> 新建
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {configs.map((config) => (
                <button
                  key={config.name}
                  onClick={() => setSelectedName(config.name)}
                  className="btn"
                  style={{
                    textAlign: 'left',
                    padding: '8px 10px',
                    fontSize: '13px',
                    background: config.name === selectedName ? 'var(--bg-muted)' : 'transparent',
                    border: config.name === selectedName ? '1px solid var(--border-muted)' : '1px solid transparent',
                    display: 'block',
                    width: '100%',
                  }}
                >
                  <div style={{ fontWeight: config.name === selectedName ? 600 : 400 }}>
                    {config.name_zh || config.name}
                    {config.builtin && (
                      <span style={{ fontSize: '10px', color: 'var(--ink-lighter)', marginLeft: '6px' }}>内置</span>
                    )}
                  </div>
                  <div style={{ fontSize: '10.5px', color: 'var(--ink-lighter)', fontFamily: 'monospace' }}>
                    {config.name}
                  </div>
                </button>
              ))}
            </div>
          </>
        )}
      </aside>

      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {view === 'tunables' && <RuntimeTunablesPanel showToast={showToast} />}
        {view === 'runtime' && <WorkerRuntimeView showToast={showToast} />}
        {view === 'workflow' && (
          <>
            {creating && (
              <div className="glass-panel" style={{ padding: '18px', borderRadius: '12px' }}>
                <h3 style={{ marginTop: 0, fontSize: '15px' }}>新建工作流</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                  <label className="form-group">
                    <span className="form-label">名称（同时是 novel_format）</span>
                    <input
                      className="form-input"
                      value={creating.name}
                      onChange={(e) => setCreating({ ...creating, name: e.target.value })}
                    />
                  </label>
                  <label className="form-group">
                    <span className="form-label">中文名</span>
                    <input
                      className="form-input"
                      value={creating.name_zh}
                      onChange={(e) => setCreating({ ...creating, name_zh: e.target.value })}
                    />
                  </label>
                  <label className="form-group">
                    <span className="form-label">克隆自</span>
                    <select
                      className="form-input"
                      value={creating.clone_from || ''}
                      onChange={(e) => setCreating({ ...creating, clone_from: e.target.value })}
                    >
                      <option value="">（从零新建）</option>
                      {configs.map((config) => (
                        <option key={config.name} value={config.name}>
                          {config.name_zh || config.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div style={{ display: 'flex', gap: '18px', marginTop: '12px', fontSize: '13px', flexWrap: 'wrap' }}>
                  {creating.clone_from ? (
                    <>
                      <label>
                        <input
                          type="radio"
                          checked={creating.prompt_mode !== 'share'}
                          onChange={() => setCreating({ ...creating, prompt_mode: 'copy' })}
                        />{' '}
                        复制一套独立提示词
                      </label>
                      <label>
                        <input
                          type="radio"
                          checked={creating.prompt_mode === 'share'}
                          onChange={() => setCreating({ ...creating, prompt_mode: 'share' })}
                        />{' '}
                        共享来源的提示词
                      </label>
                    </>
                  ) : (
                    <label className="form-group">
                      <span className="form-label">复用哪套提示词</span>
                      <select
                        className="form-input"
                        value={creating.prompt_category || 'long_webnovel'}
                        onChange={(e) => setCreating({ ...creating, prompt_category: e.target.value })}
                      >
                        {Array.from(new Set(prompts.map((prompt) => prompt.category)))
                          .sort()
                          .map((category) => (
                            <option key={category} value={category}>
                              {category}
                            </option>
                          ))}
                      </select>
                    </label>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                  <button className="btn btn-primary" onClick={handleCreate} disabled={!creating.name}>
                    <Copy size={13} /> 创建
                  </button>
                  <button className="btn" onClick={() => setCreating(null)}>
                    取消
                  </button>
                </div>
              </div>
            )}
            {draft && (
              <WorkflowConfigPanel
                draft={draft}
                promptCategory={promptCategory}
                sharesPrompts={sharesPrompts}
                tab={tab}
                setTab={setTab}
                setDraft={setDraft}
                saving={saving}
                onSave={handleSave}
                onDelete={handleDelete}
                onResetGraph={resetGraph}
                vocabulary={vocabulary}
                nodes={nodes}
                prompts={prompts}
                errors={errors}
                guard={guard}
                reloadPrompts={refreshPrompts}
                reloadNodes={refreshNodes}
                api={systemConfigApi}
              />
            )}
          </>
        )}
      </main>
      {toast && (
        <div
          style={{
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            padding: '12px 22px',
            background: toast.type === 'error' ? 'var(--color-red)' : 'var(--color-emerald)',
            color: 'white',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '14px',
            maxWidth: '520px',
          }}
        >
          {toast.type === 'error' ? <AlertCircle size={18} /> : <Save size={18} />}
          {toast.message}
        </div>
      )}
    </div>
  );
}

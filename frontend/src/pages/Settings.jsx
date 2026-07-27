import { useState, useEffect, useRef, useCallback } from 'react';
import { Loader2, RefreshCw, Plus, Trash2, Save, ChevronDown } from 'lucide-react';
import { DEFAULT_TARGET_CHAPTERS, DEFAULT_WORD_COUNT_PER_CHAPTER } from '../utils/constants';
import { settingsApi } from '../services/novelApi';

const PROVIDER_PRESETS = [
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com', model: 'deepseek-v4-flash', models: ['deepseek-v4-flash', 'deepseek-chat', 'deepseek-reasoner'] },
  { name: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'] },
  { name: 'Moonshot (Kimi)', base_url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k', models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'] },
  { name: '智谱 GLM', base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash', models: ['glm-4-flash', 'glm-4-plus', 'glm-4-air'] },
  { name: '通义千问', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', models: ['qwen-plus', 'qwen-turbo', 'qwen-max'] },
  { name: '自定义', base_url: '', model: 'deepseek-v4-flash', models: ['deepseek-v4-flash', 'deepseek-chat'] },
];

function buildModelOptions(prov) {
  if (!prov?.cached_models?.length) return [];
  return prov.cached_models;
}

function modelDetailFor(prov, modelId) {
  return prov?.cached_model_details?.[modelId] || null;
}

function formatModelDetailValue(value) {
  if (value === null || value === undefined || value === '') return '未提供';
  if (Array.isArray(value)) return value.length ? value.join('、') : '未提供';
  if (typeof value === 'object') return Object.entries(value).map(([k, v]) => `${k}: ${v}`).join('；') || '未提供';
  return String(value);
}

const WatchdogP95Estimator = ({ onApplySuggested }) => {
  const [loading, setLoading] = useState(false);
  const [p95Stats, setP95Stats] = useState(null);

  const fetchP95 = async () => {
    setLoading(true);
    try {
      setP95Stats(await settingsApi.watchdogP95());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ marginTop: '10px', background: 'rgba(0,0,0,0.15)', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-muted)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '13px', fontWeight: 600 }}>智能体历史耗时分析 (95分位数)</span>
        <button className="btn btn-secondary" onClick={fetchP95} disabled={loading} style={{ padding: '2px 8px', fontSize: '11px' }}>
          {loading ? '加载中...' : '加载分析数据'}
        </button>
      </div>
      {p95Stats ? (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', fontSize: '11px', color: 'var(--ink-light)' }}>
            <div>大纲策划: <span style={{ color: 'var(--gold)' }}>{p95Stats.planner}s</span></div>
            <div>执笔初稿: <span style={{ color: 'var(--gold)' }}>{p95Stats.writer}s</span></div>
            <div>编辑精修: <span style={{ color: 'var(--gold)' }}>{p95Stats.editor}s</span></div>
            <div>设定提取: <span style={{ color: 'var(--gold)' }}>{p95Stats.extractor}s</span></div>
            <div>天道法则: <span style={{ color: 'var(--gold)' }}>{p95Stats.validator}s</span></div>
          </div>
          {(() => {
            const suggested = Math.ceil(Math.max(...Object.values(p95Stats)) * 1.2 / 5) * 5;
            return (
              <div style={{ marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-muted)', paddingTop: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--ink-light)' }}>
                  建议心跳超时阈值: <strong style={{ color: 'var(--vermilion)' }}>{suggested} 秒</strong>
                </span>
                <button className="btn btn-primary" onClick={() => onApplySuggested(suggested)} style={{ padding: '2px 8px', fontSize: '11px' }}>
                  应用此建议值
                </button>
              </div>
            );
          })()}
        </div>
      ) : (
        <p style={{ margin: 0, fontSize: '11px', color: 'var(--ink-lighter)' }}>加载各环节智能体的历史 P95 耗时，帮助您科学设定防卡死看门狗阈值。</p>
      )}
    </div>
  );
};

export default function Settings({
  settingsData,
  saveSettings,
  backendUrl,
  saveBackendUrl,
  activeProject,
  activeProjectStatus,
  onUpdateProjectConfig
}) {
  const [localBackendUrl, setLocalBackendUrl] = useState(backendUrl || '');
  const [localSettings, setLocalSettings] = useState(settingsData);
  const [selectedId, setSelectedId] = useState(settingsData.active_provider_id || settingsData.providers?.[0]?.id || '');
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const debounceRef = useRef(null);
  const dirtyRef = useRef(false);

  const [projTargetChapters, setProjTargetChapters] = useState(30);
  const [projWordCount, setProjWordCount] = useState(3000);
  const [projMode, setProjMode] = useState('step');
  const [projOptimizeInterval, setProjOptimizeInterval] = useState(10);
  const [savingProjConfig, setSavingProjConfig] = useState(false);

  useEffect(() => {
    if (activeProjectStatus) {
      setProjTargetChapters(activeProjectStatus.target_chapters !== undefined ? activeProjectStatus.target_chapters : DEFAULT_TARGET_CHAPTERS);
      setProjWordCount(activeProjectStatus.word_count_per_chapter !== undefined ? activeProjectStatus.word_count_per_chapter : DEFAULT_WORD_COUNT_PER_CHAPTER);
      setProjMode(activeProjectStatus.mode || 'step');
      setProjOptimizeInterval(activeProjectStatus.optimize_interval !== undefined ? activeProjectStatus.optimize_interval : 10);
    } else if (activeProject) {
      setProjTargetChapters(activeProject.target_chapters !== undefined ? activeProject.target_chapters : DEFAULT_TARGET_CHAPTERS);
      setProjWordCount(activeProject.word_count_per_chapter !== undefined ? activeProject.word_count_per_chapter : DEFAULT_WORD_COUNT_PER_CHAPTER);
      setProjMode(activeProject.mode || 'step');
      setProjOptimizeInterval(activeProject.optimize_interval !== undefined ? activeProject.optimize_interval : 10);
    }
  }, [activeProject, activeProjectStatus]);

  useEffect(() => {
    if (dirtyRef.current) return;
    setLocalSettings(settingsData);
    const id = settingsData.active_provider_id || settingsData.providers?.[0]?.id || '';
    if (id) setSelectedId(id);
  }, [settingsData]);

  const providers = localSettings.providers || [];
  const current = providers.find((p) => p.id === selectedId) || providers[0];

  useEffect(() => {
    if (!showModelMenu) return;
    const onDown = (e) => {
      if (!e.target.closest?.('[data-model-combobox]')) setShowModelMenu(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [showModelMenu]);

  const persist = useCallback(async (data, immediate = false) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const doSave = async () => {
      setSaving(true);
      try {
        await saveSettings(data);
        dirtyRef.current = false;
        setDirty(false);
      } finally {
        setSaving(false);
      }
    };
    if (immediate) {
      await doSave();
    } else {
      debounceRef.current = setTimeout(doSave, 600);
    }
  }, [saveSettings]);

  const patchCurrent = (patch, immediate = false) => {
    const nextProviders = providers.map((p) => (p.id === current.id ? { ...p, ...patch } : p));
    const next = { ...localSettings, providers: nextProviders, backup_provider_id: null };
    setLocalSettings(next);
    dirtyRef.current = true;
    setDirty(true);
    persist(next, immediate);
  };

  const handleSelectProvider = (id) => {
    setSelectedId(id);
    setTestResult(null);
    setShowModelMenu(false);
    const next = { ...localSettings, active_provider_id: id, backup_provider_id: null };
    setLocalSettings(next);
    persist(next, true);
  };

  const addProvider = (preset) => {
    const baseId = preset.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'custom';
    let id = baseId;
    let n = 1;
    while (providers.some((p) => p.id === id)) id = `${baseId}-${n++}`;
    const newProvider = {
      id,
      name: preset.name === '自定义' ? '新提供商' : preset.name,
      base_url: preset.base_url,
      api_key: '',
      model: preset.model || '',
      embedding_model: '',
      cached_models: [],
    };
    const nextProviders = [...providers, newProvider];
    const next = { ...localSettings, providers: nextProviders, active_provider_id: id, backup_provider_id: null };
    setLocalSettings(next);
    setSelectedId(id);
    setShowAddMenu(false);
    persist(next, true);
  };

  const removeProvider = () => {
    if (providers.length <= 1 || !current) return;
    const nextProviders = providers.filter((p) => p.id !== current.id);
    const nextId = nextProviders[0].id;
    const next = { ...localSettings, providers: nextProviders, active_provider_id: nextId, backup_provider_id: null };
    setLocalSettings(next);
    setSelectedId(nextId);
    persist(next, true);
  };

  const fetchModels = async () => {
    if (!current?.api_key?.trim() && !current?.has_api_key) {
      setTestResult({ ok: false, error: '请先填写 API Key' });
      return;
    }
    setLoadingModels(true);
    setTestResult(null);
    try {
      const data = await settingsApi.modelsByProvider({
        provider_id: current.id,
        base_url: current.base_url || '',
        api_key: current.api_key,
      });
      if (data.ok && data.models?.length) {
        const fetched = data.models;
        const nextModel = fetched.includes(current.model) ? current.model : fetched[0];
        const patch = { cached_models: fetched, cached_model_details: data.model_details || {}, model: nextModel };
        if (data.auto_corrected && data.base_url !== current.base_url) {
          patch.base_url = data.base_url;
        }
        const nextProviders = providers.map((p) =>
          p.id === current.id ? { ...p, ...patch } : p,
        );
        const next = { ...localSettings, providers: nextProviders, backup_provider_id: null };
        setLocalSettings(next);
        dirtyRef.current = true;
        setDirty(true);
        persist(next);
        setTestResult({ ok: true, message: `已拉取 ${fetched.length} 个模型，请在下拉框中选择。` });
      } else {
        setTestResult({ ok: false, error: data.error || '无法获取模型列表' });
      }
    } catch (e) {
      setTestResult({ ok: false, error: e.message });
    } finally {
      setLoadingModels(false);
    }
  };

  const testConnection = async () => {
    if (!current) return;
    setTesting(true);
    setTestResult(null);
    try {
      const data = await settingsApi.testProvider({
        provider_id: current.id,
        base_url: current.base_url,
        api_key: current.api_key,
        model: current.model,
      });
      if (data.ok && data.auto_corrected && data.base_url !== current.base_url) {
        patchCurrent({ base_url: data.base_url });
      }
      setTestResult(data);
    } catch (e) {
      setTestResult({ ok: false, error: e.message });
    } finally {
      setTesting(false);
    }
  };

  const modelOptions = buildModelOptions(current);
  const selectedModelDetail = modelDetailFor(current, current?.model);

  return (
    <div style={{ maxWidth: '720px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {activeProject && (
        <div className="glass-panel" style={{ padding: '24px', borderRadius: '12px', border: '1px solid rgba(245, 158, 11, 0.25)', background: 'rgba(245, 158, 11, 0.02)' }}>
          <h3 style={{ marginTop: 0, color: 'var(--color-amber, #f59e0b)' }}>当前项目基本参数设置 ({activeProject.title})</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginTop: '16px' }}>
            <div className="form-group">
              <label className="form-label">目标编写章数</label>
              <input 
                type="number"
                min={(activeProjectStatus?.current_chapter || activeProject?.current_chapter || 0) + 1}
                className="form-input" 
                value={projTargetChapters} 
                onChange={(e) => setProjTargetChapters(parseInt(e.target.value) || 1)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">每章字数限制</label>
              <input 
                type="number"
                min="0"
                className="form-input" 
                value={projWordCount} 
                onChange={(e) => setProjWordCount(parseInt(e.target.value) || 0)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">写书创作模式</label>
              <select 
                className="form-input"
                value={projMode}
                onChange={(e) => setProjMode(e.target.value)}
              >
                <option value="step">分步生成与人机协同模式</option>
                <option value="auto">全自动生成完结模式</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">大纲优化频率 (章)</label>
              <input 
                type="number"
                min="1"
                className="form-input" 
                value={projOptimizeInterval} 
                onChange={(e) => setProjOptimizeInterval(parseInt(e.target.value) || 1)}
              />
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
            <button 
              className="btn btn-primary" 
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              disabled={savingProjConfig}
              onClick={async () => {
                setSavingProjConfig(true);
                if (onUpdateProjectConfig) {
                  await onUpdateProjectConfig({
                    word_count_per_chapter: projWordCount,
                    mode: projMode,
                    optimize_interval: projOptimizeInterval,
                    target_chapters: projTargetChapters
                  });
                }
                setSavingProjConfig(false);
              }}
            >
              {savingProjConfig ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />} 保存项目配置
            </button>
          </div>
        </div>
      )}
      <div className="glass-panel" style={{ padding: '24px', borderRadius: '12px' }}>
        <h3 style={{ marginTop: 0 }}>前后端连接配置 (Connection Config)</h3>
        <div className="form-group" style={{ marginTop: '12px' }}>
          <label className="form-label">后端 API 服务地址 (Backend API URL)</label>
          <div style={{ display: 'flex', gap: '10px' }}>
            <input
              className="form-input"
              style={{ flex: 1 }}
              value={localBackendUrl}
              onChange={(e) => setLocalBackendUrl(e.target.value)}
              placeholder="例如: http://127.0.0.1:8000"
            />
            <button className="btn btn-primary" onClick={() => saveBackendUrl(localBackendUrl)} style={{ whiteSpace: 'nowrap' }}>
              保存并重连
            </button>
          </div>
        </div>
      </div>

      <div className="glass-panel" style={{ padding: '24px', borderRadius: '12px' }}>
        <h3 style={{ marginTop: 0 }}>智能体模型供应配置 (LLM Config)</h3>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '8px 0 0' }}>
          可保存多个模型提供商的 API Key，通过下拉框切换编辑；当前选中的提供商即为创作链路使用的模型。
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '20px' }}>
          <div className="form-group">
            <label className="form-label">选择模型提供商</label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <select
                className="form-input"
                style={{ flex: 1 }}
                value={selectedId}
                onChange={(e) => handleSelectProvider(e.target.value)}
              >
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <div style={{ position: 'relative' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddMenu((v) => !v)} title="添加提供商">
                  <Plus size={14} />
                </button>
                {showAddMenu && (
                  <div className="provider-add-menu">
                    {PROVIDER_PRESETS.map((preset) => (
                      <button key={preset.name} type="button" className="provider-add-menu-item" onClick={() => addProvider(preset)}>
                        {preset.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {providers.length > 1 && (
                <button type="button" className="btn btn-secondary provider-delete-btn" onClick={removeProvider} title="删除当前提供商">
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          </div>

          {current && (
            <div className="provider-card provider-card-active">
              <div className="provider-card-body" style={{ paddingTop: 0 }}>
                <div className="form-group">
                  <label className="form-label">提供商名称</label>
                  <input
                    className="form-input"
                    value={current.name}
                    onChange={(e) => patchCurrent({ name: e.target.value })}
                    placeholder="例如 DeepSeek"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">API 基础路径 (Base URL)</label>
                  <input
                    className="form-input"
                    value={current.base_url}
                    onChange={(e) => patchCurrent({ base_url: e.target.value })}
                    placeholder="https://api.example.com/v1"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">API 密匙 (API Key)</label>
                  <input
                    className="form-input"
                    type="password"
                    value={current.api_key}
                    onChange={(e) => patchCurrent({ api_key: e.target.value })}
                    placeholder={current.has_api_key ? '已安全保存；留空保持原密钥' : 'sk-...'}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">大语言模型 (Model)</label>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <div data-model-combobox style={{ position: 'relative', flex: 1 }}>
                      <input
                        className="form-input"
                        style={{ width: '100%', minWidth: 0, boxSizing: 'border-box', paddingRight: '32px' }}
                        value={current.model || ''}
                        onChange={(e) => patchCurrent({ model: e.target.value }, true)}
                        onFocus={() => { if (modelOptions.length) setShowModelMenu(true); }}
                        placeholder="输入模型名，或点右侧箭头选择"
                      />
                      <button
                        type="button"
                        onClick={() => setShowModelMenu((v) => !v)}
                        title={modelOptions.length ? '展开候选模型' : '暂无候选，点刷新拉取或直接输入'}
                        style={{ position: 'absolute', right: '4px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', padding: '4px', color: 'var(--text-secondary)', display: 'flex' }}
                      >
                        <ChevronDown size={16} style={{ transform: showModelMenu ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
                      </button>
                      {showModelMenu && (
                        <div className="provider-add-menu" style={{ left: 0, right: 0, minWidth: 0, maxHeight: '240px', overflowY: 'auto' }}>
                          {modelOptions.length === 0 ? (
                            <div style={{ padding: '10px 12px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                              暂无候选模型，请填写 API Key 后点刷新，或直接在输入框键入模型名。
                            </div>
                          ) : (
                            modelOptions.map((m) => (
                              <button
                                key={m}
                                type="button"
                                className="provider-add-menu-item"
                                style={{ fontWeight: m === current.model ? 600 : 400 }}
                                onClick={() => { patchCurrent({ model: m }, true); setShowModelMenu(false); }}
                              >
                                {m}
                              </button>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                    <button type="button" className="btn btn-secondary" onClick={fetchModels} disabled={loadingModels} title="从 API 拉取可用模型">
                      {loadingModels ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                    </button>
                  </div>
                  <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: '6px 0 0' }}>
                    {modelOptions.length > 0
                      ? `共 ${modelOptions.length} 个候选模型，可直接输入或点箭头从列表选择；切换后立即保存，并从下一次智能体调用生效。已发出的请求不会中途切换。`
                      : '可直接输入模型名；填写 API Key 后点刷新可拉取候选列表。'}
                  </p>
                  {selectedModelDetail && (
                    <div style={{ marginTop: '8px', padding: '10px', borderRadius: '8px', border: '1px solid var(--border-muted)', background: 'rgba(0,0,0,0.12)', fontSize: '11px', color: 'var(--text-secondary)', display: 'grid', gap: '4px' }}>
                      <div><strong>能力:</strong> {formatModelDetailValue(selectedModelDetail.capabilities)}</div>
                      <div><strong>上下文长度:</strong> {formatModelDetailValue(selectedModelDetail.context_length)}</div>
                      <div><strong>定价:</strong> {formatModelDetailValue(selectedModelDetail.pricing)}</div>
                    </div>
                  )}
                </div>
                <div className="form-group">
                  <label className="form-label">嵌入模型 (Embedding Model，可选)</label>
                  <input
                    className="form-input"
                    value={current.embedding_model || ''}
                    onChange={(e) => patchCurrent({ embedding_model: e.target.value })}
                    placeholder="留空则使用默认"
                  />
                </div>

                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={testConnection} disabled={testing}>
                    {testing ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />} 测试连接
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => persist(localSettings, true)}
                    disabled={!dirty || saving}
                  >
                    {saving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />}
                    {saving ? '保存中…' : dirty ? '立即保存' : '已保存'}
                  </button>
                </div>

                {testResult && (
                  <div className={`provider-test-result ${testResult.ok ? 'ok' : 'fail'}`}>
                    {testResult.ok
                      ? (testResult.message || '连接成功，API 鉴权正常。')
                      : `失败: ${testResult.error}`}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="glass-panel" style={{ padding: '24px', borderRadius: '12px' }}>
        <h3 style={{ marginTop: 0 }}>心跳卡死看门狗配置 (Watchdog Config)</h3>
        <div className="form-group" style={{ marginTop: '20px' }}>
          <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>看门狗心跳超时阈值:</span>
            <span style={{ fontWeight: 'bold' }}>{localSettings.watchdog_timeout || 45} 秒</span>
          </label>
          <input
            type="range"
            min="15"
            max="180"
            step="5"
            style={{ width: '100%', accentColor: 'var(--vermilion)' }}
            value={localSettings.watchdog_timeout || 45}
            onChange={(e) => {
              const next = { ...localSettings, watchdog_timeout: parseInt(e.target.value, 10) };
              setLocalSettings(next);
              persist(next);
            }}
          />
        </div>
        <WatchdogP95Estimator
          onApplySuggested={(val) => {
            const next = { ...localSettings, watchdog_timeout: val };
            setLocalSettings(next);
            persist(next, true);
          }}
        />
      </div>
    </div>
  );
}

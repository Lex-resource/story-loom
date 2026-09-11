import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import { DEFAULT_TARGET_CHAPTERS, DEFAULT_WORD_COUNT_PER_CHAPTER } from '../utils/constants';
import { settingsApi } from '../services/novelApi';
import { createRequestGuard } from '../utils/requestLifecycle';
import ProviderEditor from '../components/settings/ProviderEditor';

const PROVIDER_PRESETS = [
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com', model: 'deepseek-v4-flash' },
  { name: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o' },
  { name: 'Moonshot (Kimi)', base_url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { name: '智谱 GLM', base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  { name: '通义千问', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { name: '自定义', base_url: '', model: 'deepseek-v4-flash' },
];

function buildModelOptions(provider) {
  return provider?.cached_models?.length ? provider.cached_models : [];
}

function modelDetailFor(provider, modelId) {
  return provider?.cached_model_details?.[modelId] || null;
}

export default function Settings({
  settingsData,
  saveSettings,
  activeProject,
  activeProjectStatus,
  onUpdateProjectConfig,
}) {
  const [localSettings, setLocalSettings] = useState(settingsData);
  const [selectedId, setSelectedId] = useState(
    settingsData.active_provider_id || settingsData.providers?.[0]?.id || '',
  );
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const debounceRef = useRef(null);
  const saveVersionRef = useRef(0);
  const dirtyRef = useRef(false);
  const providerRequestGuardRef = useRef(null);
  if (!providerRequestGuardRef.current) providerRequestGuardRef.current = createRequestGuard();
  const selectedProviderRef = useRef(selectedId);
  selectedProviderRef.current = selectedId;

  const [projTargetChapters, setProjTargetChapters] = useState(30);
  const [projWordCount, setProjWordCount] = useState(3000);
  const [projMode, setProjMode] = useState('step');
  const [projOptimizeInterval, setProjOptimizeInterval] = useState(10);
  const [savingProjConfig, setSavingProjConfig] = useState(false);

  useEffect(
    () => () => {
      providerRequestGuardRef.current.cancel();
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    [],
  );

  useEffect(() => {
    const source = activeProjectStatus || activeProject;
    if (!source) return;
    setProjTargetChapters(source.target_chapters ?? DEFAULT_TARGET_CHAPTERS);
    setProjWordCount(source.word_count_per_chapter ?? DEFAULT_WORD_COUNT_PER_CHAPTER);
    setProjMode(source.mode || 'step');
    setProjOptimizeInterval(source.optimize_interval ?? 10);
  }, [activeProject, activeProjectStatus]);

  useEffect(() => {
    if (dirtyRef.current) return;
    setLocalSettings(settingsData);
    const id = settingsData.active_provider_id || settingsData.providers?.[0]?.id || '';
    if (id) setSelectedId(id);
  }, [settingsData]);

  const providers = localSettings.providers || [];
  const current = providers.find((provider) => provider.id === selectedId) || providers[0];
  const activeProviderId = localSettings.active_provider_id || providers[0]?.id || '';
  const backupProviderId =
    providers.some((provider) => provider.id === localSettings.backup_provider_id) &&
    localSettings.backup_provider_id !== activeProviderId
      ? localSettings.backup_provider_id
      : '';

  const persist = useCallback(
    async (data, immediate = false) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      const saveVersion = ++saveVersionRef.current;
      const doSave = async () => {
        setSaving(true);
        try {
          const saved = await saveSettings(data);
          if (saved && saveVersion === saveVersionRef.current) {
            dirtyRef.current = false;
            setDirty(false);
          }
        } finally {
          if (saveVersion === saveVersionRef.current) setSaving(false);
        }
      };
      if (immediate) await doSave();
      else debounceRef.current = setTimeout(doSave, 600);
    },
    [saveSettings],
  );

  const patchCurrent = (patch, immediate = false) => {
    providerRequestGuardRef.current.cancel();
    if (!current) return;
    const nextProviders = providers.map((provider) =>
      provider.id === current.id ? { ...provider, ...patch } : provider,
    );
    const next = { ...localSettings, providers: nextProviders };
    setLocalSettings(next);
    dirtyRef.current = true;
    setDirty(true);
    persist(next, immediate);
  };

  const updateBackupProvider = (value) => {
    providerRequestGuardRef.current.cancel();
    const next = { ...localSettings, backup_provider_id: value || null };
    setLocalSettings(next);
    dirtyRef.current = true;
    setDirty(true);
    persist(next, true);
  };

  const handleSelectProvider = (id) => {
    providerRequestGuardRef.current.cancel();
    setSelectedId(id);
    setTestResult(null);
    setShowModelMenu(false);
    const next = {
      ...localSettings,
      active_provider_id: id,
      backup_provider_id: localSettings.backup_provider_id === id ? null : localSettings.backup_provider_id,
    };
    setLocalSettings(next);
    dirtyRef.current = true;
    setDirty(true);
    persist(next, true);
  };

  const addProvider = (preset) => {
    providerRequestGuardRef.current.cancel();
    const baseId =
      preset.name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '') || 'custom';
    let id = baseId;
    let suffix = 1;
    while (providers.some((provider) => provider.id === id)) id = `${baseId}-${suffix++}`;
    const provider = {
      id,
      name: preset.name === '自定义' ? '新提供商' : preset.name,
      base_url: preset.base_url,
      api_key: '',
      model: preset.model || '',
      embedding_model: '',
      cached_models: [],
    };
    const next = { ...localSettings, providers: [...providers, provider], active_provider_id: id };
    setLocalSettings(next);
    setSelectedId(id);
    setShowAddMenu(false);
    dirtyRef.current = true;
    setDirty(true);
    persist(next, true);
  };

  const removeProvider = () => {
    if (providers.length <= 1 || !current) return;
    providerRequestGuardRef.current.cancel();
    const nextProviders = providers.filter((provider) => provider.id !== current.id);
    const nextId = nextProviders[0].id;
    const next = {
      ...localSettings,
      providers: nextProviders,
      active_provider_id: nextId,
      backup_provider_id: localSettings.backup_provider_id === current.id ? null : localSettings.backup_provider_id,
    };
    setLocalSettings(next);
    setSelectedId(nextId);
    dirtyRef.current = true;
    setDirty(true);
    persist(next, true);
  };

  const fetchModels = async () => {
    if (!current?.api_key?.trim() && !current?.has_api_key) {
      setTestResult({ ok: false, error: '请先填写 API Key' });
      return;
    }
    setLoadingModels(true);
    setTestResult(null);
    const providerId = current.id;
    const request = providerRequestGuardRef.current.start();
    try {
      const data = await settingsApi.modelsByProvider(
        { provider_id: providerId, base_url: current.base_url || '', api_key: current.api_key },
        { signal: request.signal },
      );
      if (!request.isCurrent() || selectedProviderRef.current !== providerId) return;
      if (data.ok && data.models?.length) {
        const fetched = data.models;
        const patch = {
          cached_models: fetched,
          cached_model_details: data.model_details || {},
          model: fetched.includes(current.model) ? current.model : fetched[0],
          ...(data.auto_corrected && data.base_url !== current.base_url ? { base_url: data.base_url } : {}),
        };
        const next = {
          ...localSettings,
          providers: providers.map((provider) => (provider.id === current.id ? { ...provider, ...patch } : provider)),
        };
        setLocalSettings(next);
        dirtyRef.current = true;
        setDirty(true);
        persist(next);
        setTestResult({ ok: true, message: `已拉取 ${fetched.length} 个模型，请在下拉框中选择。` });
      } else {
        setTestResult({ ok: false, error: data.error || '无法获取模型列表' });
      }
    } catch (error) {
      if (!request.isCurrent() || error.name === 'AbortError') return;
      setTestResult({ ok: false, error: error.message });
    } finally {
      if (request.isCurrent()) setLoadingModels(false);
    }
  };

  const testConnection = async () => {
    if (!current) return;
    setTesting(true);
    setTestResult(null);
    const providerId = current.id;
    const request = providerRequestGuardRef.current.start();
    try {
      const data = await settingsApi.testProvider(
        { provider_id: providerId, base_url: current.base_url, api_key: current.api_key, model: current.model },
        { signal: request.signal },
      );
      if (!request.isCurrent() || selectedProviderRef.current !== providerId) return;
      if (data.ok && data.auto_corrected && data.base_url !== current.base_url)
        patchCurrent({ base_url: data.base_url });
      setTestResult(data);
    } catch (error) {
      if (!request.isCurrent() || error.name === 'AbortError') return;
      setTestResult({ ok: false, error: error.message });
    } finally {
      if (request.isCurrent()) setTesting(false);
    }
  };

  const modelOptions = buildModelOptions(current);
  const selectedModelDetail = modelDetailFor(current, current?.model);

  return (
    <div style={{ maxWidth: '720px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {activeProject && (
        <div
          className="glass-panel"
          style={{
            padding: '24px',
            borderRadius: '12px',
            border: '1px solid rgba(245, 158, 11, 0.25)',
            background: 'rgba(245, 158, 11, 0.02)',
          }}
        >
          <h3 style={{ marginTop: 0, color: 'var(--color-amber, #f59e0b)' }}>
            当前项目基本参数设置 ({activeProject.title})
          </h3>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '16px',
              marginTop: '16px',
            }}
          >
            <div className="form-group">
              <label className="form-label">目标编写章数</label>
              <input
                type="number"
                min={(activeProjectStatus?.current_chapter || activeProject?.current_chapter || 0) + 1}
                className="form-input"
                value={projTargetChapters}
                onChange={(e) => setProjTargetChapters(parseInt(e.target.value, 10) || 1)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">每章字数限制</label>
              <input
                type="number"
                min="0"
                className="form-input"
                value={projWordCount}
                onChange={(e) => setProjWordCount(parseInt(e.target.value, 10) || 0)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">写书创作模式</label>
              <select className="form-input" value={projMode} onChange={(e) => setProjMode(e.target.value)}>
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
                onChange={(e) => setProjOptimizeInterval(parseInt(e.target.value, 10) || 1)}
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
                try {
                  await onUpdateProjectConfig?.({
                    word_count_per_chapter: projWordCount,
                    mode: projMode,
                    optimize_interval: projOptimizeInterval,
                    target_chapters: projTargetChapters,
                  });
                } finally {
                  setSavingProjConfig(false);
                }
              }}
            >
              {savingProjConfig ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />} 保存项目配置
            </button>
          </div>
        </div>
      )}
      <ProviderEditor
        providers={providers}
        current={current}
        selectedId={selectedId}
        activeProviderId={activeProviderId}
        backupProviderId={backupProviderId}
        providerPresets={PROVIDER_PRESETS}
        modelOptions={modelOptions}
        selectedModelDetail={selectedModelDetail}
        showAddMenu={showAddMenu}
        showModelMenu={showModelMenu}
        loadingModels={loadingModels}
        testing={testing}
        testResult={testResult}
        dirty={dirty}
        saving={saving}
        localSettings={localSettings}
        onSelectProvider={handleSelectProvider}
        onToggleAddMenu={() => setShowAddMenu((value) => !value)}
        onAddProvider={addProvider}
        onRemoveProvider={removeProvider}
        onPatchCurrent={patchCurrent}
        onToggleModelMenu={setShowModelMenu}
        onFetchModels={fetchModels}
        onUpdateBackupProvider={updateBackupProvider}
        onTestConnection={testConnection}
        onSave={(data) => persist(data, true)}
      />
    </div>
  );
}

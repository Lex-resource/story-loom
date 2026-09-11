import { ChevronDown, Loader2, Plus, RefreshCw, Save, Trash2 } from 'lucide-react';

function formatModelDetailValue(value) {
  if (value === null || value === undefined || value === '') return '未提供';
  if (Array.isArray(value)) return value.length ? value.join('、') : '未提供';
  if (typeof value === 'object') {
    return (
      Object.entries(value)
        .map(([key, item]) => `${key}: ${item}`)
        .join('；') || '未提供'
    );
  }
  return String(value);
}

export default function ProviderEditor({
  providers,
  current,
  selectedId,
  activeProviderId,
  backupProviderId,
  providerPresets,
  modelOptions,
  selectedModelDetail,
  showAddMenu,
  showModelMenu,
  loadingModels,
  testing,
  testResult,
  dirty,
  saving,
  localSettings,
  onSelectProvider,
  onToggleAddMenu,
  onAddProvider,
  onRemoveProvider,
  onPatchCurrent,
  onToggleModelMenu,
  onFetchModels,
  onUpdateBackupProvider,
  onTestConnection,
  onSave,
}) {
  return (
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
              onChange={(e) => onSelectProvider(e.target.value)}
            >
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </select>
            <div style={{ position: 'relative' }}>
              <button type="button" className="btn btn-secondary" onClick={onToggleAddMenu} title="添加提供商">
                <Plus size={14} />
              </button>
              {showAddMenu && (
                <div className="provider-add-menu">
                  {providerPresets.map((preset) => (
                    <button
                      key={preset.name}
                      type="button"
                      className="provider-add-menu-item"
                      onClick={() => onAddProvider(preset)}
                    >
                      {preset.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {providers.length > 1 && (
              <button
                type="button"
                className="btn btn-secondary provider-delete-btn"
                onClick={onRemoveProvider}
                title="删除当前提供商"
              >
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
                  onChange={(e) => onPatchCurrent({ name: e.target.value })}
                  placeholder="例如 DeepSeek"
                />
              </div>
              <div className="form-group">
                <label className="form-label">API 基础路径 (Base URL)</label>
                <input
                  className="form-input"
                  value={current.base_url}
                  onChange={(e) => onPatchCurrent({ base_url: e.target.value })}
                  placeholder="https://api.example.com/v1"
                />
              </div>
              <div className="form-group">
                <label className="form-label">API 密匙 (API Key)</label>
                <input
                  className="form-input"
                  type="password"
                  value={current.api_key}
                  onChange={(e) => onPatchCurrent({ api_key: e.target.value })}
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
                      onChange={(e) => onPatchCurrent({ model: e.target.value }, true)}
                      onFocus={() => modelOptions.length && onToggleModelMenu(true)}
                      placeholder="输入模型名，或点右侧箭头选择"
                    />
                    <button
                      type="button"
                      onClick={() => onToggleModelMenu(!showModelMenu)}
                      title={modelOptions.length ? '展开候选模型' : '暂无候选，点刷新拉取或直接输入'}
                      style={{
                        position: 'absolute',
                        right: '4px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        padding: '4px',
                        color: 'var(--text-secondary)',
                        display: 'flex',
                      }}
                    >
                      <ChevronDown
                        size={16}
                        style={{ transform: showModelMenu ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}
                      />
                    </button>
                    {showModelMenu && (
                      <div
                        className="provider-add-menu"
                        style={{ left: 0, right: 0, minWidth: 0, maxHeight: '240px', overflowY: 'auto' }}
                      >
                        {modelOptions.length === 0 ? (
                          <div style={{ padding: '10px 12px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                            暂无候选模型，请填写 API Key 后点刷新，或直接在输入框键入模型名。
                          </div>
                        ) : (
                          modelOptions.map((model) => (
                            <button
                              key={model}
                              type="button"
                              className="provider-add-menu-item"
                              style={{ fontWeight: model === current.model ? 600 : 400 }}
                              onClick={() => {
                                onPatchCurrent({ model }, true);
                                onToggleModelMenu(false);
                              }}
                            >
                              {model}
                            </button>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={onFetchModels}
                    disabled={loadingModels}
                    title="从 API 拉取可用模型"
                  >
                    {loadingModels ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                  </button>
                </div>
                <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: '6px 0 0' }}>
                  {modelOptions.length > 0
                    ? `共 ${modelOptions.length} 个候选模型，可直接输入或点箭头从列表选择；切换后立即保存，并从下一次智能体调用生效。已发出的请求不会中途切换。`
                    : '可直接输入模型名；填写 API Key 后点刷新可拉取候选列表。'}
                </p>
                {selectedModelDetail && (
                  <div
                    style={{
                      marginTop: '8px',
                      padding: '10px',
                      borderRadius: '8px',
                      border: '1px solid var(--border-muted)',
                      background: 'rgba(0,0,0,0.12)',
                      fontSize: '11px',
                      color: 'var(--text-secondary)',
                      display: 'grid',
                      gap: '4px',
                    }}
                  >
                    <div>
                      <strong>能力:</strong> {formatModelDetailValue(selectedModelDetail.capabilities)}
                    </div>
                    <div>
                      <strong>上下文长度:</strong> {formatModelDetailValue(selectedModelDetail.context_length)}
                    </div>
                    <div>
                      <strong>定价:</strong> {formatModelDetailValue(selectedModelDetail.pricing)}
                    </div>
                  </div>
                )}
              </div>
              <div className="form-group">
                <label className="form-label">嵌入模型 (Embedding Model，可选)</label>
                <input
                  className="form-input"
                  value={current.embedding_model || ''}
                  onChange={(e) => onPatchCurrent({ embedding_model: e.target.value })}
                  placeholder="留空则使用默认"
                />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="backup-provider-select">
                  备用模型（可选）
                </label>
                <select
                  id="backup-provider-select"
                  className="form-input"
                  value={backupProviderId}
                  onChange={(e) => onUpdateBackupProvider(e.target.value)}
                >
                  <option value="">不启用备用模型</option>
                  {providers
                    .filter((provider) => provider.id !== activeProviderId)
                    .map((provider) => (
                      <option key={provider.id} value={provider.id}>
                        {provider.name || provider.id}（{provider.model || '未配置模型'}）
                      </option>
                    ))}
                </select>
                <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: '6px 0 0' }}>
                  未选择时，主模型失败会直接报错，不会自动切换到其他 provider。
                </p>
              </div>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={onTestConnection}
                  disabled={testing}
                >
                  {testing ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />} 测试连接
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() => onSave(localSettings)}
                  disabled={!dirty || saving}
                >
                  {saving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />}{' '}
                  {saving ? '保存中…' : dirty ? '立即保存' : '已保存'}
                </button>
              </div>
              {testResult && (
                <div className={`provider-test-result ${testResult.ok ? 'ok' : 'fail'}`}>
                  {testResult.ok ? testResult.message || '连接成功，API 鉴权正常。' : `失败: ${testResult.error}`}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

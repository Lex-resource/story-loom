import { useState, useEffect } from 'react';
import { Save, Loader2, AlertCircle } from 'lucide-react';
import { systemConfigApi } from '../services/novelApi';

export default function SystemConfigs() {
  const [loading, setLoading] = useState(true);
  const [configs, setConfigs] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [availableNodes, setAvailableNodes] = useState([]);
  const [availableDocs, setAvailableDocs] = useState([]);
  const [selectedFormat, setSelectedFormat] = useState('');
  const [selectedType, setSelectedType] = useState('all');
  const [selectedAgentId, setSelectedAgentId] = useState(null);
  
  const [currentConfig, setCurrentConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [confData, promptData, nodesData, docsData] = await systemConfigApi.load();
        setConfigs(confData);
        setPrompts(promptData);
        setAvailableNodes(nodesData);
        setAvailableDocs(docsData);
        
        if (confData.length > 0) {
          const defaultFormat = confData[0].name;
          setSelectedFormat(defaultFormat);
          setCurrentConfig(JSON.parse(JSON.stringify(confData[0])));
        }
    } catch (e) {
      showToast(`加载失败: ${e.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedFormat && configs.length > 0) {
      const conf = configs.find(c => c.name === selectedFormat);
      if (conf) {
        setCurrentConfig(JSON.parse(JSON.stringify(conf)));
      }
    }
  }, [selectedFormat, configs]);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleSave = async () => {
    if (!currentConfig) return;
    setSaving(true);
    try {
      await systemConfigApi.updatePipeline(currentConfig.name, {
        name_zh: currentConfig.name_zh,
        nodes: currentConfig.nodes,
        enable_living_docs_update: currentConfig.enable_living_docs_update,
        enable_editor_loop: currentConfig.enable_editor_loop,
        max_rewrite: parseInt(currentConfig.max_rewrite) || 1,
        readonly_docs: currentConfig.readonly_docs,
        required_docs: currentConfig.required_docs,
        enable_force_correction: currentConfig.enable_force_correction,
        validation_before_editor: currentConfig.validation_before_editor,
      });
      showToast('流程配置保存成功！', 'success');
      const updated = configs.map(c => c.name === currentConfig.name ? currentConfig : c);
      setConfigs(updated);
    } catch (e) {
      showToast(`保存出错: ${e.message}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleCheckboxToggle = (field, id) => {
    const currentArray = currentConfig[field] || [];
    if (currentArray.includes(id)) {
      setCurrentConfig({
        ...currentConfig,
        [field]: currentArray.filter(item => item !== id)
      });
    } else {
      setCurrentConfig({
        ...currentConfig,
        [field]: [...currentArray, id]
      });
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', color: 'var(--ink-light)' }}>
        <Loader2 className="spin-slow" size={32} />
        <span style={{ marginLeft: '12px' }}>正在加载系统配置...</span>
      </div>
    );
  }

  // Filter prompts to only those belonging to the selected novel format
  const currentFormatPrompts = prompts.filter(p => p.category === selectedFormat);
  const availableTypes = ['all', ...new Set(currentFormatPrompts.map(p => p.type).filter(Boolean))];
  const currentPrompts = selectedType === 'all' ? currentFormatPrompts : currentFormatPrompts.filter(p => p.type === selectedType);
  const displayAgent = currentPrompts.find(p => p.id === selectedAgentId) || currentPrompts[0];

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px', paddingBottom: '40px', padding: '0 20px' }}>
      
      {/* 顶部格式选择 */}
      <div className="glass-panel" style={{ padding: '20px', borderRadius: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ margin: '0 0 8px 0' }}>全局流程与智能体配置</h3>
            <p style={{ margin: 0, fontSize: '13px', color: 'var(--ink-light)' }}>在此处配置长篇小说与短篇小说的生成工作流和可用智能体。</p>
          </div>
          <div>
            <select 
              className="form-input" 
              style={{ minWidth: '180px', fontWeight: 'bold' }}
              value={selectedFormat}
              onChange={(e) => setSelectedFormat(e.target.value)}
            >
              {configs.map(c => (
                <option key={c.name} value={c.name}>{c.name_zh || c.name} ({c.name})</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {currentConfig && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '24px', alignItems: 'stretch' }}>
          {/* 左侧：流程核心参数 */}
          <div className="glass-panel" style={{ padding: '24px', borderRadius: '12px', maxHeight: 'calc(100vh - 120px)', overflowY: 'auto' }}>
            <h3 style={{ marginTop: 0, borderBottom: '1px solid var(--border-muted)', paddingBottom: '12px', display: 'flex', justifyContent: 'space-between' }}>
              <span>流程核心参数</span>
              <button className="btn btn-primary" style={{ padding: '4px 16px', fontSize: '13px' }} onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 size={16} className="spin-slow" /> : <Save size={16} />} 
                {saving ? '保存中...' : '保存配置'}
              </button>
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '16px' }}>
              
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">启用节点链路 (Nodes)</label>
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginTop: '8px' }}>
                  {availableNodes.map(node => (
                    <label key={node.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '13px' }}>
                      <input 
                        type="checkbox" 
                        checked={(currentConfig.nodes || []).includes(node.id)}
                        onChange={() => handleCheckboxToggle('nodes', node.id)}
                      />
                      {node.label}
                    </label>
                  ))}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--ink-lighter)', marginTop: '8px' }}>勾选的节点将作为创作流的核心环节被激活。</div>
              </div>

              <div className="form-group">
                <label className="form-label">最大重写次数 (max_rewrite)</label>
                <input 
                  type="number" 
                  min="0"
                  className="form-input" 
                  value={currentConfig.max_rewrite} 
                  onChange={(e) => setCurrentConfig({...currentConfig, max_rewrite: e.target.value})}
                />
              </div>

              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '8px', justifyContent: 'center' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                  <input 
                    type="checkbox" 
                    checked={currentConfig.enable_editor_loop} 
                    onChange={(e) => setCurrentConfig({...currentConfig, enable_editor_loop: e.target.checked})}
                  />
                  启用 Editor 打回重写循环
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                  <input 
                    type="checkbox" 
                    checked={currentConfig.enable_living_docs_update} 
                    onChange={(e) => setCurrentConfig({...currentConfig, enable_living_docs_update: e.target.checked})}
                  />
                  允许更新世界设定 (Living Docs)
                </label>
              </div>

              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">只读文档类型 (readonly_docs)</label>
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginTop: '8px' }}>
                  {availableDocs.map(doc => {
                    const isGlobalUpdateDisabled = !currentConfig.enable_living_docs_update;
                    return (
                      <label key={doc.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: isGlobalUpdateDisabled ? 'not-allowed' : 'pointer', fontSize: '13px', opacity: isGlobalUpdateDisabled ? 0.6 : 1 }}>
                        <input 
                          type="checkbox" 
                          checked={isGlobalUpdateDisabled ? true : (currentConfig.readonly_docs || []).includes(doc.id)}
                          onChange={() => !isGlobalUpdateDisabled && handleCheckboxToggle('readonly_docs', doc.id)}
                          disabled={isGlobalUpdateDisabled}
                        />
                        {doc.label}
                      </label>
                    );
                  })}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--ink-lighter)', marginTop: '4px' }}>
                  {currentConfig.enable_living_docs_update 
                    ? '勾选的活文档将被禁止更新，只允许智能体读取作为参考。'
                    : '全局设定更新已关闭，因此所有活文档默认强制为只读状态。'}
                </div>
              </div>

              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">必需文档类型 (required_docs)</label>
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginTop: '8px' }}>
                  {availableDocs.map(doc => (
                    <label key={doc.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '13px' }}>
                      <input 
                        type="checkbox" 
                        checked={(currentConfig.required_docs || []).includes(doc.id)}
                        onChange={() => handleCheckboxToggle('required_docs', doc.id)}
                      />
                      {doc.label}
                    </label>
                  ))}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--ink-lighter)', marginTop: '4px' }}>勾选的活文档如果缺失，系统会在生成任务前强制尝试提取或生成。</div>
              </div>
              
              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '8px', justifyContent: 'center' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                  <input 
                    type="checkbox" 
                    checked={currentConfig.enable_force_correction} 
                    onChange={(e) => setCurrentConfig({...currentConfig, enable_force_correction: e.target.checked})}
                  />
                  达最大重写次数后强制修正
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                  <input 
                    type="checkbox" 
                    checked={currentConfig.validation_before_editor} 
                    onChange={(e) => setCurrentConfig({...currentConfig, validation_before_editor: e.target.checked})}
                  />
                  在 Editor 审阅前优先进行天道校验
                </label>
              </div>

            </div>
          </div>

          {/* 右侧：智能体提示词展示（只读） */}
          <div className="glass-panel" style={{ padding: '24px', borderRadius: '12px', maxHeight: 'calc(100vh - 120px)', overflowY: 'auto' }}>
            <h3 style={{ marginTop: 0, borderBottom: '1px solid var(--border-muted)', paddingBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>各节点智能体提示词预览</span>
                <span style={{ fontSize: '12px', backgroundColor: 'var(--bg-muted)', padding: '2px 8px', borderRadius: '4px', color: 'var(--ink-light)', fontWeight: 'normal' }}>
                  只读模式
                </span>
              </div>
              <div style={{ display: 'flex', gap: '4px' }}>
                {availableTypes.map(type => (
                  <button
                    key={type}
                    className={`btn ${selectedType === type ? 'btn-primary' : ''}`}
                    style={{ padding: '4px 12px', fontSize: '12px', ...(selectedType !== type ? { backgroundColor: 'var(--bg-muted)', color: 'var(--ink-light)', border: 'none' } : {}) }}
                    onClick={() => setSelectedType(type)}
                  >
                    {type === 'all' ? '全部 (All)' : type}
                  </button>
                ))}
              </div>
            </h3>

            {currentPrompts.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--ink-lighter)', fontSize: '13px' }}>
                未找到该分类的提示词数据。
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginTop: '16px' }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {currentPrompts.map(prompt => {
                    const isSelected = displayAgent && displayAgent.id === prompt.id;
                    return (
                      <button 
                        key={prompt.id} 
                        className={`btn ${isSelected ? 'btn-primary' : ''}`}
                        style={{ padding: '6px 12px', fontSize: '13px', ...(isSelected ? {} : { backgroundColor: 'var(--bg-muted)', color: 'var(--ink)', border: '1px solid var(--border-muted)' }) }}
                        onClick={() => setSelectedAgentId(prompt.id)}
                      >
                        {prompt.name_zh || prompt.name}
                      </button>
                    )
                  })}
                </div>

                {displayAgent && (
                  <div style={{ border: '1px solid var(--border-muted)', borderRadius: '8px', overflow: 'hidden' }}>
                    <div style={{ backgroundColor: 'var(--bg-muted)', padding: '8px 16px', fontWeight: 'bold', fontSize: '14px', borderBottom: '1px solid var(--border-muted)' }}>
                      {displayAgent.name_zh || displayAgent.name} ({displayAgent.type || '未知'})
                    </div>
                    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div className="form-group">
                        <label className="form-label">System Prompt</label>
                        <textarea 
                          className="form-input" 
                          readOnly 
                          rows={Math.max(4, (displayAgent.system_prompt || '').split('\n').length + 1)} 
                          value={displayAgent.system_prompt || ''} 
                          style={{ backgroundColor: 'rgba(0,0,0,0.02)', cursor: 'default', fontFamily: 'monospace', fontSize: '13px', resize: 'vertical' }}
                        />
                      </div>
                      <div className="form-group">
                        <label className="form-label">User Prompt Template</label>
                        <textarea 
                          className="form-input" 
                          readOnly 
                          rows={Math.max(4, (displayAgent.user_prompt_template || '').split('\n').length + 1)} 
                          value={displayAgent.user_prompt_template || ''} 
                          style={{ backgroundColor: 'rgba(0,0,0,0.02)', cursor: 'default', fontFamily: 'monospace', fontSize: '13px', resize: 'vertical' }}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {toast && (
        <div style={{
          position: 'fixed',
          bottom: '20px',
          right: '20px',
          padding: '12px 24px',
          background: toast.type === 'error' ? 'var(--color-red)' : 'var(--color-emerald)',
          color: 'white',
          borderRadius: '8px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '14px'
        }}>
          {toast.type === 'error' ? <AlertCircle size={18} /> : <Save size={18} />}
          {toast.message}
        </div>
      )}
    </div>
  );
}

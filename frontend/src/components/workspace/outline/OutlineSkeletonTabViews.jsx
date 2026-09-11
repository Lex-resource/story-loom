import { Plus, Trash2 } from 'lucide-react';

export function BasicOutlineTab({
  obj,
  isShortOutline,
  creativeContract,
  getField,
  setPreservedField,
  setEditedOutline,
  updateOutlineField,
}) {
  return (
    <div className="outline-section-card animate-fadeIn">
      <div className="outline-grid-2x3">
        <div className="form-group-outline">
          <label className="form-label-outline">书名 (Title)</label>
          <input
            className="form-input-outline"
            value={getField(obj, ['书名', '标题'])}
            onChange={(e) => {
              const next = { ...obj };
              setPreservedField(next, ['书名', '标题'], e.target.value);
              setEditedOutline(JSON.stringify(next, null, 2));
            }}
            placeholder={isShortOutline ? '输入短篇标题...' : '输入书名...'}
          />
        </div>
        <div className="form-group-outline">
          <label className="form-label-outline">类型 (Genre)</label>
          <input
            className="form-input-outline"
            value={obj['类型'] || ''}
            onChange={(e) => updateOutlineField('类型', e.target.value)}
            placeholder={isShortOutline ? '如：知乎短篇、悬疑、甜虐...' : '如：仙侠、玄幻...'}
          />
        </div>
        <div className="form-group-outline">
          <label className="form-label-outline">{isShortOutline ? '故事基调 (Tone)' : '风格 (Style)'}</label>
          <input
            className="form-input-outline"
            value={getField(obj, ['风格', '故事基调'])}
            onChange={(e) => {
              const next = { ...obj };
              setPreservedField(next, ['风格', '故事基调'], e.target.value);
              setEditedOutline(JSON.stringify(next, null, 2));
            }}
            placeholder={isShortOutline ? '如：悬疑、甜虐、爽文、现实向...' : '如：热血、杀伐果断...'}
          />
        </div>
        <div className="form-group-outline">
          <label className="form-label-outline">总章数 (Chapters)</label>
          <input
            className="form-input-outline"
            type="number"
            value={getField(obj, ['总章数', '总章节数'])}
            onChange={(e) => {
              const next = { ...obj };
              setPreservedField(next, ['总章数', '总章节数'], parseInt(e.target.value) || 0);
              setEditedOutline(JSON.stringify(next, null, 2));
            }}
            placeholder={isShortOutline ? '如：3...' : '如：200...'}
          />
        </div>
      </div>
      <div className="form-group-outline">
        <label className="form-label-outline">
          {isShortOutline ? '一句话钩子/简介 (Hook)' : '结局走向 (Ending Direction)'}
        </label>
        <textarea
          className="form-textarea-outline"
          style={{ minHeight: '100px', resize: 'vertical', lineHeight: '1.6' }}
          value={getField(obj, ['结局走向', '简介'])}
          onChange={(e) => {
            const next = { ...obj };
            setPreservedField(next, ['结局走向', '简介'], e.target.value);
            setEditedOutline(JSON.stringify(next, null, 2));
          }}
          placeholder={isShortOutline ? '短篇的核心钩子、冲突和反转承诺...' : '简述故事的最终结局走向与核心收尾内容...'}
        />
      </div>
      {!isShortOutline && (
        <div style={{ marginTop: '18px' }}>
          <div className="outline-card-header" style={{ marginBottom: '10px' }}>
            <span className="info-badge">创作契约</span>
          </div>
          <div className="outline-grid-2x3">
            {[
              ['核心卖点', '读者为什么持续追读这本书'],
              ['主角底层动机', '主角长期行动背后的不可替代欲望'],
              ['终局承诺', '故事最终必须兑现的结果'],
              ['叙事边界', '不能改变的题材、尺度、视角或价值边界'],
            ].map(([field, placeholder]) => (
              <div className="form-group-outline" key={field}>
                <label className="form-label-outline">{field}</label>
                <textarea
                  className="form-textarea-outline"
                  style={{ minHeight: '76px', resize: 'vertical' }}
                  value={creativeContract[field] || ''}
                  onChange={(e) => updateOutlineField('创作契约', { ...creativeContract, [field]: e.target.value })}
                  placeholder={placeholder}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ArcsOutlineTab({ isShortOutline, stagesKey, stages, updateOutlineField }) {
  return (
    <div className="outline-section-card animate-fadeIn">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {stages.map((arc, idx) => (
          <div
            key={idx}
            className="outline-card-inner glow-shadow outline-stage-card"
            style={{ borderLeft: '4px solid var(--vermilion)' }}
          >
            <div className="outline-card-header">
              <span className="info-badge">阶段 {idx + 1}</span>
              <button
                type="button"
                className="event-move-btn"
                style={{ color: 'var(--vermilion)' }}
                onClick={() => {
                  const newStages = [...stages];
                  newStages.splice(idx, 1);
                  updateOutlineField(stagesKey, newStages);
                }}
                title="删除此阶段"
              >
                <Trash2 size={16} />
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
              <div>
                <label className="form-label-outline" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  幕名/卷名
                </label>
                <input
                  className="form-input-outline"
                  style={{ fontSize: '13px', padding: '6px 10px' }}
                  value={arc['卷名'] || arc['幕名'] || ''}
                  onChange={(e) => {
                    const newStages = [...stages];
                    newStages[idx][stagesKey === '卷纲' ? '卷名' : '幕名'] = e.target.value;
                    updateOutlineField(stagesKey, newStages);
                  }}
                  placeholder={isShortOutline ? '例如：开局钩子' : '例如：第一幕 初露峥嵘'}
                />
              </div>
              <div>
                <label className="form-label-outline" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  章节范围
                </label>
                <input
                  className="form-input-outline"
                  style={{ fontSize: '13px', padding: '6px 10px' }}
                  value={arc['章节范围'] || ''}
                  onChange={(e) => {
                    const newStages = [...stages];
                    newStages[idx]['章节范围'] = e.target.value;
                    updateOutlineField(stagesKey, newStages);
                  }}
                  placeholder={isShortOutline ? '例如：1' : '例如：1-15 章'}
                />
              </div>
            </div>
            <div style={{ marginBottom: '8px' }}>
              <label className="form-label-outline" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                {stagesKey === '卷纲' ? '卷目标' : isShortOutline ? '主要推进' : '概要'}
              </label>
              <textarea
                className="form-textarea-outline"
                style={{
                  minHeight: '70px',
                  resize: 'vertical',
                  fontSize: '13px',
                  padding: '8px 10px',
                  lineHeight: '1.5',
                }}
                value={arc['卷目标'] || arc['概要'] || arc['progress'] || ''}
                onChange={(e) => {
                  const newStages = [...stages];
                  const fieldKey =
                    stagesKey === '卷纲' ? '卷目标' : arc['progress'] !== undefined ? 'progress' : '概要';
                  newStages[idx][fieldKey] = e.target.value;
                  updateOutlineField(stagesKey, newStages);
                }}
                placeholder={isShortOutline ? '这一阶段的钩子、信息增量和反转推进...' : '本卷的起承转合核心剧情...'}
              />
            </div>
            <div>
              <label className="form-label-outline" style={{ fontSize: '11px', color: 'var(--vermilion)' }}>
                {stagesKey === '卷纲' ? '主要对手与冲突' : '核心冲突'}
              </label>
              <textarea
                className="form-textarea-outline"
                style={{
                  minHeight: '70px',
                  resize: 'vertical',
                  fontSize: '13px',
                  padding: '8px 10px',
                  lineHeight: '1.5',
                }}
                value={arc['主要对手'] || arc['核心冲突'] || ''}
                onChange={(e) => {
                  const newStages = [...stages];
                  newStages[idx][stagesKey === '卷纲' ? '主要对手' : '核心冲突'] = e.target.value;
                  updateOutlineField(stagesKey, newStages);
                }}
                placeholder={
                  isShortOutline ? '本阶段的主要冲突、爽点、反转或情绪爆点...' : '本阶段的主要矛盾与高潮对抗...'
                }
              />
            </div>
            {stagesKey === '卷纲' && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
                  gap: '10px',
                  marginTop: '10px',
                }}
              >
                {[
                  ['升级变化', '能力、资源或关系发生什么变化'],
                  ['阶段兑现', '本卷向读者兑现什么期待'],
                  ['失败代价', '主角失败会失去什么'],
                ].map(([field, placeholder]) => (
                  <div key={field}>
                    <label className="form-label-outline" style={{ fontSize: '11px' }}>
                      {field}
                    </label>
                    <textarea
                      className="form-textarea-outline"
                      style={{ minHeight: '64px', fontSize: '12px' }}
                      value={arc[field] || ''}
                      onChange={(e) => {
                        const newStages = [...stages];
                        newStages[idx][field] = e.target.value;
                        updateOutlineField(stagesKey, newStages);
                      }}
                      placeholder={placeholder}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        <button
          type="button"
          className="btn btn-secondary"
          style={{
            alignSelf: 'flex-start',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '6px 12px',
            fontSize: '12px',
          }}
          onClick={() => {
            const newStages = [...stages];
            newStages.push(
              isShortOutline
                ? { 幕名: '', 章节范围: '', progress: '', 核心冲突: '' }
                : stagesKey === '卷纲'
                  ? {
                      卷名: '',
                      章节范围: '',
                      卷目标: '',
                      主要对手: '',
                      升级变化: '',
                      阶段兑现: '',
                      失败代价: '',
                      核心事件: [],
                    }
                  : { 幕名: '', 章节范围: '', 概要: '', 核心冲突: '' },
            );
            updateOutlineField(stagesKey, newStages);
          }}
        >
          <Plus size={14} /> 添加{stagesKey === '卷纲' ? '卷' : '故事阶段'}
        </button>
      </div>
    </div>
  );
}

export function CharactersOutlineTab({ isShortOutline, characters, updateOutlineField }) {
  return (
    <div className="outline-section-card animate-fadeIn">
      <div className="character-grid-premium">
        {characters.map((char, idx) => {
          const roleType = char['角色'] || '';
          const isProtagonist = roleType.includes('主') || roleType.includes('男一') || roleType.includes('女一');
          const isAntagonist = roleType.includes('反') || roleType.includes('敌') || roleType.includes('魔');
          const badgeClass = isProtagonist ? 'protagonist' : isAntagonist ? 'antagonist' : 'supporting';
          return (
            <div key={idx} className="character-card-premium">
              <div style={{ display: 'flex', gap: '8px', marginBottom: '4px' }}>
                <input
                  className="form-input-outline"
                  placeholder="姓名"
                  value={char['姓名'] || char['名字'] || ''}
                  onChange={(e) => {
                    const newChars = [...characters];
                    const nameKey = char['名字'] !== undefined ? '名字' : '姓名';
                    newChars[idx][nameKey] = e.target.value;
                    updateOutlineField('主要人物', newChars);
                  }}
                  style={{ flex: 1, fontSize: '14px', fontWeight: 'bold', padding: '6px 10px' }}
                />
                <input
                  className="form-input-outline"
                  placeholder="类型(主角/配角)"
                  value={char['角色'] || ''}
                  onChange={(e) => {
                    const newChars = [...characters];
                    newChars[idx]['角色'] = e.target.value;
                    updateOutlineField('主要人物', newChars);
                  }}
                  style={{ width: '100px', fontSize: '12px', padding: '4px 8px', textAlign: 'center' }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className={`character-badge ${badgeClass}`}>{char['角色'] || '配角'}</span>
              </div>
              <textarea
                className="form-textarea-outline"
                placeholder="主要人物特征、来历、金手指与性格简述..."
                style={{
                  minHeight: '60px',
                  resize: 'vertical',
                  fontSize: '12px',
                  padding: '8px 10px',
                  lineHeight: '1.5',
                }}
                value={char['简述'] || char['动机'] || ''}
                onChange={(e) => {
                  const newChars = [...characters];
                  const descKey = char['动机'] !== undefined ? '动机' : '简述';
                  newChars[idx][descKey] = e.target.value;
                  updateOutlineField('主要人物', newChars);
                }}
              />
              <button
                type="button"
                className="event-move-btn"
                style={{ position: 'absolute', bottom: '12px', right: '12px' }}
                onClick={() => {
                  const newChars = [...characters];
                  newChars.splice(idx, 1);
                  updateOutlineField('主要人物', newChars);
                }}
                title="删除角色"
              >
                <Trash2 size={14} />
              </button>
            </div>
          );
        })}
      </div>
      <button
        type="button"
        className="btn btn-secondary"
        style={{
          alignSelf: 'flex-start',
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          padding: '6px 12px',
          fontSize: '12px',
          marginTop: '8px',
        }}
        onClick={() => {
          const newChars = [...characters];
          newChars.push(isShortOutline ? { 名字: '', 角色: '配角', 动机: '' } : { 姓名: '', 角色: '配角', 简述: '' });
          updateOutlineField('主要人物', newChars);
        }}
      >
        <Plus size={14} /> 添加角色
      </button>
    </div>
  );
}

export function WorldOutlineTab({ obj, updateOutlineField }) {
  return (
    <div className="outline-section-card animate-fadeIn">
      {Array.isArray(obj['世界设定']) ? (
        <div className="outline-list-stack">
          {obj['世界设定'].map((setting, idx) => (
            <div key={idx} className="outline-card-inner outline-world-rule-card">
              <div className="outline-card-header">
                <div className="form-group-outline" style={{ flex: 1 }}>
                  <label className="form-label-outline">设定名称</label>
                  <input
                    className="form-input-outline"
                    value={setting['名称'] || ''}
                    onChange={(e) => {
                      const nextSettings = [...obj['世界设定']];
                      nextSettings[idx] = { ...nextSettings[idx], 名称: e.target.value };
                      updateOutlineField('世界设定', nextSettings);
                    }}
                    placeholder="规则、地点、组织或限制..."
                  />
                </div>
                <button
                  type="button"
                  className="event-move-btn"
                  style={{ color: 'var(--vermilion)' }}
                  onClick={() => {
                    const nextSettings = [...obj['世界设定']];
                    nextSettings.splice(idx, 1);
                    updateOutlineField('世界设定', nextSettings);
                  }}
                  title="删除设定"
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="outline-grid-2x3">
                <div className="form-group-outline">
                  <label className="form-label-outline">类型</label>
                  <input
                    className="form-input-outline"
                    value={setting['rule_type'] || ''}
                    onChange={(e) => {
                      const nextSettings = [...obj['世界设定']];
                      nextSettings[idx] = { ...nextSettings[idx], rule_type: e.target.value };
                      updateOutlineField('世界设定', nextSettings);
                    }}
                    placeholder="rule/location/faction..."
                  />
                </div>
              </div>
              <div className="form-group-outline">
                <label className="form-label-outline">描述</label>
                <textarea
                  className="form-textarea-outline"
                  style={{ minHeight: '80px', resize: 'vertical', lineHeight: '1.6' }}
                  value={setting['描述'] || ''}
                  onChange={(e) => {
                    const nextSettings = [...obj['世界设定']];
                    nextSettings[idx] = { ...nextSettings[idx], 描述: e.target.value };
                    updateOutlineField('世界设定', nextSettings);
                  }}
                  placeholder="短篇中真正会影响剧情的设定..."
                />
              </div>
            </div>
          ))}
          <button
            type="button"
            className="btn btn-secondary"
            style={{
              alignSelf: 'flex-start',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '6px 12px',
              fontSize: '12px',
            }}
            onClick={() => {
              const nextSettings = [...obj['世界设定'], { 名称: '', 描述: '', rule_type: 'rule' }];
              updateOutlineField('世界设定', nextSettings);
            }}
          >
            <Plus size={14} /> 添加短篇设定
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div className="form-group-outline">
            <label className="form-label-outline">核心规则 (Core Rules)</label>
            <textarea
              className="form-textarea-outline"
              style={{ minHeight: '90px', resize: 'vertical', lineHeight: '1.6' }}
              value={obj['世界设定']?.['核心规则'] || ''}
              onChange={(e) => {
                const newSettings = { ...(obj['世界设定'] || {}) };
                newSettings['核心规则'] = e.target.value;
                updateOutlineField('世界设定', newSettings);
              }}
              placeholder="世界观核心设定或修行规则上限..."
            />
          </div>
          <div className="form-group-outline">
            <label className="form-label-outline">背景设定 (World Background)</label>
            <textarea
              className="form-textarea-outline"
              style={{ minHeight: '90px', resize: 'vertical', lineHeight: '1.6' }}
              value={obj['世界设定']?.['背景设定'] || ''}
              onChange={(e) => {
                const newSettings = { ...(obj['世界设定'] || {}) };
                newSettings['背景设定'] = e.target.value;
                updateOutlineField('世界设定', newSettings);
              }}
              placeholder="世界地理、大势版图、门派分立等背景设定..."
            />
          </div>
          <div className="form-group-outline">
            <label className="form-label-outline">体系/特殊机制 (Mechanism)</label>
            <textarea
              className="form-textarea-outline"
              style={{ minHeight: '90px', resize: 'vertical', lineHeight: '1.6' }}
              value={obj['体系/特殊机制'] || obj['特殊机制'] || obj['特殊设定'] || ''}
              onChange={(e) => {
                const mechKey = obj['特殊机制'] ? '特殊机制' : obj['特殊设定'] ? '特殊设定' : '体系/特殊机制';
                updateOutlineField(mechKey, e.target.value);
              }}
              placeholder="升级境界划分、战力指数或其它特殊机制..."
            />
          </div>
        </div>
      )}
    </div>
  );
}

export function ForeshadowingOutlineTab({ isShortOutline, foreshadowingKey, foreshadowings, updateOutlineField }) {
  return (
    <div className="outline-section-card animate-fadeIn">
      <div className="foreshadowing-grid">
        {foreshadowings.map((fb, idx) => (
          <div key={idx} className="foreshadowing-card-premium">
            <div className="outline-card-header">
              <input
                className="form-input-outline"
                value={fb['伏笔名称'] || ''}
                onChange={(e) => {
                  const newFb = [...foreshadowings];
                  newFb[idx]['伏笔名称'] = e.target.value;
                  updateOutlineField(foreshadowingKey, newFb);
                }}
                placeholder="伏笔名称"
                style={{ fontSize: '13px', fontWeight: 600 }}
              />
              <button
                type="button"
                className="event-move-btn"
                style={{ color: 'var(--vermilion)', flex: '0 0 auto' }}
                onClick={() => {
                  const newFb = [...foreshadowings];
                  newFb.splice(idx, 1);
                  updateOutlineField(foreshadowingKey, newFb);
                }}
                title="删除伏笔"
              >
                <Trash2 size={14} />
              </button>
            </div>
            <div className="foreshadowing-chapters">
              <span>埋：第 </span>
              <input
                className="form-input-outline"
                type="number"
                value={fb['埋设章节'] || fb['出现章节'] || fb['chapter'] || 0}
                onChange={(e) => {
                  const newFb = [...foreshadowings];
                  const chapterKey = fb['chapter'] !== undefined ? 'chapter' : '埋设章节';
                  newFb[idx][chapterKey] = parseInt(e.target.value) || 0;
                  updateOutlineField(foreshadowingKey, newFb);
                }}
                style={{ width: '45px', padding: '2px 4px', fontSize: '11px', textAlign: 'center', background: '#fff' }}
              />
              <span> 章</span>
              <span className="foreshadowing-arrow">➜</span>
              <span>收：第 </span>
              <input
                className="form-input-outline"
                type="number"
                value={fb['收回章节'] || fb['解开章节'] || fb['resolved_chapter'] || 0}
                onChange={(e) => {
                  const newFb = [...foreshadowings];
                  const resolvedKey = fb['resolved_chapter'] !== undefined ? 'resolved_chapter' : '收回章节';
                  newFb[idx][resolvedKey] = parseInt(e.target.value) || 0;
                  updateOutlineField(foreshadowingKey, newFb);
                }}
                style={{ width: '45px', padding: '2px 4px', fontSize: '11px', textAlign: 'center', background: '#fff' }}
              />
              <span> 章</span>
            </div>
            <textarea
              className="form-textarea-outline"
              placeholder="伏笔触发原因与收回时的反转剧情细节..."
              style={{
                minHeight: '70px',
                resize: 'vertical',
                fontSize: '12px',
                padding: '8px 10px',
                lineHeight: '1.5',
              }}
              value={fb['描述'] || fb['伏笔'] || fb['description'] || ''}
              onChange={(e) => {
                const newFb = [...foreshadowings];
                const descKey = fb['description'] !== undefined ? 'description' : '描述';
                newFb[idx][descKey] = e.target.value;
                updateOutlineField(foreshadowingKey, newFb);
              }}
            />
          </div>
        ))}
      </div>
      <button
        type="button"
        className="btn btn-secondary"
        style={{
          alignSelf: 'flex-start',
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          padding: '6px 12px',
          fontSize: '12px',
          marginTop: '8px',
        }}
        onClick={() => {
          const newFb = [...foreshadowings];
          newFb.push(
            isShortOutline
              ? { 伏笔名称: '', chapter: 1, resolved_chapter: 1, description: '' }
              : { 埋设章节: 0, 收回章节: 0, 描述: '' },
          );
          updateOutlineField(foreshadowingKey, newFb);
        }}
      >
        <Plus size={14} /> 添加伏笔
      </button>
    </div>
  );
}

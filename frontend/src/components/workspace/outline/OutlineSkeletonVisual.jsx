
import { BasicOutlineTab, ArcsOutlineTab, CharactersOutlineTab, WorldOutlineTab, ForeshadowingOutlineTab } from './OutlineSkeletonTabViews';
export default function OutlineSkeletonVisual({
  outlineObj, activeProject, outlineTab, setOutlineTab, skeletonScrollRef, shortOutlineKeys,
  getForeshadowingKey, normalizeList, getField, setPreservedField, updateOutlineField,
  setEditedOutline,
}) {
  const renderSkeletonVisual = () => {
    const obj = outlineObj;
    const isShortOutline = activeProject?.novel_format === 'zhihu_short' || shortOutlineKeys.some((key) => obj[key] !== undefined);
    const foreshadowingKey = getForeshadowingKey(obj);
    const foreshadowings = normalizeList(obj[foreshadowingKey]);
    const stagesKey = !isShortOutline && Array.isArray(obj["卷纲"]) ? "卷纲" : "故事阶段";
    const stages = normalizeList(obj[stagesKey]);
    const characters = normalizeList(obj["主要人物"]);
    const creativeContract = !isShortOutline && typeof obj["创作契约"] === 'object' && obj["创作契约"]
      ? obj["创作契约"]
      : {};
  
    return (
      <div ref={skeletonScrollRef} className="parchment-scroll" style={{ flexGrow: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', padding: '16px 20px', borderRadius: '12px' }}>
        {/* Tab Switcher */}
        <div className="outline-tabs-container">
          <button
            type="button"
            className={`outline-tab-btn ${outlineTab === 'basic' ? 'active' : ''}`}
            onClick={() => setOutlineTab('basic')}
          >
            📋 基本设定
          </button>
          <button
            type="button"
            className={`outline-tab-btn ${outlineTab === 'arcs' ? 'active' : ''}`}
            onClick={() => setOutlineTab('arcs')}
          >
            📜 {stagesKey === '卷纲' ? '卷纲' : '故事阶段'} ({stages.length})
          </button>
          <button
            type="button"
            className={`outline-tab-btn ${outlineTab === 'characters' ? 'active' : ''}`}
            onClick={() => setOutlineTab('characters')}
          >
            👤 主要人物 ({characters.length})
          </button>
          <button
            type="button"
            className={`outline-tab-btn ${outlineTab === 'world' ? 'active' : ''}`}
            onClick={() => setOutlineTab('world')}
          >
            ☯ {isShortOutline ? '短篇设定' : '世界观与体系'}
          </button>
          <button
            type="button"
            className={`outline-tab-btn ${outlineTab === 'foreshadowing' ? 'active' : ''}`}
            onClick={() => setOutlineTab('foreshadowing')}
          >
            🔍 伏笔埋设 ({foreshadowings.length})
          </button>
        </div>
  
        {/* Tab Contents */}
{outlineTab === 'basic' && <BasicOutlineTab obj={obj} isShortOutline={isShortOutline} creativeContract={creativeContract} getField={getField} setPreservedField={setPreservedField} setEditedOutline={setEditedOutline} updateOutlineField={updateOutlineField} />}
  
{outlineTab === 'arcs' && <ArcsOutlineTab isShortOutline={isShortOutline} stagesKey={stagesKey} stages={stages} updateOutlineField={updateOutlineField} />}
  
{outlineTab === 'characters' && <CharactersOutlineTab isShortOutline={isShortOutline} characters={characters} updateOutlineField={updateOutlineField} />}
  
{outlineTab === 'world' && <WorldOutlineTab obj={obj} updateOutlineField={updateOutlineField} />}
  
{outlineTab === 'foreshadowing' && <ForeshadowingOutlineTab isShortOutline={isShortOutline} foreshadowingKey={foreshadowingKey} foreshadowings={foreshadowings} updateOutlineField={updateOutlineField} />}
      </div>
    );
  };

  return renderSkeletonVisual();
}

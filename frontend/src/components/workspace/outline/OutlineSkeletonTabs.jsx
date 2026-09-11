import {
  BasicOutlineTab,
  ArcsOutlineTab,
  CharactersOutlineTab,
  WorldOutlineTab,
  ForeshadowingOutlineTab,
} from './OutlineSkeletonTabViews';

export default function OutlineSkeletonTabs({
  outlineTab,
  setOutlineTab,
  isShortOutline,
  stagesKey,
  stages,
  characters,
  obj,
  creativeContract,
  foreshadowingKey,
  foreshadowings,
  getField,
  setPreservedField,
  setEditedOutline,
  updateOutlineField,
}) {
  return (
    <>
      <div className="outline-tabs-container">
        {[
          ['basic', '📋 基本设定'],
          ['arcs', `📜 ${stagesKey === '卷纲' ? '卷纲' : '故事阶段'} (${stages.length})`],
          ['characters', `👤 主要人物 (${characters.length})`],
          ['world', `☯ ${isShortOutline ? '短篇设定' : '世界观与体系'}`],
          ['foreshadowing', `🔍 伏笔埋设 (${foreshadowings.length})`],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`outline-tab-btn ${outlineTab === key ? 'active' : ''}`}
            onClick={() => setOutlineTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {outlineTab === 'basic' && (
        <BasicOutlineTab
          obj={obj}
          isShortOutline={isShortOutline}
          creativeContract={creativeContract}
          getField={getField}
          setPreservedField={setPreservedField}
          setEditedOutline={setEditedOutline}
          updateOutlineField={updateOutlineField}
        />
      )}
      {outlineTab === 'arcs' && (
        <ArcsOutlineTab
          isShortOutline={isShortOutline}
          stagesKey={stagesKey}
          stages={stages}
          updateOutlineField={updateOutlineField}
        />
      )}
      {outlineTab === 'characters' && (
        <CharactersOutlineTab
          isShortOutline={isShortOutline}
          characters={characters}
          updateOutlineField={updateOutlineField}
        />
      )}
      {outlineTab === 'world' && <WorldOutlineTab obj={obj} updateOutlineField={updateOutlineField} />}
      {outlineTab === 'foreshadowing' && (
        <ForeshadowingOutlineTab
          isShortOutline={isShortOutline}
          foreshadowingKey={foreshadowingKey}
          foreshadowings={foreshadowings}
          updateOutlineField={updateOutlineField}
        />
      )}
    </>
  );
}

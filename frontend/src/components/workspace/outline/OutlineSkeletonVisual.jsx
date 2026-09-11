import OutlineSkeletonTabs from './OutlineSkeletonTabs';

export default function OutlineSkeletonVisual({
  outlineObj,
  activeProject,
  outlineTab,
  setOutlineTab,
  skeletonScrollRef,
  shortOutlineKeys,
  getForeshadowingKey,
  normalizeList,
  getField,
  setPreservedField,
  updateOutlineField,
  setEditedOutline,
}) {
  const obj = outlineObj;
  const isShortOutline =
    activeProject?.novel_format === 'zhihu_short' || shortOutlineKeys.some((key) => obj[key] !== undefined);
  const foreshadowingKey = getForeshadowingKey(obj);
  const foreshadowings = normalizeList(obj[foreshadowingKey]);
  const stagesKey = !isShortOutline && Array.isArray(obj['卷纲']) ? '卷纲' : '故事阶段';
  const stages = normalizeList(obj[stagesKey]);
  const characters = normalizeList(obj['主要人物']);
  const creativeContract =
    !isShortOutline && typeof obj['创作契约'] === 'object' && obj['创作契约'] ? obj['创作契约'] : {};

  return (
    <div
      ref={skeletonScrollRef}
      className="parchment-scroll"
      style={{
        flexGrow: 1,
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        padding: '16px 20px',
        borderRadius: '12px',
      }}
    >
      <OutlineSkeletonTabs
        outlineTab={outlineTab}
        setOutlineTab={setOutlineTab}
        isShortOutline={isShortOutline}
        stagesKey={stagesKey}
        stages={stages}
        characters={characters}
        obj={obj}
        creativeContract={creativeContract}
        foreshadowingKey={foreshadowingKey}
        foreshadowings={foreshadowings}
        getField={getField}
        setPreservedField={setPreservedField}
        setEditedOutline={setEditedOutline}
        updateOutlineField={updateOutlineField}
      />
    </div>
  );
}

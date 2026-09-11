import React, { useMemo } from 'react';
import { Loader2, ArrowUp, ArrowDown, Trash2, Plus, RefreshCw } from 'lucide-react';
import {
  moveKeyEvent as moveOutlineKeyEvent,
  normalizeOutlineText,
  parseOutlineText,
  updateOutlineJson,
} from './outline/outlineModel';
import OutlineSkeletonVisual from './outline/OutlineSkeletonVisual';
import { outlineApi } from '../../services/novelApi';
import { createRequestGuard } from '../../utils/requestLifecycle';

export default function WorkspaceOutline({
  workspaceStep,
  outlineMode,
  setOutlineMode,
  editedOutline,
  setEditedOutline,
  activeChapter,
  isOutlineStreaming,
  isSkeletonStreaming,
  activeProject,
  handleDeleteChapter,
  handleRewriteOutline,
  actionLoading,
  isGenerating,
}) {
  const isSkeleton = workspaceStep === 'structure' || !activeChapter;
  const [fetchingSkeleton, setFetchingSkeleton] = React.useState(false);
  const outlineRequestGuardRef = React.useRef(null);
  if (!outlineRequestGuardRef.current) outlineRequestGuardRef.current = createRequestGuard();
  const [outlineTab, setOutlineTab] = React.useState('basic'); // 'basic' | 'arcs' | 'characters' | 'world' | 'foreshadowing'
  const skeletonScrollRef = React.useRef(null);
  const shortOutlineKeys = ['标题', '简介', '总章节数', '关键伏笔', '故事基调'];
  const activeProjectId = activeProject?.id;
  const activeProjectOutline = activeProject?.outline;

  const pickKey = (obj, keys, fallback) => {
    for (const key of keys) {
      if (obj && obj[key] !== undefined) return key;
    }
    return fallback || keys[0];
  };

  const getField = (obj, keys, fallback = '') => {
    const key = pickKey(obj, keys);
    return obj?.[key] ?? fallback;
  };

  const setPreservedField = (obj, keys, value) => {
    const key = pickKey(obj, keys);
    obj[key] = value;
  };

  const getForeshadowingKey = (obj) => pickKey(obj, ['关键伏笔', '主要伏笔', '核心伏笔'], '关键伏笔');
  const normalizeList = (value) => (Array.isArray(value) ? value : []);

  const moveKeyEvent = (idx, direction) => {
    try {
      setEditedOutline(moveOutlineKeyEvent(editedOutline, idx, direction));
    } catch (e) {
      console.error('Failed to move key event:', e);
    }
  };

  // Initialize editedOutline with skeleton if we are in skeleton mode and it's empty
  React.useEffect(() => {
    outlineRequestGuardRef.current.cancel();
    if (isSkeleton && !isSkeletonStreaming && !editedOutline) {
      if (activeProjectOutline) {
        setEditedOutline(
          typeof activeProjectOutline === 'string'
            ? activeProjectOutline
            : JSON.stringify(activeProjectOutline, null, 2),
        );
      } else if (activeProjectId && !fetchingSkeleton) {
        // Fetch outline from backend if not present in activeProject object
        const request = outlineRequestGuardRef.current.start();
        setFetchingSkeleton(true);
        outlineApi
          .get(activeProjectId, { signal: request.signal })
          .then((data) => {
            if (request.isCurrent() && data.outline) {
              setEditedOutline(typeof data.outline === 'string' ? data.outline : JSON.stringify(data.outline, null, 2));
            }
          })
          .catch((e) => {
            if (request.isCurrent() && e.name !== 'AbortError') console.error('Failed to fetch outline:', e);
          })
          .finally(() => {
            if (request.isCurrent()) setFetchingSkeleton(false);
          });
      }
    }
    return () => outlineRequestGuardRef.current.cancel();
  }, [isSkeleton, isSkeletonStreaming, editedOutline, activeProjectId, activeProjectOutline, setEditedOutline]);

  // F-19: Memoize JSON.parse so it only re-runs when editedOutline changes, not on every render
  const { outlineObj, parseError } = useMemo(() => {
    return parseOutlineText(editedOutline);
  }, [editedOutline]);

  React.useEffect(() => {
    // Automatically clean backticks and switch back to visual mode when streaming completes if the JSON is valid
    if (!isOutlineStreaming && editedOutline) {
      const cleaned = normalizeOutlineText(editedOutline);
      const hasBackticks = cleaned !== editedOutline.trim();

      let isParseable = false;
      try {
        if (cleaned) JSON.parse(cleaned);
        isParseable = true;
      } catch {
        // Leave visual mode unchanged until the streamed JSON is complete.
      }

      if (isParseable) {
        if (hasBackticks) {
          setEditedOutline(cleaned);
        }
        setOutlineMode('visual');
      }
    }
  }, [isOutlineStreaming, editedOutline, setOutlineMode, setEditedOutline]);

  React.useEffect(() => {
    if (skeletonScrollRef.current) {
      skeletonScrollRef.current.scrollTop = 0;
    }
  }, [outlineTab]);

  if (workspaceStep !== 'planner' && workspaceStep !== 'structure') return null;
  // If no chapter and no streaming and no content, hide it.
  // But if there is content (editedOutline or activeProject.outline) or it's streaming or we are fetching, show it.
  if (
    isSkeleton &&
    !isOutlineStreaming &&
    !editedOutline &&
    !isSkeletonStreaming &&
    !activeProject?.outline &&
    !fetchingSkeleton
  )
    return null;

  const updateOutlineField = (field, value) => {
    try {
      setEditedOutline(
        updateOutlineJson(editedOutline, (outline) => {
          outline[field] = value;
        }),
      );
    } catch (e) {
      console.error('Failed to update outline field:', e);
    }
  };

  const updateKeyEvent = (idx, value) => {
    try {
      setEditedOutline(
        updateOutlineJson(editedOutline, (outline) => {
          const events = [...(outline.key_events || [])];
          events[idx] = value;
          outline.key_events = events;
        }),
      );
    } catch (e) {
      console.error('Failed to update key event:', e);
    }
  };

  const addKeyEvent = () => {
    try {
      setEditedOutline(
        updateOutlineJson(editedOutline, (outline) => {
          outline.key_events = [...(outline.key_events || []), ''];
        }),
      );
    } catch (e) {
      console.error('Failed to add key event:', e);
    }
  };

  const removeKeyEvent = (idx) => {
    try {
      setEditedOutline(
        updateOutlineJson(editedOutline, (outline) => {
          const events = [...(outline.key_events || [])];
          events.splice(idx, 1);
          outline.key_events = events;
        }),
      );
    } catch (e) {
      console.error('Failed to remove key event:', e);
    }
  };

  const renderSkeletonVisual = () => (
    <OutlineSkeletonVisual
      outlineObj={outlineObj}
      activeProject={activeProject}
      outlineTab={outlineTab}
      setOutlineTab={setOutlineTab}
      skeletonScrollRef={skeletonScrollRef}
      shortOutlineKeys={shortOutlineKeys}
      getForeshadowingKey={getForeshadowingKey}
      normalizeList={normalizeList}
      getField={getField}
      setPreservedField={setPreservedField}
      updateOutlineField={updateOutlineField}
      setEditedOutline={setEditedOutline}
    />
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0, gap: '12px' }}>
      <div
        className="outline-toolbar"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
      >
        <div className="outline-toolbar-title" style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
          <span>
            {isSkeleton ? (isSkeletonStreaming ? '全书大纲生成中…' : '全书骨架大纲设定') : '章节大纲策划卷轴'}
          </span>
          {isOutlineStreaming && (
            <span className="warning-badge warning pulsing-border" style={{ margin: 0, fontSize: '11px' }}>
              <Loader2 className="animate-spin" size={12} style={{ marginRight: 4 }} />
              {isSkeletonStreaming ? '骨架流式生成中…' : '大纲流式生成中…'}
            </span>
          )}
        </div>
        <div className="outline-toolbar-actions" style={{ display: 'flex', gap: '8px' }}>
          <button
            className={`btn ${outlineMode === 'visual' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '3px 10px', fontSize: '12px' }}
            onClick={() => setOutlineMode('visual')}
          >
            可视化大纲
          </button>
          <button
            className={`btn ${outlineMode === 'json' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '3px 10px', fontSize: '12px' }}
            onClick={() => setOutlineMode('json')}
          >
            JSON 配置
          </button>
          {isSkeleton && handleRewriteOutline && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleRewriteOutline}
              disabled={actionLoading || isGenerating || isOutlineStreaming}
              style={{ padding: '3px 10px', fontSize: '12px' }}
              title={isGenerating ? '请先暂停创作，再重新规划全书大纲' : '根据当前大纲重新规划全书结构'}
            >
              {actionLoading ? <Loader2 className="animate-spin" size={13} /> : <RefreshCw size={13} />}
              重新大纲
            </button>
          )}
          {!isSkeleton &&
            activeChapter &&
            !(isGenerating && activeProject?.current_chapter === activeChapter?.chapter_index) &&
            handleDeleteChapter && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  if (window.confirm(`确定要删除第 ${activeChapter.chapter_index} 章吗？删除后不可恢复。`)) {
                    handleDeleteChapter(activeChapter.chapter_index);
                  }
                }}
                style={{
                  padding: '3px 10px',
                  fontSize: '12px',
                  color: '#ef4444',
                  borderColor: 'rgba(239, 68, 68, 0.3)',
                  background: 'rgba(239, 68, 68, 0.05)',
                }}
                title="删除此章节"
              >
                删除本章
              </button>
            )}
        </div>
      </div>

      {outlineMode === 'json' || parseError || isOutlineStreaming ? (
        <div style={{ display: 'flex', flexDirection: 'column', flexGrow: 1, gap: '8px' }}>
          {parseError && !isOutlineStreaming && (
            <div className="alert alert-warning" style={{ margin: 0, padding: '6px 12px', fontSize: '12px' }}>
              警告：JSON 格式解析有误，已自动降级为原文编辑。
            </div>
          )}
          <textarea
            className="editor-textarea"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
              background: 'rgba(0,0,0,0.3)',
              border: '1px solid var(--border-muted)',
              borderRadius: '8px',
              flexGrow: 1,
            }}
            value={editedOutline}
            onChange={(e) => setEditedOutline(e.target.value)}
            readOnly={isOutlineStreaming}
            placeholder={isOutlineStreaming ? '策划智能体正在流式写入大纲 JSON...' : ''}
          />
        </div>
      ) : isSkeleton ? (
        renderSkeletonVisual()
      ) : (
        <div
          className="parchment-scroll"
          style={{
            flexGrow: 1,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            padding: '20px',
            borderRadius: '12px',
          }}
        >
          <div className="outline-section-card animate-fadeIn">
            <div className="form-group-outline">
              <label
                className="form-label-outline"
                style={{
                  fontSize: '15px',
                  color: 'var(--vermilion)',
                  borderBottom: '1px solid var(--border)',
                  paddingBottom: '6px',
                }}
              >
                第 {activeChapter?.chapter_index} 章 章节大纲
              </label>
            </div>

            <div className="form-group-outline">
              <label className="form-label-outline">章节标题 (Chapter Title)</label>
              <input
                className="form-input-outline"
                value={outlineObj.title || ''}
                onChange={(e) => updateOutlineField('title', e.target.value)}
                placeholder="输入本章标题..."
                style={{ fontSize: '15px', fontWeight: 'bold' }}
              />
            </div>

            <div className="form-group-outline">
              <label className="form-label-outline">本章大局概要 (Summary)</label>
              <textarea
                className="form-textarea-outline"
                style={{ minHeight: '80px', resize: 'vertical', fontSize: '14px', lineHeight: '1.6', width: '100%' }}
                value={outlineObj.summary || ''}
                onChange={(e) => updateOutlineField('summary', e.target.value)}
                placeholder="简述本章节的核心目标、剧情发展和要达到的核心转折..."
              />
            </div>

            <div className="form-group-outline">
              <div
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}
              >
                <label className="form-label-outline">核心事件流与冲突递进 (Key Events Timeline)</label>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '4px 10px', fontSize: '11px' }}
                  onClick={addKeyEvent}
                >
                  <Plus size={12} /> 添加剧情节点
                </button>
              </div>

              {!outlineObj.key_events || outlineObj.key_events.length === 0 ? (
                <div
                  style={{
                    padding: '20px',
                    textAlign: 'center',
                    background: 'var(--cloud)',
                    borderRadius: '8px',
                    border: '1px dashed var(--border)',
                  }}
                >
                  <p className="text-secondary text-xs" style={{ margin: 0 }}>
                    暂无剧情节点事件流，请点击右上方按钮进行添加
                  </p>
                </div>
              ) : (
                <div className="event-timeline">
                  {outlineObj.key_events.map((event, idx) => (
                    <div key={idx} className="event-timeline-item">
                      <div className="event-number-badge">{String(idx + 1).padStart(2, '0')}</div>

                      <div className="event-timeline-card">
                        <div style={{ flexGrow: 1 }}>
                          <textarea
                            className="form-textarea-outline"
                            style={{
                              resize: 'vertical',
                              minHeight: '50px',
                              fontSize: '13px',
                              lineHeight: '1.5',
                              width: '100%',
                              border: 'none',
                              padding: 0,
                              background: 'transparent',
                            }}
                            value={event}
                            onChange={(e) => updateKeyEvent(idx, e.target.value)}
                            placeholder="描述该剧情事件节点细节..."
                          />
                        </div>

                        <div className="event-action-buttons">
                          <button
                            type="button"
                            className="event-move-btn"
                            onClick={() => moveKeyEvent(idx, 'up')}
                            disabled={idx === 0}
                            title="移至上方"
                          >
                            <ArrowUp size={14} />
                          </button>
                          <button
                            type="button"
                            className="event-move-btn"
                            onClick={() => moveKeyEvent(idx, 'down')}
                            disabled={idx === outlineObj.key_events.length - 1}
                            title="移至下方"
                          >
                            <ArrowDown size={14} />
                          </button>
                          <button
                            type="button"
                            className="event-move-btn"
                            style={{ color: 'var(--vermilion)' }}
                            onClick={() => removeKeyEvent(idx)}
                            title="删除节点"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

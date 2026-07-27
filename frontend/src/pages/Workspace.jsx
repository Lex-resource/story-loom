import { useState, useEffect, useRef } from 'react';
import {
  Trash2,
  Save,
  Loader2,
  AlertTriangle,
  Check,
  RefreshCw,
  HelpCircle,
  List,
  PenLine
} from 'lucide-react';
import ConsoleLogs from '../components/ConsoleLogs';

import WorkspaceSidebar from '../components/workspace/WorkspaceSidebar';
import WorkspaceOutline from '../components/workspace/WorkspaceOutline';
import WorkspaceEditor from '../components/workspace/WorkspaceEditor';
import WorkspaceValidator from '../components/workspace/WorkspaceValidator';


export default function Workspace({
  API_BASE,
  activeProject,
  activeProjectStatus,
  chapters,
  activeChapter,
  workspaceStep,
  setWorkspaceStep,
  editedOutline,
  setEditedOutline,
  editedTitle,
  setEditedTitle,
  editedContent,
  setEditedContent,
  savingOutline,
  savingContent,
  writerSubTab,
  setWriterSubTab,
  validationResult,
  customPrompt,
  setCustomPrompt,
  outlineMode,
  setOutlineMode,
  wsLogs,
  streamingText,
  loadChapterDetails,
  handleDeleteChapter,
  openContinueModal,
  handleSaveOutline,
  handleSaveContent,
  handlePause,
  handleResume,
  handleRewriteChapter,
  handleInsertPrompt,
  handleForcePublish,
  currentFlowStep,
  streamingEvaluations,
  validatorStreamLog,
  onOpenChapterOverview,
  actionLoading,
  autoFollowGeneration,
  setAutoFollowGeneration,
  runningChapter
}) {

  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const timerRef = useRef(null);

  const [jsonReviewText, setJsonReviewText] = useState('');
  const [jsonParseError, setJsonParseError] = useState(null);
  const [savingJsonReview, setSavingJsonReview] = useState(false);
  const [selectedPatchIndexes, setSelectedPatchIndexes] = useState([]);
  const [showGuide, setShowGuide] = useState(false);
  const [mobilePane, setMobilePane] = useState('editor');
  const extractorReviewFlag = activeChapter?.review_flags?.find((flag) => flag?.type === 'extractor_high_risk');
  const fullStoryReviewFlag = activeChapter?.review_flags?.find((flag) => flag?.type === 'short_story_full_review');
  const fullStoryReview = fullStoryReviewFlag?.report;
  const extractorReviewPatchSet = extractorReviewFlag?.patch_set || null;
  const hasExtractorHighRiskReview = Boolean(
    extractorReviewFlag
  );

  useEffect(() => {
    if (activeChapter && activeChapter.status === 'pending_review') {
      if (hasExtractorHighRiskReview && extractorReviewPatchSet) {
        const patchIndexes = (extractorReviewPatchSet.patches || []).map((_, idx) => idx);
        setSelectedPatchIndexes(patchIndexes);
        setJsonReviewText(JSON.stringify(extractorReviewPatchSet, null, 2));
      } else {
        setSelectedPatchIndexes([]);
        setJsonReviewText(hasExtractorHighRiskReview ? '{}' : (activeChapter.error || '{}'));
      }
      setJsonParseError(null);
    }
  }, [activeChapter, hasExtractorHighRiskReview, extractorReviewPatchSet]);

  const updateSelectedPatchSet = (nextIndexes) => {
    setSelectedPatchIndexes(nextIndexes);
    if (!extractorReviewPatchSet) return;
    const selected = new Set(nextIndexes);
    const filteredPatchSet = {
      ...extractorReviewPatchSet,
      patches: (extractorReviewPatchSet.patches || []).filter((_, idx) => selected.has(idx)),
    };
    setJsonReviewText(JSON.stringify(filteredPatchSet, null, 2));
    setJsonParseError(null);
  };

  const isEditorJSON = (jsonStr) => {
    if (!jsonStr) return false;
    try {
      const parsed = JSON.parse(jsonStr);
      return parsed && (parsed.evaluations !== undefined || parsed.edited_content !== undefined);
    } catch {
      return jsonStr.includes('evaluations') || jsonStr.includes('edited_content') || jsonStr.includes('raw_issues');
    }
  };

  const handleSaveReviewJson = async () => {
    try {
      JSON.parse(jsonReviewText);
      setJsonParseError(null);
    } catch (e) {
      setJsonParseError("JSON 语法错误: " + e.message);
      return;
    }

    setSavingJsonReview(true);
    try {
      const step = isEditorJSON(jsonReviewText) ? 'editor' : 'extractor';
      const response = await fetch(`${API_BASE}/writing/${activeProject.id}/chapters/${activeChapter.chapter_index}/review_json`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          step,
          corrected_json: JSON.parse(jsonReviewText)
        })
      });
      if (response.ok) {
        setJsonParseError(null);
        await loadChapterDetails(activeProject.id, activeChapter.chapter_index);
        if (handleResume) {
          handleResume();
        }
      } else {
        const errData = await response.json();
        setJsonParseError(errData.detail || "提交失败，请检查数据格式");
      }
    } catch (err) {
      setJsonParseError(err.message);
    } finally {
      setSavingJsonReview(false);
    }
  };

  const isGenerating = activeProjectStatus?.status === 'generating';
  const isViewingRunningChapter = Boolean(
    isGenerating
    && activeChapter
    && runningChapter
    && activeChapter.chapter_index === runningChapter
  );
  const isViewingRunningSkeleton = Boolean(isGenerating && !activeChapter && (!runningChapter || runningChapter === 0));
  const isOutlineStreaming = isGenerating && currentFlowStep === 'planner';
  const isSkeletonStreaming = isOutlineStreaming && !activeChapter;
  const isEditorStreaming = isViewingRunningChapter && currentFlowStep === 'editor';
  const isValidatorStreaming = isViewingRunningChapter && currentFlowStep === 'validator';

  const mergedEvaluations = {
    ...(activeChapter?.evaluations || {}),
    ...(streamingEvaluations || {}),
  };
  const hasEvaluations = Object.keys(mergedEvaluations).length > 0;

  useEffect(() => {
    if (isGenerating) {
      setElapsedSeconds(0);
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setElapsedSeconds(0);
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isGenerating]);

  // Auto-switch tabs based on flow step
  useEffect(() => {
    if (autoFollowGeneration && isGenerating && currentFlowStep) {
      if (currentFlowStep === 'planner') {
        if (!activeChapter) {
          setWorkspaceStep('structure');
        } else {
          setWorkspaceStep('planner');
        }
      } else if (currentFlowStep === 'writer' || currentFlowStep === 'editor') {
        setWorkspaceStep('writer');
      } else if (currentFlowStep === 'validator') {
        setWorkspaceStep('validator');
      }
    }
  }, [autoFollowGeneration, currentFlowStep, isGenerating, setWorkspaceStep, activeChapter]);

  // Synchronize workspaceStep and activeChapter selection
  useEffect(() => {
    if (!activeChapter) {
      if (workspaceStep !== 'structure') {
        setWorkspaceStep('structure');
      }
    } else {
      if (workspaceStep === 'structure') {
        setWorkspaceStep('planner');
      }
    }
  }, [activeChapter, workspaceStep, setWorkspaceStep]);

  return (
    <div className={`workspace-layout workspace-layout--${mobilePane}`}>
      <div className="workspace-mobile-switcher" aria-label="工作台视图">
        <button type="button" className={mobilePane === 'chapters' ? 'active' : ''} onClick={() => setMobilePane('chapters')}>
          <List size={16} /> 章节目录
        </button>
        <button type="button" className={mobilePane === 'editor' ? 'active' : ''} onClick={() => setMobilePane('editor')}>
          <PenLine size={16} /> 编辑内容
        </button>
      </div>
      <WorkspaceSidebar
        loadChapterDetails={loadChapterDetails}
        openContinueModal={openContinueModal}
        onOpenChapterOverview={onOpenChapterOverview}
        setAutoFollowGeneration={setAutoFollowGeneration}
        onNavigateToEditor={() => setMobilePane('editor')}
      />
      <div className="workspace-main">
        <div className="workspace-main-content">
          {fullStoryReview && (
            <section className="glass-panel" style={{ padding: '16px', borderRadius: '8px', border: `1px solid ${fullStoryReview.passed ? 'rgba(34, 197, 94, 0.35)' : 'rgba(245, 158, 11, 0.4)'}`, marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                {fullStoryReview.passed ? <Check size={18} style={{ color: '#22c55e' }} /> : <AlertTriangle size={18} style={{ color: '#f59e0b' }} />}
                <strong style={{ fontSize: '14px' }}>短篇全文审校</strong>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{fullStoryReview.summary}</span>
              </div>
              {fullStoryReview.dimensions && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px' }}>
                  {Object.entries(fullStoryReview.dimensions).map(([key, dimension]) => (
                    <div key={key} style={{ borderTop: '1px solid var(--border-muted)', paddingTop: '8px', minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', fontSize: '12px' }}>
                        <span>{key.replaceAll('_', ' ')}</span>
                        <strong>{dimension?.score ?? '-'}/10</strong>
                      </div>
                      <p style={{ margin: '4px 0 0', fontSize: '11px', lineHeight: 1.45, color: 'var(--text-secondary)' }}>{dimension?.reason}</p>
                    </div>
                  ))}
                </div>
              )}
              {fullStoryReview.issues?.length > 0 && (
                <ul style={{ margin: '12px 0 0', paddingLeft: '18px', color: 'var(--text-secondary)', fontSize: '12px' }}>
                  {fullStoryReview.issues.map((issue, index) => (
                    <li key={`${issue.section || 0}-${index}`} style={{ marginBottom: '5px' }}>
                      第 {issue.section || '-'} 节：{issue.description} {issue.suggestion && `建议：${issue.suggestion}`}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
          {activeChapter && activeChapter.status === 'pending_review' && (
            <div className="glass-panel" style={{ padding: '20px', borderRadius: '12px', border: '1px solid var(--color-amber, #f59e0b)', background: 'rgba(245, 158, 11, 0.05)', marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <AlertTriangle className="text-amber-500" style={{ color: '#f59e0b' }} size={24} />
                <div>
                  <h4 style={{ margin: 0, fontSize: '15px', color: '#f59e0b', fontWeight: 600 }}>
                    {hasExtractorHighRiskReview ? '需要人工复核设定变更' : '需要人工审核 JSON 格式与字段设定'}
                  </h4>
                  <p className="text-xs text-secondary mt-1">
                    {hasExtractorHighRiskReview
                      ? '设定提取器发现可能影响后续剧情的高风险知识变更。请确认本章内容和设定变化合理后发布；系统不会把这段中文说明当作 JSON 解析。'
                      : isEditorJSON(activeChapter.error)
                      ? "【编辑智能体 (Editor)】返回的 JSON 结构损坏或缺失必须字段。您可以在下方微调 JSON 字段，保存以完成精修并继续。"
                      : "【提取智能体 (Extractor)】返回的 JSON 结构损坏或校验失败。您可以在下方微调 JSON 设定更新，保存以完成知识图谱同步。"}
                  </p>
                </div>
              </div>

              {hasExtractorHighRiskReview ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                  <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(0,0,0,0.18)', border: '1px solid var(--border-muted)' }}>
                    {activeChapter.error || '设定提取器发现高风险知识变更，需人工复核后发布。'}
                  </div>
                  {activeChapter.review_flags?.map((flag, idx) => (
                    <div key={idx} style={{ padding: '12px', borderRadius: '8px', background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
                      <strong>{flag.message || flag.detail || '复核提示'}</strong>
                      {flag.issues?.length > 0 && (
                        <ul style={{ margin: '8px 0 0 18px', padding: 0 }}>
                          {flag.issues.map((issue, issueIdx) => (
                            <li key={issueIdx}>{issue.description || JSON.stringify(issue)}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                  {extractorReviewPatchSet?.patches?.length > 0 && (
                    <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(0,0,0,0.18)', border: '1px solid var(--border-muted)' }}>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
                        本章 Extractor 提取出的设定变更
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {extractorReviewPatchSet.patches.map((patch, patchIdx) => (
                          <label key={patchIdx} style={{ display: 'grid', gridTemplateColumns: '18px 1fr', gap: '8px', alignItems: 'start', fontSize: '12px' }}>
                            <input
                              type="checkbox"
                              checked={selectedPatchIndexes.includes(patchIdx)}
                              onChange={(event) => {
                                const nextIndexes = event.target.checked
                                  ? [...selectedPatchIndexes, patchIdx].sort((a, b) => a - b)
                                  : selectedPatchIndexes.filter((idx) => idx !== patchIdx);
                                updateSelectedPatchSet(nextIndexes);
                              }}
                            />
                            <span>
                              <strong>{patch.doc_type || patch.category}</strong>
                              {' / '}
                              {patch.operation}
                              {' / '}
                              {patch.name}
                              <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '2px', wordBreak: 'break-word' }}>
                                {JSON.stringify(patch.data || {})}
                              </span>
                            </span>
                          </label>
                        ))}
                      </div>
                      <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginTop: '12px', marginBottom: '6px' }}>
                        提交前 JSON（可继续手动微调）
                      </label>
                      <textarea
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '12px',
                          background: 'rgba(0,0,0,0.4)',
                          border: '1px solid var(--border-muted)',
                          borderRadius: '8px',
                          padding: '12px',
                          minHeight: '180px',
                          color: '#e2e8f0',
                          width: '100%',
                          resize: 'vertical'
                        }}
                        value={jsonReviewText}
                        onChange={(e) => setJsonReviewText(e.target.value)}
                      />
                      {jsonParseError && (
                        <span style={{ fontSize: '12px', color: 'var(--color-red, #ef4444)', display: 'block', marginTop: '6px' }}>
                          {jsonParseError}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>微调 JSON 数据 (请确保格式合法)：</label>
                  <textarea
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '12px',
                      background: 'rgba(0,0,0,0.4)',
                      border: '1px solid var(--border-muted)',
                      borderRadius: '8px',
                      padding: '12px',
                      minHeight: '220px',
                      color: '#e2e8f0',
                      width: '100%',
                      resize: 'vertical'
                    }}
                    value={jsonReviewText}
                    onChange={(e) => setJsonReviewText(e.target.value)}
                  />
                  {jsonParseError && (
                    <span style={{ fontSize: '12px', color: 'var(--color-red, #ef4444)' }}>
                      ❌ {jsonParseError}
                    </span>
                  )}
                </div>
              )}

              <div style={{ display: 'flex', gap: '12px' }}>
                {hasExtractorHighRiskReview ? (
                  <>
                    {extractorReviewPatchSet?.patches?.length > 0 && (
                      <button
                        className="btn btn-primary"
                        onClick={handleSaveReviewJson}
                        disabled={savingJsonReview}
                        style={{ fontSize: '13px', padding: '6px 16px', display: 'flex', alignItems: 'center', gap: '4px' }}
                      >
                        {savingJsonReview ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />} 保存勾选后的设定变更
                      </button>
                    )}
                    <button
                      className="btn btn-secondary"
                      onClick={() => {
                        if (window.confirm('确认跳过设定变更，仅发布本章吗？这会忽略本章的高风险设定变更。')) {
                          handleForcePublish(activeChapter.chapter_index);
                        }
                      }}
                      style={{ fontSize: '13px', padding: '6px 16px', display: 'flex', alignItems: 'center', gap: '4px' }}
                    >
                      <Check size={14} /> 跳过设定变更，仅发布本章
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      className="btn btn-primary"
                      onClick={handleSaveReviewJson}
                      disabled={savingJsonReview}
                      style={{ fontSize: '13px', padding: '6px 16px', display: 'flex', alignItems: 'center', gap: '4px' }}
                    >
                      {savingJsonReview ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />} 保存并提交 (继续流程)
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={() => {
                        setJsonReviewText(activeChapter.error || '{}');
                        setJsonParseError(null);
                      }}
                      style={{ fontSize: '13px', padding: '6px 12px' }}
                    >
                      重置为原始响应
                    </button>
                  </>
                )}
              </div>
            </div>
          )}



          {/* Step Focus display */}
          <div className="step-focused-pane">
            <div className="pane-header">
              <div style={{ display: 'flex', gap: '8px' }}>
                {!activeChapter ? (
                  <button className={`btn ${workspaceStep === 'structure' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setWorkspaceStep('structure')}>
                    全书大纲 {(currentFlowStep === 'planner' || currentFlowStep === 'structure') && isViewingRunningSkeleton && <Loader2 className="animate-spin" size={12} style={{ marginLeft: 4 }} />}
                  </button>
                ) : (
                  <>
                    <button className={`btn ${workspaceStep === 'planner' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setWorkspaceStep('planner')}>
                      章节策划 {currentFlowStep === 'planner' && isViewingRunningChapter && <Loader2 className="animate-spin" size={12} style={{ marginLeft: 4 }} />}
                    </button>
                    <button className={`btn ${workspaceStep === 'writer' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setWorkspaceStep('writer')}>
                      执笔初稿与润色 {(currentFlowStep === 'writer' || currentFlowStep === 'editor') && isViewingRunningChapter && <Loader2 className="animate-spin" size={12} style={{ marginLeft: 4 }} />}
                    </button>
                    <button className={`btn ${workspaceStep === 'validator' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setWorkspaceStep('validator')}>
                      法则审查 {currentFlowStep === 'validator' && isViewingRunningChapter && <Loader2 className="animate-spin" size={12} style={{ marginLeft: 4 }} />}
                    </button>
                  </>
                )}
              </div>

              {isGenerating && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--vermilion)', fontWeight: 500 }}>
                  <RefreshCw className="spin-slow" size={14} />
                  <span>已运行 {elapsedSeconds} 秒</span>
                </div>
              )}

              {(workspaceStep === 'planner' || workspaceStep === 'structure') && (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    {activeProjectStatus?.status === 'paused' && !activeChapter && workspaceStep === 'structure' && (!chapters || chapters.length === 0) && (
                      <button className="btn btn-primary" onClick={handleResume}>
                        <Check size={14} /> 审核通过，继续创作
                      </button>
                    )}
                    <button className="btn btn-secondary" onClick={handleSaveOutline} disabled={savingOutline}>
                      {savingOutline ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />} {workspaceStep === 'structure' ? '保存全书大纲' : '保存章节大纲'}
                    </button>
                  {!(isGenerating && activeProjectStatus?.current_chapter === activeChapter?.chapter_index) && activeChapter && workspaceStep === 'planner' && (
                    <button
                      className="btn btn-secondary"
                      onClick={() => {
                        if (window.confirm(`确定要删除第 ${activeChapter.chapter_index} 章吗？删除后不可恢复。`)) {
                          handleDeleteChapter(activeChapter.chapter_index);
                        }
                      }}
                      style={{ color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.3)', background: 'rgba(239, 68, 68, 0.05)' }}
                      title="删除此章节"
                    >
                      <Trash2 size={14} /> 删除本章
                    </button>
                  )}
                </div>
              )}
              {workspaceStep === 'writer' && (
                <button className="btn btn-secondary" onClick={handleSaveContent} disabled={savingContent}>
                  {savingContent ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />} 保存修改
                </button>
              )}
            </div>

            {/* Collapsible Pipeline Guide Card */}
            <div className="glass-panel" style={{ padding: '12px 16px', borderRadius: '8px', marginBottom: '16px', background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-muted)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }} onClick={() => setShowGuide(!showGuide)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                  <HelpCircle size={15} style={{ color: 'var(--color-blue, #3b82f6)' }} />
                  <span>了解 AI 多智能体创作流水线机制 (新手指南)</span>
                </div>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{showGuide ? '收起 ▲' : '展开 ▼'}</span>
              </div>

              {showGuide && (
                <div style={{ marginTop: '12px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', borderTop: '1px solid var(--border-muted)', paddingTop: '12px', fontSize: '12px', lineHeight: '1.6' }}>
                  <div style={{ padding: '10px', borderRadius: '6px', background: 'rgba(0,0,0,0.15)' }}>
                    <strong style={{ color: 'var(--gold, #d97706)' }}>1. 策划智能体 (Planner)</strong>
                    <p style={{ margin: '4px 0 0 0', color: 'var(--text-secondary)' }}>
                      读取大纲和背景，为下一章生成细化章节情节大纲，规划剧情走向与出场人物。
                    </p>
                  </div>
                  <div style={{ padding: '10px', borderRadius: '6px', background: 'rgba(0,0,0,0.15)' }}>
                    <strong style={{ color: '#10b981' }}>2. 执笔智能体 (Writer)</strong>
                    <p style={{ margin: '4px 0 0 0', color: 'var(--text-secondary)' }}>
                      依据章节大纲、上文正文和检索到的设定知识，撰写大容量的小说正文初稿。
                    </p>
                  </div>
                  <div style={{ padding: '10px', borderRadius: '6px', background: 'rgba(0,0,0,0.15)' }}>
                    <strong style={{ color: '#f59e0b' }}>3. 精修智能体 (Editor)</strong>
                    <p style={{ margin: '4px 0 0 0', color: 'var(--text-secondary)' }}>
                      从剧情、人物、设定、文笔、逻辑 5 个维度对初稿进行全面打分，并迭代精修润色。
                    </p>
                  </div>
                  <div style={{ padding: '10px', borderRadius: '6px', background: 'rgba(0,0,0,0.15)' }}>
                    <strong style={{ color: '#ef4444' }}>4. 天道审计 (Validator)</strong>
                    <p style={{ margin: '4px 0 0 0', color: 'var(--text-secondary)' }}>
                      审查正文是否违背境界设定、人物生死等设定规则。若有严重冲突则自动回滚并启动重写。
                    </p>
                  </div>
                  <div style={{ padding: '10px', borderRadius: '6px', background: 'rgba(0,0,0,0.15)' }}>
                    <strong style={{ color: '#a855f7' }}>5. 设定同步 (Extractor)</strong>
                    <p style={{ margin: '4px 0 0 0', color: 'var(--text-secondary)' }}>
                      提取并归纳本章产生的新实体设定、人物境界突破和伏笔消解，增量式同步更新到活文档。
                    </p>
                  </div>
                </div>
              )}
            </div>

            <div className="pane-body">
              {currentFlowStep === 'extractor' && isGenerating && (
                <div className="glass-panel" style={{ padding: '12px 16px', borderRadius: '8px', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--text-secondary)', border: '1px solid rgba(168, 85, 247, 0.25)', background: 'rgba(168, 85, 247, 0.06)' }}>
                  <Loader2 className="animate-spin" size={14} style={{ color: '#a855f7' }} />
                  设定同步智能体正在提取本章新设定并更新活文档，完成后将自动进入下一章创作。
                </div>
              )}
              <WorkspaceOutline
                workspaceStep={workspaceStep}
                activeChapter={activeChapter}
                editedOutline={editedOutline}
                setEditedOutline={setEditedOutline}
                outlineMode={outlineMode}
                setOutlineMode={setOutlineMode}
                isOutlineStreaming={isOutlineStreaming}
                isSkeletonStreaming={isSkeletonStreaming}
                activeProject={activeProject}
                API_BASE={API_BASE}
                handleDeleteChapter={handleDeleteChapter}
                isGenerating={isGenerating}
                onOpenChapterOverview={onOpenChapterOverview}
              />
              <WorkspaceEditor
                workspaceStep={workspaceStep}
                writerSubTab={writerSubTab}
                setWriterSubTab={setWriterSubTab}
                activeChapter={activeChapter}
                editedTitle={editedTitle}
                setEditedTitle={setEditedTitle}
                editedContent={editedContent}
                setEditedContent={setEditedContent}
                isEditorStreaming={isEditorStreaming}
                hasEvaluations={hasEvaluations}
                mergedEvaluations={mergedEvaluations}
                streamingText={streamingText}
              />
              <WorkspaceValidator
                workspaceStep={workspaceStep}
                isValidatorStreaming={isValidatorStreaming}
                validatorStreamLog={validatorStreamLog}
                validationResult={validationResult}
                setWorkspaceStep={setWorkspaceStep}
                setWriterSubTab={setWriterSubTab}
                handleRewriteChapter={handleRewriteChapter}
                handleForcePublish={handleForcePublish}
                activeChapter={activeChapter}
              />
            </div>
          </div>
        </div>

        {/* Console Log at bottom */}
        <ConsoleLogs
          wsLogs={wsLogs}
          streamingText={streamingText}
          handlePause={handlePause}
          handleResume={handleResume}
          handleRewriteChapter={handleRewriteChapter}
          customPrompt={customPrompt}
          setCustomPrompt={setCustomPrompt}
          handleInsertPrompt={handleInsertPrompt}
          elapsedSeconds={elapsedSeconds}
          isGenerating={isGenerating}
          actionLoading={actionLoading}
        />
      </div>
    </div>
  );
}

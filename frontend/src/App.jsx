import { lazy, Suspense, useState, useEffect, useRef } from 'react';
import {
  RefreshCw,
  AlertTriangle,
  Check,
  Eye,
  Crosshair
} from 'lucide-react';
import './App.css';
import { useUIStore, useProjectStore } from './store/useStore';

import CreateProjectModal from './components/CreateProjectModal';
import ContinueModal from './components/ContinueModal';
import ChapterOutlinesOverview from './components/ChapterOutlinesOverview';
import AppShell from './components/shell/AppShell';
import StatusBadge from './components/ui/StatusBadge';
import ProjectShelf from './pages/ProjectShelf';
import Workspace from './pages/Workspace';
import useBackendHealth from './hooks/useBackendHealth';
import useGenerationActions from './hooks/useGenerationActions';
import useProjectData from './hooks/useProjectData';
import useProjectRealtime, { shouldApplyChapterStreaming } from './hooks/useProjectRealtime';
import { API_BASE, BACKEND_URL, saveBackendUrl as persistBackendUrl } from './services/api';
import { DEFAULT_TARGET_CHAPTERS, DEFAULT_WORD_COUNT_PER_CHAPTER, createDefaultCreativeProfile } from './utils/constants';
import { issuesToValidationResult } from './utils/streamingJsonParser';
const LivingDocs = lazy(() => import('./pages/LivingDocs'));
const Settings = lazy(() => import('./pages/Settings'));
const SystemConfigs = lazy(() => import('./pages/SystemConfigs'));

export default function App() {
  const [activeTab, setActiveTab] = useState('shelf'); // shelf, workspace, docs, settings
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [autoFollowGeneration, setAutoFollowGeneration] = useState(true);
  const activeProject = useProjectStore(state => state.activeProject);
  const setActiveProject = useProjectStore(state => state.setActiveProject);
  const activeProjectStatus = useProjectStore(state => state.activeProjectStatus);
  const setActiveProjectStatus = useProjectStore(state => state.setActiveProjectStatus);
  const chapters = useProjectStore(state => state.chapters);
  const setChapters = useProjectStore(state => state.setChapters);
  const activeChapter = useProjectStore(state => state.activeChapter);
  const setActiveChapter = useProjectStore(state => state.setActiveChapter);

  // Creation States
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProject, setNewProject] = useState({
    title: '',
    author: '智能体作家',
    target_chapters: DEFAULT_TARGET_CHAPTERS,
    word_count_per_chapter: DEFAULT_WORD_COUNT_PER_CHAPTER,
    novel_format: 'long_webnovel',
    creative_profile: createDefaultCreativeProfile('long'),
    user_prompt: ''
  });
  const [creating, setCreating] = useState(false);

  // Settings view
  const [settingsData, setSettingsData] = useState({ providers: [], active_provider_id: 'default' });

  // O-06: Global Toast notification state
  const [toast, setToast] = useState(null);
  const toastTimerRef = useRef(null);
  const showToast = (message, type = 'error') => {
    setToast({ message, type });
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 3000);
  };

  // O-11: Action loading state for submit-type operations
  const [actionLoading, setActionLoading] = useState(false);

  // Workspace View State
  const workspaceStep = useUIStore(state => state.workspaceStep);
  const setWorkspaceStep = useUIStore(state => state.setWorkspaceStep); // planner, writer, validator
  const editedOutline = useProjectStore(state => state.editedOutline);
  const setEditedOutline = useProjectStore(state => state.setEditedOutline);
  const editedTitle = useProjectStore(state => state.editedTitle);
  const setEditedTitle = useProjectStore(state => state.setEditedTitle);
  const editedContent = useProjectStore(state => state.editedContent);
  const setEditedContent = useProjectStore(state => state.setEditedContent);
  const [savingOutline, setSavingOutline] = useState(false);
  const [savingContent, setSavingContent] = useState(false);
  const writerSubTab = useUIStore(state => state.writerSubTab);
  const setWriterSubTab = useUIStore(state => state.setWriterSubTab); // compare, draft, final
  const validationResult = useProjectStore(state => state.validationResult);
  const setValidationResult = useProjectStore(state => state.setValidationResult);
  const currentFlowStep = useProjectStore(state => state.currentFlowStep);
  const setCurrentFlowStep = useProjectStore(state => state.setCurrentFlowStep);
  const customPrompt = useUIStore(state => state.customPrompt);
  const setCustomPrompt = useUIStore(state => state.setCustomPrompt);
  const outlineMode = useUIStore(state => state.outlineMode);
  const setOutlineMode = useUIStore(state => state.setOutlineMode); // 'visual' | 'json'

  // Streaming/WebSockets
  const wsLogs = useProjectStore(state => state.wsLogs);
  const setWsLogs = useProjectStore(state => state.setWsLogs);
  const streamingText = useProjectStore(state => state.streamingText);
  const setStreamingText = useProjectStore(state => state.setStreamingText);
  const lastWsMessageTimeRef = useRef(Date.now());
  const chaptersFetchSeqRef = useRef(0);
  const chapterDetailsFetchSeqRef = useRef(0);
  const chaptersDebounceRef = useRef(null);
  const refreshDebounceRef = useRef(null);
  const abortControllerRef = useRef(null);
  const lastPolledJobRef = useRef({ step: '', chapter: 0 });
  const initialProjectParamRef = useRef(null);
  const deepLinkConsumedRef = useRef(false);

  // F-07: Keep latest activeProject in a ref to avoid stale closure in handleWsMessage
  const activeProjectRef = useRef(activeProject);
  const activeProjectIdRef = useRef(activeProject?.id ?? null);
  activeProjectRef.current = activeProject;
  activeProjectIdRef.current = activeProject?.id ?? null;

  // Keep latest autoFollowGeneration in a ref: handleWsMessage / loadProjectStatus
  // are captured once by the single WS binding and by poll closures, so reading the
  // raw state there is stale. The ref always reflects the current toggle value.
  const autoFollowGenerationRef = useRef(autoFollowGeneration);
  autoFollowGenerationRef.current = autoFollowGeneration;

  // F-11: RAF batch refs for high-frequency streaming updates
  const pendingStreamUpdatesRef = useRef({
    text: '', textAgent: '',
    outline: '',
    writerText: '', writerChapterIndex: null,
    editorContent: '',
    evaluations: null,
    validatorLog: '',
    validationResult: null,
  });
  const rafScheduledRef = useRef(false);

  const flushStreamUpdates = () => {
    rafScheduledRef.current = false;
    const p = pendingStreamUpdatesRef.current;

    if (p.text) {
      const agent = p.textAgent;
      const chunk = p.text;
      setStreamingText((prev) => {
        if (prev.agent === agent) {
          return { agent, text: prev.text + chunk };
        }
        return { agent, text: chunk };
      });
    }
    if (p.outline) {
      const chunk = p.outline;
      setEditedOutline((prev) => prev + chunk);
    }
    if (p.writerText) {
      const chapterIndex = p.writerChapterIndex;
      const chunk = p.writerText;
      setActiveChapter((prev) => {
        if (prev && prev.chapter_index === chapterIndex) {
          return { ...prev, draft_content: (prev.draft_content || '') + chunk };
        }
        return prev;
      });
    }
    if (p.editorContent) {
      const chunk = p.editorContent;
      setEditedContent((prev) => prev + chunk);
    }
    if (p.evaluations) {
      const evalData = p.evaluations;
      setStreamingEvaluations((prev) => ({ ...(prev || {}), ...evalData }));
    }
    if (p.validatorLog) {
      const chunk = p.validatorLog;
      setValidatorStreamLog((prev) => prev + chunk);
    }
    if (p.validationResult) {
      setValidationResult(p.validationResult);
    }

    // Reset accumulated values
    pendingStreamUpdatesRef.current = {
      text: '', textAgent: '',
      outline: '',
      writerText: '', writerChapterIndex: null,
      editorContent: '',
      evaluations: null,
      validatorLog: '',
      validationResult: null,
    };
  };

  const scheduleStreamFlush = () => {
    if (!rafScheduledRef.current) {
      rafScheduledRef.current = true;
      requestAnimationFrame(flushStreamUpdates);
    }
  };

  const isStuckWarning = useProjectStore(state => state.isStuckWarning);
  const setIsStuckWarning = useProjectStore(state => state.setIsStuckWarning);
  const streamingEvaluations = useProjectStore(state => state.streamingEvaluations);
  const setStreamingEvaluations = useProjectStore(state => state.setStreamingEvaluations);
  const validatorStreamLog = useProjectStore(state => state.validatorStreamLog);
  const setValidatorStreamLog = useProjectStore(state => state.setValidatorStreamLog);

  // Living Docs States
  const [livingDocs, setLivingDocs] = useState({ world_state: '', character_state: '', foreshadowing: '', plot_threads: '' });

  // Continue writing config modal states
  const [showContinueModal, setShowContinueModal] = useState(false);
  const [showOutlinesOverview, setShowOutlinesOverview] = useState(false);
  const [continueChaptersCount, setContinueChaptersCount] = useState(1);
  const [continueWordCount, setContinueWordCount] = useState(3000);

  // Versions and timelines
  const [docVersions, setDocVersions] = useState([]);
  const [tokenStats, setTokenStats] = useState(null);

  const backendStatus = useBackendHealth();

  // Watchdog timer check
  useEffect(() => {
    const interval = setInterval(() => {
      const isGenerating = activeProjectStatus?.status === 'generating';
      if (isGenerating) {
        const timeoutSec = settingsData?.watchdog_timeout || 45;
        const elapsedSinceLastMessage = (Date.now() - lastWsMessageTimeRef.current) / 1000;
        if (elapsedSinceLastMessage > timeoutSec) {
          setIsStuckWarning(true);
        } else {
          setIsStuckWarning(false);
        }
      } else {
        setIsStuckWarning(false);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [activeProjectStatus, settingsData]);

  // REST 轮询兜底：独立 Worker 模式下保证状态/章节列表及时刷新
  useEffect(() => {
    if (!activeProject?.id) return;
    if (activeProjectStatus?.status !== 'generating') return;

    const poll = async () => {
      const signal = abortControllerRef.current?.signal;
      await loadProjectStatus(activeProject.id, { fromPoll: true, signal });
      await loadChapters(activeProject.id, { signal });
      await loadProjects({ silent: true });
      lastWsMessageTimeRef.current = Date.now();
    };

    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [activeProject?.id, activeProjectStatus?.status]);

  const saveBackendUrl = (url) => {
    persistBackendUrl(url);
    window.location.reload();
  };

  const clearProjectParam = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('project');
    window.history.replaceState(null, '', url);
  };

  // Load projects on load
  useEffect(() => {
    initialProjectParamRef.current = new URLSearchParams(window.location.search).get('project');
    loadProjects();
    loadSettings();
  }, []);

  useEffect(() => {
    const projectId = initialProjectParamRef.current;
    if (!projectId || deepLinkConsumedRef.current || projectsLoading) return;

    const project = projects.find((p) => p.id === projectId);
    if (project) {
      deepLinkConsumedRef.current = true;
      handleProjectSelect(project);
      setActiveTab('workspace');
    }
  }, [projects, projectsLoading]);

  // Connect WebSockets when active project changes
  useEffect(() => {
    setCurrentFlowStep('');
    setChapters([]);
    setActiveChapter(null);
    // F-22: Abort previous in-flight requests from the old project
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();
    const { signal } = abortControllerRef.current;
    if (activeProject) {
      loadChapters(activeProject.id, { replace: true, signal });
      loadProjectStatus(activeProject.id, { signal });
      loadLivingDocs(activeProject.id);
      loadTokenStats(activeProject.id);
    }
    return () => {
      // F-22: Abort any in-flight fetch requests from the old project
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      if (chaptersDebounceRef.current) clearTimeout(chaptersDebounceRef.current);
      // F-21: Clear pending debounced refresh on project switch
      if (refreshDebounceRef.current) {
        clearTimeout(refreshDebounceRef.current);
        refreshDebounceRef.current = null;
      }
      // Reset pending streaming updates — they belong to the old project
      rafScheduledRef.current = false;
      pendingStreamUpdatesRef.current = {
        text: '', textAgent: '',
        outline: '',
        writerText: '', writerChapterIndex: null,
        editorContent: '',
        evaluations: null,
        validatorLog: '',
        validationResult: null,
      };
    };
  }, [activeProject?.id]);

  const {
    loadProjects,
    loadProjectStatus,
    loadChapters,
    scheduleLoadChapters,
    ensureChapterInList,
    loadChapterDetails,
    loadLivingDocs,
    loadSettings,
    saveSettings,
    loadTokenStats,
  } = useProjectData({
    addLog,
    showToast,
    activeProjectRef,
    autoFollowGenerationRef,
    lastPolledJobRef,
    chaptersFetchSeqRef,
    chaptersDebounceRef,
    chapterDetailsFetchSeqRef,
    setProjects,
    setProjectsLoading,
    setActiveProject,
    setActiveProjectStatus,
    setChapters,
    setActiveChapter,
    setEditedTitle,
    setEditedContent,
    setEditedOutline,
    setValidationResult,
    setValidatorStreamLog,
    setStreamingEvaluations,
    setCurrentFlowStep,
    setOutlineMode,
    setLivingDocs,
    setDocVersions,
    setSettingsData,
    setTokenStats,
  });

  const handleWsMessage = (msg) => {
    // Use ref to read latest activeProject — avoids stale closure when activeProject properties change
    const proj = activeProjectRef.current;
    if (!proj) return;

    lastWsMessageTimeRef.current = Date.now();
    setIsStuckWarning(false);
    const type = msg.type;
    if (type === 'log') {
      let styleClass = 'system';
      if (msg.source) {
        const sourceLower = msg.source.toLowerCase();
        if (sourceLower === '校验器' || sourceLower === 'validator') styleClass = 'agent-validator';
        else if (sourceLower === '提取器' || sourceLower === 'extractor') styleClass = 'agent-extractor';
        else if (sourceLower === '策划器' || sourceLower === 'planner') styleClass = 'agent-planner';
        else if (sourceLower === '作家' || sourceLower === 'writer') styleClass = 'agent-writer';
        else if (sourceLower === '编辑器' || sourceLower === 'editor') styleClass = 'agent-editor';
        else styleClass = `agent-${sourceLower}`;
      }
      addLog(msg.source || '系统', msg.message || msg.text, styleClass);
      // Trigger status reload on stage changes
      if (msg.message && (msg.message.includes('优化') || msg.message.includes('完成') || msg.message.includes('中断'))) {
        // F-21: Debounce the 5 concurrent refresh calls to avoid request storms
        if (refreshDebounceRef.current) clearTimeout(refreshDebounceRef.current);
        refreshDebounceRef.current = setTimeout(() => {
          refreshDebounceRef.current = null;
          loadChapters(proj.id);
          loadProjectStatus(proj.id);
          loadLivingDocs(proj.id);
          loadTokenStats(proj.id);
          loadProjects(); // Keep projects/bookshelf status in sync
        }, 2000);
      }
    } else if (type === 'status') {
      addLog(msg.step || '系统', msg.message, `agent-${msg.step}`);
      setCurrentFlowStep(msg.step);

      if (autoFollowGenerationRef.current && ['planner', 'writer', 'editor', 'validator'].includes(msg.step)) {
        setActiveTab('workspace');
      }

      if (autoFollowGenerationRef.current && msg.step === 'planner') {
        setWorkspaceStep('planner');
        setOutlineMode('json');
        // chapter 0 = 整书骨架；章节大纲才清空重流
        if (msg.chapter !== 0) {
          setEditedOutline('');
        }
      } else if (autoFollowGenerationRef.current && msg.step === 'writer') {
        setOutlineMode('visual');
        setWorkspaceStep('writer');
        setWriterSubTab('draft');
        setActiveChapter(prev => {
          if (prev && prev.chapter_index === msg.chapter) {
            return { ...prev, draft_content: '' };
          }
          return prev;
        });
      } else if (autoFollowGenerationRef.current && msg.step === 'editor') {
        setWorkspaceStep('writer');
        setWriterSubTab('evaluations');
        setEditedContent('');
        setStreamingEvaluations(null);
        resetEditorParsers();
      } else if (autoFollowGenerationRef.current && msg.step === 'validator') {
        setWorkspaceStep('validator');
        setValidatorStreamLog('');
        resetValidatorParser();
        setValidationResult({ errors: [], warnings: [], infos: [], story_issues: [], streaming: true, passed: null });
      } else if (msg.step === 'extractor') {
        setStreamingEvaluations(null);
      }

      if (msg.chapter && msg.chapter > 0) {
        ensureChapterInList(msg.chapter);
        if (!autoFollowGenerationRef.current) {
          // 用户已切到其他页面或章节：后台继续刷新列表，但不抢焦点、不覆盖当前编辑区。
        } else if (msg.step === 'planner') {
          // 大纲流式写入编辑器，不在Center从服务端覆盖
        } else if (msg.step === 'editor') {
          loadChapterDetails(proj.id, msg.chapter, { preserveContent: true, preserveOutline: true });
        } else if (msg.step === 'validator') {
          loadChapterDetails(proj.id, msg.chapter, { preserveValidation: true, preserveOutline: true, preserveContent: true });
        } else {
          loadChapterDetails(proj.id, msg.chapter);
        }
      }

      scheduleLoadChapters(proj.id);
      loadProjectStatus(proj.id);
      loadProjects(); // Keep projects/bookshelf status in sync
    } else if (type === 'chunk') {
      const routedAgents = ['writer', 'editor', 'planner', 'validator'];
      const p = pendingStreamUpdatesRef.current;

      if (!routedAgents.includes(msg.agent)) {
        // Accumulate non-routed agent streaming text
        if (p.textAgent && p.textAgent !== msg.agent) {
          // Agent changed — flush current pending before switching
          flushStreamUpdates();
          const p2 = pendingStreamUpdatesRef.current;
          p2.textAgent = msg.agent;
          p2.text = msg.text;
        } else {
          p.textAgent = msg.agent;
          p.text += msg.text;
        }
        scheduleStreamFlush();
      }

      const activeChapterIndex = useProjectStore.getState().activeChapter?.chapter_index;
      const shouldApplyChapterScopedStreaming = shouldApplyChapterStreaming(
        autoFollowGenerationRef.current,
        msg.chapter_index,
        activeChapterIndex,
      );

      if (msg.agent === 'planner') {
        if (msg.phase !== 'reasoning') {
          if (shouldApplyChapterScopedStreaming) {
            p.outline += msg.text;
          }
          setOutlineMode('json');
        }
        scheduleStreamFlush();
      } else if (msg.agent === 'writer') {
        p.writerChapterIndex = msg.chapter_index;
        if (msg.phase !== 'reasoning' && shouldApplyChapterScopedStreaming) {
          p.writerText += msg.text;
        }
        scheduleStreamFlush();
      } else if (msg.agent === 'editor') {
        if (msg.phase !== 'reasoning') {
          const parsedEditor = appendEditorChunk(msg.text);
          if (parsedEditor.content && shouldApplyChapterScopedStreaming) {
            p.editorContent += parsedEditor.content;
          }
          if (parsedEditor.evaluations && shouldApplyChapterScopedStreaming) {
            p.evaluations = { ...(p.evaluations || {}), ...parsedEditor.evaluations };
          }
        }
        scheduleStreamFlush();
      } else if (msg.agent === 'validator') {
        if (shouldApplyChapterScopedStreaming) {
          p.validatorLog += msg.text;
        }
        if (msg.phase === 'llm' || msg.phase === 'streaming') {
          const { issues, passed } = appendValidatorChunk(msg.text);
          if (shouldApplyChapterScopedStreaming && (issues.length > 0 || passed !== null)) {
            p.validationResult = issuesToValidationResult(issues, passed, proj.novel_format);
          }
        }
        scheduleStreamFlush();
      }
    } else if (type === 'warning') {
      addLog('校验器', `[警报] ${msg.message}`, 'agent-validator');
    } else if (type === 'error') {
      const message = msg.message || '未知错误';
      const looksRecoverableJsonError = /JSON格式校验|Schema验证|Failed to parse JSON response/i.test(message);
      addLog(
        '系统',
        looksRecoverableJsonError ? `[自动修复重试] ${message}` : `[异常] ${message}`,
        looksRecoverableJsonError ? 'warning' : 'error',
      );
      loadProjectStatus(proj.id);
      loadChapters(proj.id);
      loadProjects(); // Keep projects/bookshelf status in sync
    }
  };

  const MAX_WS_LOGS = 500;
  const addLog = (source, message, styleClass = '') => {
    const timeStr = new Date().toLocaleTimeString();
    setWsLogs((prev) => {
      const next = [...prev, { time: timeStr, source, text: message, styleClass }];
      return next.length > MAX_WS_LOGS ? next.slice(next.length - MAX_WS_LOGS) : next;
    });
  };

  const {
    isConnected: isWsConnected,
    resetEditorParsers,
    resetValidatorParser,
    appendEditorChunk,
    appendValidatorChunk,
  } = useProjectRealtime({
    projectId: activeProject?.id,
    onMessage: handleWsMessage,
    onOpen: (projectId) => {
      addLog('系统', 'WebSocket 创作链路已成功连接', 'system');
      loadProjectStatus(projectId);
      loadChapters(projectId);
      loadProjects();
    },
    onLog: addLog,
    onError: (error, source) => {
      console.error(error);
      showToast(
        source === 'parse' ? 'WebSocket 消息解析失败' : 'WebSocket 连接出错，正在尝试重连...',
        'warning',
      );
    },
  });

  const {
    handlePause, handleResume, handleInsertPrompt, handleForcePublish, handleProjectSelect,
    handleCreateProject, handleDeleteProject, openContinueModal,
    handleConfirmContinue, handleUpdateProjectConfig, handleRewriteChapter, handleDeleteChapter,
    handleSaveOutline, handleSaveContent,
  } = useGenerationActions({
    project: { activeProject, activeChapter, newProject },
    editor: { customPrompt, editedOutline, editedContent, editedTitle },
    generation: { continueChaptersCount, continueWordCount },
    services: {
      addLog, showToast, loadProjects, loadProjectStatus, loadChapters, loadChapterDetails, loadLivingDocs,
    },
    setters: {
      setAutoFollowGeneration, setCustomPrompt, setActiveChapter, setEditedOutline, setChapters,
      setWorkspaceStep, setOutlineMode, setActiveProject, setCreating, setShowCreateModal, setNewProject,
      setActiveTab, setProjects, setActionLoading, setShowContinueModal, setContinueChaptersCount,
      setContinueWordCount, setValidationResult, setStreamingEvaluations, setValidatorStreamLog,
      setEditedContent, setSavingOutline, setSavingContent,
    },
  });

  const getStatusText = () => {
    if (!activeProjectStatus) return '';
    if (activeProjectStatus.status === 'paused') {
      if (activeProjectStatus.await_outline_review) {
        return '等待大纲审阅';
      }
      if (chapters && chapters.some(ch => ch.status === 'pending_review')) {
        return '等待章节审阅';
      }
      return '已暂停';
    }
    if (activeProjectStatus.status === 'completed') return '已完结';
    if (activeProjectStatus.status === 'failed') return '异常中断';

    if (activeProjectStatus.status === 'generating') {
      if (activeProjectStatus.latest_job_status === 'pending') {
        return '系统调度排队中';
      }
      switch (currentFlowStep) {
        case 'planner': return '大纲策划中';
        case 'writer': return '撰写初稿中';
        case 'editor': return '审阅润色中';
        case 'validator': return '天道审计中';
        case 'extractor': return '设定提取中';
        case 'system': return '后台扫描中';
        default: return 'AI创作流进行中';
      }
    }
    return '已暂停';
  };

  const handleNavigate = (tab) => {
    if (tab !== 'workspace') setAutoFollowGeneration(false);
    if (tab === 'shelf') {
      clearProjectParam();
      loadProjects();
    }
    setActiveTab(tab);
  };

  return (
    <>
      <AppShell
        activeTab={activeTab}
        activeProject={activeProject}
        backendStatus={backendStatus}
        onNavigate={handleNavigate}
        onLeaveProject={() => {
          clearProjectParam();
          setActiveProject(null);
          setActiveTab('shelf');
        }}
        headerActions={(
          <>
            {activeTab === 'workspace' && activeProjectStatus && (
              <StatusBadge
                status={activeProjectStatus.status}
                label={getStatusText()}
                pulse={activeProjectStatus.status === 'generating'}
              />
            )}
            {activeTab === 'workspace' && activeProjectStatus?.status === 'paused' && (activeProjectStatus.await_outline_review || (chapters && chapters.some(ch => ch.status === 'pending_review'))) && (
              <button className="btn btn-review"
                onClick={() => {
                  setActiveTab('workspace');
                  if (activeProjectStatus.await_outline_review) {
                    setWorkspaceStep('structure');
                    setActiveChapter(null);
                  } else {
                    const pendingCh = chapters.find(ch => ch.status === 'pending_review');
                    if (pendingCh) {
                      loadChapterDetails(activeProject.id, pendingCh.chapter_index);
                    }
                  }
                }}
              >
                <Eye size={14} /> 前往审阅
              </button>
            )}
            {activeTab === 'workspace' && activeProjectStatus?.status === 'failed' && activeProjectStatus?.latest_job_error && (
              <span className="top-bar__error" title={activeProjectStatus.latest_job_error}>
                <AlertTriangle size={14} /> {activeProjectStatus.latest_job_error}
              </span>
            )}
            {activeProject && activeProjectStatus?.status === 'generating' && (
              <button
                className={`btn btn-compact ${autoFollowGeneration ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => {
                  setAutoFollowGeneration((v) => {
                    const next = !v;
                    if (next) {
                      const runningChapter = activeProjectStatus?.latest_job_chapter;
                      if (runningChapter && runningChapter > 0) {
                        setActiveTab('workspace');
                        loadChapterDetails(activeProject.id, runningChapter);
                      }
                    }
                    return next;
                  });
                }}
                title={autoFollowGeneration ? '正在跟随生成中的章节；点击后停止自动跳转' : '已停止自动跟随；点击后回到生成中的章节'}
              >
                <Crosshair size={14} /> {autoFollowGeneration ? '自动跟随中' : '跟随已关闭'}
              </button>
            )}
            {!activeProject ? (
              <span className="connection-state">请选择一部作品</span>
            ) : isWsConnected ? (
              <span className="connection-state connection-state--online">
                <Check size={14} /> 实时同步
              </span>
            ) : (
              <span className="connection-state connection-state--pending">
                <RefreshCw className="animate-spin" size={14} /> 连接中
              </span>
            )}
          </>
        )}
      >
        <Suspense fallback={<div className="page-loading"><RefreshCw className="animate-spin" size={18} /> 正在载入页面</div>}>
          {activeTab === 'shelf' && (
            <ProjectShelf
              projects={projects}
              loading={projectsLoading}
              onSelectProject={(project) => {
                handleProjectSelect(project);
                setActiveTab('workspace');
              }}
              setShowCreateModal={setShowCreateModal}
              handleDeleteProject={handleDeleteProject}
            />
          )}

          {activeTab === 'workspace' && activeProject && (
            <Workspace
              API_BASE={API_BASE}
              activeProject={activeProject}
              activeProjectStatus={activeProjectStatus}
              chapters={chapters}
              activeChapter={activeChapter}
              workspaceStep={workspaceStep}
              setWorkspaceStep={setWorkspaceStep}
              editedOutline={editedOutline}
              setEditedOutline={setEditedOutline}
              editedTitle={editedTitle}
              setEditedTitle={setEditedTitle}
              editedContent={editedContent}
              setEditedContent={setEditedContent}
              savingOutline={savingOutline}
              savingContent={savingContent}
              writerSubTab={writerSubTab}
              setWriterSubTab={setWriterSubTab}
              validationResult={validationResult}
              customPrompt={customPrompt}
              setCustomPrompt={setCustomPrompt}
              outlineMode={outlineMode}
              setOutlineMode={setOutlineMode}
              wsLogs={wsLogs}
              streamingText={streamingText}
              loadChapterDetails={loadChapterDetails}
              handleDeleteChapter={handleDeleteChapter}
              openContinueModal={openContinueModal}
              handleSaveOutline={handleSaveOutline}
              handleSaveContent={handleSaveContent}
              handlePause={handlePause}
              handleResume={handleResume}
              handleRewriteChapter={handleRewriteChapter}
              handleInsertPrompt={handleInsertPrompt}
              handleForcePublish={handleForcePublish}
              isStuckWarning={isStuckWarning}
              settingsData={settingsData}
              currentFlowStep={currentFlowStep}
              streamingEvaluations={streamingEvaluations}
              validatorStreamLog={validatorStreamLog}
              onOpenChapterOverview={() => setShowOutlinesOverview(true)}
              actionLoading={actionLoading}
              autoFollowGeneration={autoFollowGeneration}
              setAutoFollowGeneration={setAutoFollowGeneration}
              runningChapter={activeProjectStatus?.latest_job_chapter}
            />
          )}

          {activeTab === 'docs' && activeProject && (
            <LivingDocs
              activeProject={activeProject}
              livingDocs={livingDocs}
              loadLivingDocs={loadLivingDocs}
              docVersions={docVersions}
              tokenStats={tokenStats}
              loadTokenStats={loadTokenStats}
              addLog={addLog}
              showToast={showToast}
            />
          )}

          {activeTab === 'settings' && (
            <Settings
               settingsData={settingsData}
               saveSettings={saveSettings}
               backendUrl={BACKEND_URL}
               saveBackendUrl={saveBackendUrl}
               activeProject={activeProject}
               activeProjectStatus={activeProjectStatus}
               onUpdateProjectConfig={handleUpdateProjectConfig}
            />
          )}

          {activeTab === 'system' && (
            <SystemConfigs />
          )}
        </Suspense>
      </AppShell>

      <CreateProjectModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSubmit={handleCreateProject}
        newProject={newProject}
        setNewProject={setNewProject}
        creating={creating}
      />

      <ContinueModal
        isOpen={showContinueModal}
        onClose={() => setShowContinueModal(false)}
        activeProject={activeProject}
        continueChaptersCount={continueChaptersCount}
        setContinueChaptersCount={setContinueChaptersCount}
        continueWordCount={continueWordCount}
        setContinueWordCount={setContinueWordCount}
        onSubmit={handleConfirmContinue}
        actionLoading={actionLoading}
        onUpdateProjectConfig={handleUpdateProjectConfig}
      />

      {showOutlinesOverview && (
        <ChapterOutlinesOverview
          project={activeProject}
          API_BASE={API_BASE}
          onClose={() => setShowOutlinesOverview(false)}
        />
      )}

      {/* O-06: Global Toast notification */}
      {toast && (
        <div className="toast-container">
          <div className={`toast toast-${toast.type}`}>
            {toast.message}
          </div>
        </div>
      )}
    </>
  );
}

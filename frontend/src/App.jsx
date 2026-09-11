import { lazy, Suspense, useState, useEffect, useRef } from 'react';
import { RefreshCw, AlertTriangle, Check, Eye, Crosshair } from 'lucide-react';
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
import useGenerationRealtime from './hooks/useGenerationRealtime';
import {
  DEFAULT_TARGET_CHAPTERS,
  DEFAULT_WORD_COUNT_PER_CHAPTER,
  createDefaultCreativeProfile,
} from './utils/constants';
const LivingDocs = lazy(() => import('./pages/LivingDocs'));
const Characters = lazy(() => import('./pages/Characters'));
const Settings = lazy(() => import('./pages/Settings'));
const SystemConfigs = lazy(() => import('./pages/SystemConfigs'));

export default function App() {
  const [activeTab, setActiveTab] = useState('shelf'); // shelf, workspace, docs, settings
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [autoFollowGeneration, setAutoFollowGeneration] = useState(true);
  const activeProject = useProjectStore((state) => state.activeProject);
  const setActiveProject = useProjectStore((state) => state.setActiveProject);
  const activeProjectStatus = useProjectStore((state) => state.activeProjectStatus);
  const setActiveProjectStatus = useProjectStore((state) => state.setActiveProjectStatus);
  const chapters = useProjectStore((state) => state.chapters);
  const setChapters = useProjectStore((state) => state.setChapters);
  const activeChapter = useProjectStore((state) => state.activeChapter);
  const setActiveChapter = useProjectStore((state) => state.setActiveChapter);

  // Creation States
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProject, setNewProject] = useState({
    title: '',
    author: '智能体作家',
    target_chapters: DEFAULT_TARGET_CHAPTERS,
    word_count_per_chapter: DEFAULT_WORD_COUNT_PER_CHAPTER,
    novel_format: 'long_webnovel',
    creative_profile: createDefaultCreativeProfile('long'),
    user_prompt: '',
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
  const workspaceStep = useUIStore((state) => state.workspaceStep);
  const setWorkspaceStep = useUIStore((state) => state.setWorkspaceStep); // planner, writer, validator
  const editedOutline = useProjectStore((state) => state.editedOutline);
  const setEditedOutline = useProjectStore((state) => state.setEditedOutline);
  const editedTitle = useProjectStore((state) => state.editedTitle);
  const setEditedTitle = useProjectStore((state) => state.setEditedTitle);
  const editedContent = useProjectStore((state) => state.editedContent);
  const setEditedContent = useProjectStore((state) => state.setEditedContent);
  const [savingOutline, setSavingOutline] = useState(false);
  const [savingContent, setSavingContent] = useState(false);
  const writerSubTab = useUIStore((state) => state.writerSubTab);
  const setWriterSubTab = useUIStore((state) => state.setWriterSubTab); // compare, draft, final
  const validationResult = useProjectStore((state) => state.validationResult);
  const setValidationResult = useProjectStore((state) => state.setValidationResult);
  const currentFlowStep = useProjectStore((state) => state.currentFlowStep);
  const setCurrentFlowStep = useProjectStore((state) => state.setCurrentFlowStep);
  const outlineMode = useUIStore((state) => state.outlineMode);
  const setOutlineMode = useUIStore((state) => state.setOutlineMode); // 'visual' | 'json'

  // Streaming/WebSockets
  const wsLogs = useProjectStore((state) => state.wsLogs);
  const setWsLogs = useProjectStore((state) => state.setWsLogs);
  const chaptersFetchSeqRef = useRef(0);
  const chapterDetailsFetchSeqRef = useRef(0);
  const chaptersDebounceRef = useRef(null);
  const abortControllerRef = useRef(null);
  const lastPolledJobRef = useRef({ step: '', chapter: 0 });
  const initialProjectParamRef = useRef(null);
  const deepLinkConsumedRef = useRef(false);

  // F-07: Keep latest activeProject in a ref for realtime callbacks
  const activeProjectRef = useRef(activeProject);
  activeProjectRef.current = activeProject;

  // Keep latest autoFollowGeneration in a ref: realtime callbacks / loadProjectStatus
  // are captured once by the single WS binding and by poll closures, so reading the
  // raw state there is stale. The ref always reflects the current toggle value.
  const autoFollowGenerationRef = useRef(autoFollowGeneration);
  autoFollowGenerationRef.current = autoFollowGeneration;

  const setStreamingEvaluations = useProjectStore((state) => state.setStreamingEvaluations);
  const setValidatorStreamLog = useProjectStore((state) => state.setValidatorStreamLog);

  // Continue writing config modal states
  const [showContinueModal, setShowContinueModal] = useState(false);
  const [showOutlinesOverview, setShowOutlinesOverview] = useState(false);
  const [continueChaptersCount, setContinueChaptersCount] = useState(1);
  const [continueWordCount, setContinueWordCount] = useState(3000);

  const backendStatus = useBackendHealth();

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

  const MAX_WS_LOGS = 500;
  const addLog = (source, message, styleClass = '') => {
    const timeStr = new Date().toLocaleTimeString();
    setWsLogs((prev) => {
      const next = [...prev, { time: timeStr, source, text: message, styleClass }];
      return next.length > MAX_WS_LOGS ? next.slice(next.length - MAX_WS_LOGS) : next;
    });
  };

  const {
    loadProjects,
    loadProjectStatus,
    loadChapters,
    scheduleLoadChapters,
    ensureChapterInList,
    loadChapterDetails,
    loadSettings,
    saveSettings,
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
    setSettingsData,
  });

  const { isWsConnected, isStuckWarning, streamingText, streamingEvaluations, validatorStreamLog } =
    useGenerationRealtime({
      projectId: activeProject?.id,
      activeProjectStatus,
      settingsData,
      activeProjectRef,
      autoFollowGenerationRef,
      abortControllerRef,
      chaptersDebounceRef,
      addLog,
      showToast,
      loadProjects,
      loadProjectStatus,
      loadChapters,
      scheduleLoadChapters,
      ensureChapterInList,
      loadChapterDetails,
      setActiveTab,
      setChapters,
      setActiveChapter,
      setCurrentFlowStep,
      setEditedOutline,
      setEditedContent,
      setOutlineMode,
      setWorkspaceStep,
      setWriterSubTab,
      setValidationResult,
      setValidatorStreamLog,
      setStreamingEvaluations,
    });

  const {
    handlePause,
    handleResume,
    handleForcePublish,
    handleProjectSelect,
    handleCreateProject,
    handleDeleteProject,
    openContinueModal,
    handleConfirmContinue,
    handleUpdateProjectConfig,
    handleRewriteChapter,
    handleRewriteOutline,
    handleDeleteChapter,
    handleSaveOutline,
    handleSaveContent,
  } = useGenerationActions({
    project: { activeProject, activeChapter, newProject },
    editor: { editedOutline, editedContent, editedTitle },
    generation: { continueChaptersCount, continueWordCount },
    services: {
      addLog,
      showToast,
      loadProjects,
      loadProjectStatus,
      loadChapters,
      loadChapterDetails,
    },
    setters: {
      setAutoFollowGeneration,
      setActiveChapter,
      setEditedOutline,
      setChapters,
      setWorkspaceStep,
      setOutlineMode,
      setActiveProject,
      setCreating,
      setShowCreateModal,
      setNewProject,
      setActiveTab,
      setProjects,
      setActionLoading,
      setShowContinueModal,
      setContinueChaptersCount,
      setContinueWordCount,
      setValidationResult,
      setStreamingEvaluations,
      setValidatorStreamLog,
      setEditedContent,
      setSavingOutline,
      setSavingContent,
    },
  });

  const getStatusText = () => {
    if (!activeProjectStatus) return '';
    if (activeProjectStatus.status === 'paused') {
      if (activeProjectStatus.await_outline_review) {
        return '等待大纲审阅';
      }
      if (chapters && chapters.some((ch) => ch.status === 'pending_review')) {
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
        case 'planner':
          return '大纲策划中';
        case 'writer':
          return '撰写初稿中';
        case 'editor':
          return '审阅润色中';
        case 'validator':
          return '天道审计中';
        case 'extractor':
          return '设定提取中';
        case 'system':
          return '后台扫描中';
        default:
          return 'AI创作流进行中';
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
        headerActions={
          <>
            {activeTab === 'workspace' && activeProjectStatus && (
              <StatusBadge
                status={activeProjectStatus.status}
                label={getStatusText()}
                pulse={activeProjectStatus.status === 'generating'}
              />
            )}
            {activeTab === 'workspace' &&
              activeProjectStatus?.status === 'paused' &&
              (activeProjectStatus.await_outline_review ||
                (chapters && chapters.some((ch) => ch.status === 'pending_review'))) && (
                <button
                  className="btn btn-review"
                  onClick={() => {
                    setActiveTab('workspace');
                    if (activeProjectStatus.await_outline_review) {
                      setWorkspaceStep('structure');
                      setActiveChapter(null);
                    } else {
                      const pendingCh = chapters.find((ch) => ch.status === 'pending_review');
                      if (pendingCh) {
                        loadChapterDetails(activeProject.id, pendingCh.chapter_index);
                      }
                    }
                  }}
                >
                  <Eye size={14} /> 前往审阅
                </button>
              )}
            {activeTab === 'workspace' &&
              activeProjectStatus?.status === 'failed' &&
              activeProjectStatus?.latest_job_error && (
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
                title={
                  autoFollowGeneration
                    ? '正在跟随生成中的章节；点击后停止自动跳转'
                    : '已停止自动跟随；点击后回到生成中的章节'
                }
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
        }
      >
        <Suspense
          fallback={
            <div className="page-loading">
              <RefreshCw className="animate-spin" size={18} /> 正在载入页面
            </div>
          }
        >
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
              handleRewriteOutline={handleRewriteOutline}
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
            // 这一页只剩知识图谱视图（活文档服务已移除），原先传的
            // tokenStats / loadTokenStats / addLog / showToast 都已无人读取，
            // 成本统计的前后端也一并删掉了。TokenUsage 表仍在写入，但只作为
            // 排查用的原始记录，前端不再读它。
            <LivingDocs activeProject={activeProject} />
          )}

          {activeTab === 'characters' && activeProject && (
            <Characters activeProject={activeProject} showToast={showToast} />
          )}

          {activeTab === 'settings' && (
            <Settings
              settingsData={settingsData}
              saveSettings={saveSettings}
              activeProject={activeProject}
              activeProjectStatus={activeProjectStatus}
              onUpdateProjectConfig={handleUpdateProjectConfig}
            />
          )}

          {activeTab === 'system' && <SystemConfigs />}
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
        <ChapterOutlinesOverview project={activeProject} onClose={() => setShowOutlinesOverview(false)} />
      )}

      {/* O-06: Global Toast notification */}
      {toast && (
        <div className="toast-container">
          <div className={`toast toast-${toast.type}`}>{toast.message}</div>
        </div>
      )}
    </>
  );
}

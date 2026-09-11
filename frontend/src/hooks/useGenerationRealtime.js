import { useEffect, useRef } from 'react';

import { useProjectStore } from '../store/useStore';
import useProjectRealtime, { shouldApplyChapterStreaming } from './useProjectRealtime';
import { issuesToValidationResult } from '../utils/streamingJsonParser';
import {
  agentStyleClass,
  createPendingStreamUpdates,
  isWatchdogTimedOut,
  ROUTED_STREAM_AGENTS,
} from '../utils/streamingRuntime';

export default function useGenerationRealtime({
  projectId,
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
}) {
  const streamingText = useProjectStore((state) => state.streamingText);
  const setStreamingText = useProjectStore((state) => state.setStreamingText);
  const isStuckWarning = useProjectStore((state) => state.isStuckWarning);
  const setIsStuckWarning = useProjectStore((state) => state.setIsStuckWarning);
  const streamingEvaluations = useProjectStore((state) => state.streamingEvaluations);
  const validatorStreamLog = useProjectStore((state) => state.validatorStreamLog);

  const lastWsMessageTimeRef = useRef(Date.now());
  const previousProjectStatusRef = useRef(activeProjectStatus?.status);
  const pollInFlightRef = useRef(false);
  const refreshDebounceRef = useRef(null);
  const pendingStreamUpdatesRef = useRef(createPendingStreamUpdates());
  const rafScheduledRef = useRef(false);

  const resetPendingStreamUpdates = () => {
    rafScheduledRef.current = false;
    pendingStreamUpdatesRef.current = createPendingStreamUpdates();
  };

  const flushStreamUpdates = () => {
    rafScheduledRef.current = false;
    const pending = pendingStreamUpdatesRef.current;

    if (pending.text) {
      setStreamingText((previous) =>
        previous.agent === pending.textAgent
          ? { agent: pending.textAgent, text: previous.text + pending.text }
          : { agent: pending.textAgent, text: pending.text },
      );
    }
    if (pending.outline) {
      setEditedOutline((previous) => previous + pending.outline);
    }
    if (pending.writerText) {
      setActiveChapter((previous) => {
        if (previous && previous.chapter_index === pending.writerChapterIndex) {
          return {
            ...previous,
            draft_content: (previous.draft_content || '') + pending.writerText,
          };
        }
        return previous;
      });
    }
    if (pending.editorContent) {
      setEditedContent((previous) => previous + pending.editorContent);
    }
    if (pending.evaluations) {
      setStreamingEvaluations((previous) => ({ ...(previous || {}), ...pending.evaluations }));
    }
    if (pending.validatorLog) {
      setValidatorStreamLog((previous) => previous + pending.validatorLog);
    }
    if (pending.validationResult) {
      setValidationResult(pending.validationResult);
    }

    pendingStreamUpdatesRef.current = createPendingStreamUpdates();
  };

  const scheduleStreamFlush = () => {
    if (!rafScheduledRef.current) {
      rafScheduledRef.current = true;
      requestAnimationFrame(flushStreamUpdates);
    }
  };

  const resetWatchdog = () => {
    lastWsMessageTimeRef.current = Date.now();
    setIsStuckWarning(false);
  };

  useEffect(() => {
    const status = activeProjectStatus?.status;
    if (status === 'generating' && previousProjectStatusRef.current !== 'generating') {
      resetWatchdog();
    }
    previousProjectStatusRef.current = status;
  }, [activeProjectStatus?.status, projectId]);

  useEffect(() => {
    const interval = setInterval(() => {
      const isGenerating = activeProjectStatus?.status === 'generating';
      if (!isGenerating) {
        setIsStuckWarning(false);
        return;
      }
      const timeoutSec = settingsData?.watchdog_timeout || 45;
      setIsStuckWarning(
        isWatchdogTimedOut({
          isGenerating,
          lastMessageAt: lastWsMessageTimeRef.current,
          now: Date.now(),
          timeoutSec,
        }),
      );
    }, 1000);
    return () => clearInterval(interval);
  }, [activeProjectStatus, settingsData, setIsStuckWarning]);

  useEffect(() => {
    if (!projectId || activeProjectStatus?.status !== 'generating') return undefined;

    const poll = async () => {
      if (pollInFlightRef.current) return;
      pollInFlightRef.current = true;
      const signal = abortControllerRef.current?.signal;
      try {
        await loadProjectStatus(projectId, { fromPoll: true, signal });
        await loadChapters(projectId, { signal });
        await loadProjects({ silent: true });
      } finally {
        pollInFlightRef.current = false;
      }
    };

    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [projectId, activeProjectStatus?.status]);

  useEffect(() => {
    resetWatchdog();
    setCurrentFlowStep('');
    setChapters([]);
    setActiveChapter(null);
    if (abortControllerRef.current) abortControllerRef.current.abort();
    abortControllerRef.current = new AbortController();
    const { signal } = abortControllerRef.current;

    if (projectId) {
      loadChapters(projectId, { replace: true, signal });
      loadProjectStatus(projectId, { signal });
    }

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      if (chaptersDebounceRef.current) clearTimeout(chaptersDebounceRef.current);
      if (refreshDebounceRef.current) {
        clearTimeout(refreshDebounceRef.current);
        refreshDebounceRef.current = null;
      }
      resetPendingStreamUpdates();
    };
  }, [projectId]);

  const handleMessage = (message) => {
    const project = activeProjectRef.current;
    if (!project) return;

    lastWsMessageTimeRef.current = Date.now();
    setIsStuckWarning(false);

    if (message.type === 'log') {
      addLog(message.source || '系统', message.message || message.text, agentStyleClass(message.source));
      if (message.message && ['优化', '完成', '中断'].some((keyword) => message.message.includes(keyword))) {
        if (refreshDebounceRef.current) clearTimeout(refreshDebounceRef.current);
        refreshDebounceRef.current = setTimeout(() => {
          refreshDebounceRef.current = null;
          loadChapters(project.id);
          loadProjectStatus(project.id);
          loadProjects();
        }, 2000);
      }
      return;
    }

    if (message.type === 'status') {
      addLog(message.step || '系统', message.message, `agent-${message.step}`);
      setCurrentFlowStep(message.step);

      if (autoFollowGenerationRef.current && ['planner', 'writer', 'editor', 'validator'].includes(message.step)) {
        setActiveTab('workspace');
      }
      if (message.step === 'editor') {
        resetEditorParsers();
      } else if (message.step === 'validator') {
        resetValidatorParser();
      }

      if (autoFollowGenerationRef.current && message.step === 'planner') {
        setWorkspaceStep('planner');
        setOutlineMode('json');
        if (message.chapter !== 0) setEditedOutline('');
      } else if (autoFollowGenerationRef.current && message.step === 'writer') {
        setOutlineMode('visual');
        setWorkspaceStep('writer');
        setWriterSubTab('draft');
        setActiveChapter((previous) =>
          previous && previous.chapter_index === message.chapter ? { ...previous, draft_content: '' } : previous,
        );
      } else if (autoFollowGenerationRef.current && message.step === 'editor') {
        setWorkspaceStep('writer');
        setWriterSubTab('evaluations');
        setEditedContent('');
        setStreamingEvaluations(null);
      } else if (autoFollowGenerationRef.current && message.step === 'validator') {
        setWorkspaceStep('validator');
        setValidatorStreamLog('');
        setValidationResult({
          errors: [],
          warnings: [],
          infos: [],
          story_issues: [],
          streaming: true,
          passed: null,
        });
      } else if (message.step === 'extractor') {
        setStreamingEvaluations(null);
      }

      if (message.chapter && message.chapter > 0) {
        ensureChapterInList(message.chapter);
        if (autoFollowGenerationRef.current && message.step === 'editor') {
          loadChapterDetails(project.id, message.chapter, {
            preserveContent: true,
            preserveOutline: true,
          });
        } else if (autoFollowGenerationRef.current && message.step === 'validator') {
          loadChapterDetails(project.id, message.chapter, {
            preserveValidation: true,
            preserveOutline: true,
            preserveContent: true,
          });
        } else if (autoFollowGenerationRef.current && message.step !== 'planner') {
          loadChapterDetails(project.id, message.chapter);
        }
      }

      scheduleLoadChapters(project.id);
      loadProjectStatus(project.id);
      loadProjects();
      return;
    }

    if (message.type === 'chunk') {
      const pending = pendingStreamUpdatesRef.current;
      if (!ROUTED_STREAM_AGENTS.has(message.agent)) {
        if (pending.textAgent && pending.textAgent !== message.agent) {
          flushStreamUpdates();
          const next = pendingStreamUpdatesRef.current;
          next.textAgent = message.agent;
          next.text = message.text;
        } else {
          pending.textAgent = message.agent;
          pending.text += message.text;
        }
        scheduleStreamFlush();
      }

      const activeChapterIndex = useProjectStore.getState().activeChapter?.chapter_index;
      const shouldApply = shouldApplyChapterStreaming(
        autoFollowGenerationRef.current,
        message.chapter_index,
        activeChapterIndex,
      );

      if (message.agent === 'planner') {
        if (message.phase !== 'reasoning') {
          if (shouldApply) pending.outline += message.text;
          setOutlineMode('json');
        }
      } else if (message.agent === 'writer') {
        pending.writerChapterIndex = message.chapter_index;
        if (message.phase !== 'reasoning' && shouldApply) pending.writerText += message.text;
      } else if (message.agent === 'editor') {
        if (message.phase !== 'reasoning') {
          const parsed = appendEditorChunk(message.text);
          if (parsed.content && shouldApply) pending.editorContent += parsed.content;
          if (parsed.evaluations && shouldApply) {
            pending.evaluations = { ...(pending.evaluations || {}), ...parsed.evaluations };
          }
        }
      } else if (message.agent === 'validator') {
        if (shouldApply) pending.validatorLog += message.text;
        if (message.phase === 'llm' || message.phase === 'streaming') {
          const { issues, passed } = appendValidatorChunk(message.text);
          if (shouldApply && (issues.length > 0 || passed !== null)) {
            pending.validationResult = issuesToValidationResult(issues, passed);
          }
        }
      }
      scheduleStreamFlush();
      return;
    }

    if (message.type === 'warning') {
      addLog('校验器', `[警报] ${message.message}`, 'agent-validator');
      return;
    }

    if (message.type === 'error') {
      const messageText = message.message || '未知错误';
      const looksRecoverableJsonError = /JSON格式校验|Schema验证|Failed to parse JSON response/i.test(messageText);
      addLog(
        '系统',
        looksRecoverableJsonError ? `[自动修复重试] ${messageText}` : `[异常] ${messageText}`,
        looksRecoverableJsonError ? 'warning' : 'error',
      );
      loadProjectStatus(project.id);
      loadChapters(project.id);
      loadProjects();
    }
  };

  const {
    isConnected: isWsConnected,
    appendEditorChunk,
    appendValidatorChunk,
    resetEditorParsers,
    resetValidatorParser,
  } = useProjectRealtime({
    projectId,
    onMessage: handleMessage,
    onOpen: (connectedProjectId) => {
      resetWatchdog();
      addLog('系统', 'WebSocket 创作链路已成功连接', 'system');
      loadProjectStatus(connectedProjectId);
      loadChapters(connectedProjectId);
      loadProjects();
    },
    onLog: addLog,
    onError: (error, source) => {
      console.error(error);
      showToast(source === 'parse' ? 'WebSocket 消息解析失败' : 'WebSocket 连接出错，正在尝试重连...', 'warning');
    },
  });

  return {
    isWsConnected,
    isStuckWarning,
    streamingText,
    streamingEvaluations,
    validatorStreamLog,
  };
}

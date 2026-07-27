import { useProjectStore } from '../store/useStore';
import { API_BASE, requestJson } from '../services/api';

export default function useProjectData({
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
}) {
const loadProjects = async ({ silent = false } = {}) => {
  if (!silent) setProjectsLoading(true);
  try {
    const data = await requestJson('/writing/projects');
    setProjects(data);
    setActiveProject(prev => {
      if (prev) {
        const updated = data.find(p => p.id === prev.id);
        return updated || prev;
      }
      return prev;
    });
  } catch (e) {
    addLog('系统', `加载项目失败: ${e.message}`, 'error');
  } finally {
    if (!silent) setProjectsLoading(false);
  }
};

const loadProjectStatus = async (id, { fromPoll = false, signal } = {}) => {
  try {
    const data = await requestJson(`/writing/${id}/status`, { signal });
      // Compare prev status with data BEFORE the updater — avoid side effects inside setState.
      // Read from the store (not the captured state) since this runs from poll/WS closures.
      const prevStatus = useProjectStore.getState().activeProjectStatus;
      if (prevStatus && prevStatus.status !== data.status) {
        let statusText = '';
        if (data.status === 'generating') statusText = 'AI 创作流开始运行';
        else if (data.status === 'paused') statusText = '创作流已暂停';
        else if (data.status === 'completed') statusText = '创作已全部完结';
        else if (data.status === 'failed') statusText = '创作流发生异常中断';

        if (statusText) {
          addLog('系统', `【状态变更】${statusText}`, 'system');
        }
        if (prevStatus.status === 'generating') {
          setOutlineMode('visual');
        }
      }
      setActiveProjectStatus(data);
      if (data.status === 'generating' && data.latest_job_step) {
        setCurrentFlowStep(data.latest_job_step);
      }
      if (fromPoll && data.latest_job_chapter && autoFollowGenerationRef.current) {
        const step = data.latest_job_step || '';
        const chapter = data.latest_job_chapter;
        const prev = lastPolledJobRef.current;
        if (step !== prev.step || chapter !== prev.chapter) {
          lastPolledJobRef.current = { step, chapter };
          ensureChapterInList(chapter);
          if (step === 'editor') {
            loadChapterDetails(id, chapter, { preserveContent: true, preserveOutline: true });
          } else if (step === 'validator') {
            loadChapterDetails(id, chapter, { preserveValidation: true, preserveOutline: true, preserveContent: true });
          } else if (step && step !== 'planner') {
            loadChapterDetails(id, chapter);
          }
        }
      }
      setActiveProject((prev) =>
        prev && prev.id === id
          ? {
              ...prev,
              current_chapter: data.current_chapter ?? prev.current_chapter,
              total_chapters: data.total_chapters ?? prev.total_chapters,
              total_chars: data.total_chars ?? prev.total_chars,
              status: data.status ?? prev.status,
              target_chapters: data.target_chapters ?? prev.target_chapters,
              mode: data.mode ?? prev.mode,
              word_count_per_chapter: data.word_count_per_chapter ?? prev.word_count_per_chapter,
              optimize_interval: data.optimize_interval ?? prev.optimize_interval,
            }
          : prev
      );
      setProjects((prev) =>
        prev.map((p) =>
          p.id === id
            ? {
                ...p,
                current_chapter: data.current_chapter ?? p.current_chapter,
                total_chapters: data.total_chapters ?? p.total_chapters,
                total_chars: data.total_chars ?? p.total_chars,
                status: data.status ?? p.status,
                target_chapters: data.target_chapters ?? p.target_chapters,
                mode: data.mode ?? p.mode,
                word_count_per_chapter: data.word_count_per_chapter ?? p.word_count_per_chapter,
                optimize_interval: data.optimize_interval ?? p.optimize_interval,
              }
            : p
        )
      );
  } catch (e) {
    // F-22: Silently ignore aborted fetches from project switching
    if (e.name === 'AbortError') return;
    console.error(e);
    showToast('加载项目状态失败');
  }
};

const loadChapters = async (id, { replace = false, signal } = {}) => {
  const seq = ++chaptersFetchSeqRef.current;
  try {
    const data = await requestJson(`/writing/${id}/chapters`, { signal });
    if (seq !== chaptersFetchSeqRef.current) return;
    setChapters((prev) => {
      if (replace || prev.length === 0) return data;
      const map = new Map();
      for (const ch of prev) map.set(ch.chapter_index, ch);
      for (const ch of data) {
        map.set(ch.chapter_index, { ...map.get(ch.chapter_index), ...ch });
      }
      return Array.from(map.values()).sort((a, b) => a.chapter_index - b.chapter_index);
    });
  } catch (e) {
    // F-22: Silently ignore aborted fetches from project switching
    if (e.name === 'AbortError') return;
    console.error(e);
    showToast('加载章节列表失败');
  }
};

const scheduleLoadChapters = (id, delayMs = 500) => {
  if (chaptersDebounceRef.current) clearTimeout(chaptersDebounceRef.current);
  chaptersDebounceRef.current = setTimeout(() => {
    chaptersDebounceRef.current = null;
    loadChapters(id);
  }, delayMs);
};

const ensureChapterInList = (chapterIndex) => {
  if (!chapterIndex || chapterIndex <= 0) return;
  setChapters((prev) => {
    if (prev.some((ch) => ch.chapter_index === chapterIndex)) return prev;
    return [
      ...prev,
      { chapter_index: chapterIndex, title: `第${chapterIndex}章`, status: 'draft' },
    ].sort((a, b) => a.chapter_index - b.chapter_index);
  });
};

const loadChapterDetails = async (projectId, chapterIndex, options = {}) => {
  let { preserveOutline = false, preserveContent = false, preserveValidation = false, signal } = options;

  const currentStatus = activeProjectRef.current?.status;
  const currentStep = useProjectStore.getState().currentFlowStep;
  if (currentStatus === 'generating') {
    if (currentStep === 'planner') preserveOutline = true;
    if (currentStep === 'writer' || currentStep === 'editor') preserveContent = true;
    if (currentStep === 'validator') preserveValidation = true;
  }

  // Guard against out-of-order responses: a rapid chapter switch (5 -> 6) must
  // not let the slower chapter-5 response overwrite the chapter-6 view.
  const seq = ++chapterDetailsFetchSeqRef.current;
  try {
    const data = await requestJson(`/writing/${projectId}/chapters/${chapterIndex}`, { signal });
      if (seq !== chapterDetailsFetchSeqRef.current) return;
      const previous = useProjectStore.getState().activeChapter;
      const isSameChapter = previous?.chapter_index === chapterIndex;
      const shouldPreserveContent = preserveContent && isSameChapter;
      const shouldPreserveOutline = preserveOutline && isSameChapter;
      const shouldPreserveValidation = preserveValidation && isSameChapter;
      const nextChapter = (() => {
        if (shouldPreserveContent) {
          return {
            ...data,
            draft_content: previous.draft_content || data.draft_content,
            edited_content: previous.edited_content || data.edited_content
          };
        }
        return data;
      })();

      setActiveChapter(nextChapter);

      setEditedTitle(nextChapter.title || '');
      if (!shouldPreserveContent) {
        setEditedContent(nextChapter.edited_content || nextChapter.content || nextChapter.draft_content || '');
      }
      if (!shouldPreserveOutline) {
        setEditedOutline(data.outline ? JSON.stringify(data.outline, null, 2) : '');
      }
      if (!shouldPreserveValidation) {
        setValidationResult(data.validator_result);
        setValidatorStreamLog('');
        setStreamingEvaluations(null);
      }
  } catch (e) {
    // Silently ignore aborted fetches from project switching
    if (e.name === 'AbortError') return;
    console.error(e);
    showToast('加载章节详情失败');
  }
};

const loadLivingDocs = async (id) => {
  try {
    const [data, versions] = await Promise.all([
      requestJson(`/writing/${id}/living-docs`),
      requestJson(`/writing/${id}/living-docs/versions`),
    ]);
    setLivingDocs(data);
    setDocVersions(versions);
  } catch (e) {
    console.error(e);
    showToast('加载活文档设定失败');
  }
};

const loadSettings = async () => {
  try {
    setSettingsData(await requestJson('/settings'));
  } catch (e) {
    console.error(e);
    showToast('加载设置失败');
  }
};

const saveSettings = async (newData) => {
  try {
    const saved = await requestJson('/settings', {
      method: 'POST',
      body: JSON.stringify(newData)
    });
    setSettingsData(saved || newData);
    showToast('设置已保存', 'success');
  } catch (e) {
    showToast(`保存失败: ${e.message}`);
  }
};

const loadTokenStats = async (id, modelName = 'All Models') => {
  try {
    let url = `${API_BASE}/writing/${id}/token-stats`;
    if (modelName !== 'All Models') {
      url += `?model=${encodeURIComponent(modelName)}`;
    }
    setTokenStats(await requestJson(url));
  } catch (e) {
    console.error(e);
    showToast('加载 Token 统计失败');
  }
};
  return {
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
  };
}

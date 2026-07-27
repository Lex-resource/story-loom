import { chapterApi, outlineApi, pipelineApi, projectApi } from '../services/novelApi';
import { DEFAULT_TARGET_CHAPTERS, DEFAULT_WORD_COUNT_PER_CHAPTER, createDefaultCreativeProfile } from '../utils/constants';

export default function useGenerationActions({ project, editor, generation, services, setters }) {
const { activeProject, activeChapter, newProject } = project;
const { customPrompt, editedOutline, editedContent, editedTitle } = editor;
const { continueChaptersCount, continueWordCount } = generation;
const { addLog, showToast, loadProjects, loadProjectStatus, loadChapters, loadChapterDetails, loadLivingDocs } = services;
const {
  setAutoFollowGeneration, setCustomPrompt, setActiveChapter, setEditedOutline, setChapters,
  setWorkspaceStep, setOutlineMode, setActiveProject, setCreating, setShowCreateModal, setNewProject,
  setActiveTab, setProjects, setActionLoading, setShowContinueModal, setContinueChaptersCount,
  setContinueWordCount, setValidationResult, setStreamingEvaluations, setValidatorStreamLog,
  setEditedContent, setSavingOutline, setSavingContent,
} = setters;
const handlePause = async () => {
  if (!activeProject) return;
  try {
    await pipelineApi.pause(activeProject.id);
    await loadProjectStatus(activeProject.id);
    await loadChapters(activeProject.id);
  } catch (e) {
    showToast(`暂停失败: ${e.message}`);
  }
};

const handleResume = async () => {
  if (!activeProject) return;
  setAutoFollowGeneration(true);
  try {
    await pipelineApi.resume(activeProject.id);
    await loadProjectStatus(activeProject.id);
    await loadChapters(activeProject.id);
  } catch (e) {
    showToast(`继续失败: ${e.message}`);
  }
};

const handleInsertPrompt = async () => {
  if (activeProject && customPrompt.trim()) {
    try {
      await pipelineApi.intervene(activeProject.id, customPrompt.trim());
      addLog('系统', '人工指令已保存，将由创作任务在下一安全检查点读取。', 'system');
    } catch (e) {
      showToast(`发送人工指令失败: ${e.message}`);
      return;
    }
    setCustomPrompt('');
  }
};

const handleForcePublish = async (chapterIndex) => {
  if (!activeProject) return;
  try {
    await chapterApi.publish(activeProject.id, chapterIndex);
    addLog('系统', `第 ${chapterIndex} 章已被用户强制发布（忽略法则矛盾）！正在准备继续创作流程。`, 'system');
    await loadChapters(activeProject.id);
    await loadProjectStatus(activeProject.id);
  } catch (e) {
    showToast(e.message);
  }
};

// API Call helper
const handleProjectSelect = async (project) => {
  setAutoFollowGeneration(true);
  setActiveChapter(null);
  setEditedOutline('');
  setChapters([]);
  setWorkspaceStep('structure');
  setOutlineMode('visual');
  setActiveProject(project);
  if (project?.id) {
    const url = new URL(window.location.href);
    url.searchParams.set('project', project.id);
    window.history.replaceState(null, '', url);
  }
  // The useEffect will handle loadProjectStatus, loadChapters, loadLivingDocs when activeProject changes
};

const handleCreateProject = async (e) => {
  e.preventDefault();
  if (!newProject.title?.trim() || !newProject.user_prompt?.trim()) {
    showToast('请填写书名和世界观立意', 'warning');
    return;
  }
  setCreating(true);
  try {
    const data = await projectApi.create(newProject);
      setShowCreateModal(false);
      setNewProject({
        title: '',
        author: '智能体作家',
        target_chapters: DEFAULT_TARGET_CHAPTERS,
        word_count_per_chapter: DEFAULT_WORD_COUNT_PER_CHAPTER,
        novel_format: 'long_webnovel',
        creative_profile: createDefaultCreativeProfile('long'),
        user_prompt: '',
      });
      await loadProjects();
      const freshData = await projectApi.list();
      const created = freshData.find((p) => p.id === data.project_id);
      if (created) {
        setActiveProject(created);
        setActiveTab('workspace');
        loadProjectStatus(created.id);
        loadChapters(created.id);
      }
  } catch (e) {
    showToast(`创建失败: ${e.message}`);
  } finally {
    setCreating(false);
  }
};

const handleDeleteProject = async (id, e) => {
  e.stopPropagation();
  if (confirm('确认删除此项目？所有数据及活文档都将被彻底抹除且不可恢复！')) {
    try {
      await projectApi.remove(id);
      if (activeProject?.id === id) setActiveProject(null);
      loadProjects();
    } catch (err) {
      showToast(err.message);
    }
  }
};

const handleStartGenerate = async (batchSize = 1, wordCount = 3000) => {
  if (!activeProject) return;
  setAutoFollowGeneration(true);
  setActionLoading(true);
  try {
    await pipelineApi.generate(activeProject.id, {
      batch_size: parseInt(batchSize) || 1,
      word_count_per_chapter: (wordCount !== undefined && wordCount !== null) ? parseInt(wordCount) : 3000,
    });
    addLog('系统', `已成功启动续写任务（续写 ${batchSize} 章，单章目标 ${wordCount > 0 ? wordCount + ' 字' : '无限制'}）。准备拉起大纲策划与创作...`, 'system');
    loadProjectStatus(activeProject.id);
  } catch (e) {
    console.error(e);
    showToast(`启动续写失败: ${e.message}`);
  } finally {
    setActionLoading(false);
  }
};

const openContinueModal = () => {
  if (activeProject) {
    setContinueWordCount(activeProject.word_count_per_chapter !== undefined ? activeProject.word_count_per_chapter : DEFAULT_WORD_COUNT_PER_CHAPTER);
    setContinueChaptersCount(1);
  }
  setShowContinueModal(true);
};

const handleConfirmContinue = () => {
  setShowContinueModal(false);
  handleStartGenerate(continueChaptersCount, continueWordCount);
};

const handleUpdateProjectConfig = async (config) => {
  if (!activeProject) return false;
  try {
    await projectApi.updateConfig(activeProject.id, {
      word_count_per_chapter: config.word_count_per_chapter,
      mode: config.mode,
      optimize_interval: config.optimize_interval,
      target_chapters: config.target_chapters,
    });
    showToast('项目设置已成功更新！', 'success');
    await loadProjectStatus(activeProject.id);
    await loadProjects();
    return true;
  } catch (e) {
    console.error(e);
    showToast(`保存设置失败: ${e.message}`);
    return false;
  }
};

const handleRewriteChapter = async () => {
  if (!activeProject || !activeChapter) return;
  setAutoFollowGeneration(true);
  setActionLoading(true);
  try {
    await pipelineApi.rewrite(activeProject.id, {
      use_existing_outline: true,
      custom_prompt: customPrompt || null,
      chapter_index: activeChapter.chapter_index,
    });
    addLog('系统', `已对第 ${activeChapter.chapter_index} 章发起重写请求...`, 'system');
    setCustomPrompt('');
    setEditedContent('');
    setValidationResult({ errors: [], warnings: [], infos: [], story_issues: [], streaming: false, passed: null });
    setValidatorStreamLog('');
    setStreamingEvaluations(null);
    loadProjectStatus(activeProject.id);
    loadChapterDetails(activeProject.id, activeChapter.chapter_index);
    loadChapters(activeProject.id);
  } catch (e) {
    console.error(e);
    showToast(`重写请求失败: ${e.message}`);
  } finally {
    setActionLoading(false);
  }
};

const handleDeleteChapter = async (chapterIndex, e) => {
  if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
  if (confirm(`确认要删除第 ${chapterIndex} 章吗？删除后后续所有章节将自动往前重排！`)) {
    try {
      const data = await chapterApi.remove(activeProject.id, chapterIndex);
        const written = data.written_count ?? data.current_chapter ?? 0;
        const totalChars = data.total_chars ?? 0;
        setActiveChapter(null);
        loadChapters(activeProject.id, { replace: true });
        loadProjectStatus(activeProject.id);
        loadLivingDocs(activeProject.id);
        setActiveProject((prev) =>
          prev && prev.id === activeProject.id
            ? {
                ...prev,
                current_chapter: written,
                total_chapters: written,
                total_chars: totalChars,
              }
            : prev
        );
        setProjects((prev) =>
          prev.map((p) =>
            p.id === activeProject.id
              ? {
                  ...p,
                  current_chapter: written,
                  total_chapters: written,
                  total_chars: totalChars,
                }
              : p
          )
        );
        loadProjects();
      addLog('系统', `已删除第 ${chapterIndex} 章，当前共 ${written} 章`, 'system');
    } catch (err) {
      showToast(err.message);
    }
  }
};

const handleSaveOutline = async () => {
  if (!activeProject) return;

  if (!activeChapter) {
    // Saving skeleton outline
    setSavingOutline(true);
    try {
      const outlineObj = JSON.parse(editedOutline);
      await outlineApi.update(activeProject.id, outlineObj);
      addLog('系统', `全书骨架大纲修改成功并同步。`, 'system');
      loadProjectStatus(activeProject.id);
    } catch (e) {
      showToast(`JSON 格式有误: ${e.message}`, 'warning');
    } finally {
      setSavingOutline(false);
    }
    return;
  }

  // Saving chapter outline
  setSavingOutline(true);
  try {
    const outlineObj = JSON.parse(editedOutline);
    await chapterApi.updateOutline(activeProject.id, activeChapter.chapter_index, outlineObj);
    addLog('系统', `第 ${activeChapter.chapter_index} 章大纲修改成功并同步。`, 'system');
    loadChapterDetails(activeProject.id, activeChapter.chapter_index);
    loadChapters(activeProject.id);
  } catch (e) {
    showToast(`JSON 格式有误: ${e.message}`, 'warning');
  } finally {
    setSavingOutline(false);
  }
};

const handleSaveContent = async () => {
  if (!activeProject || !activeChapter) return;
  const contentToSave = editedContent || activeChapter.edited_content || activeChapter.content || activeChapter.draft_content || '';
  setSavingContent(true);
  try {
    await chapterApi.updateContent(activeProject.id, activeChapter.chapter_index, {
      title: editedTitle,
      content: contentToSave,
    });
    addLog('系统', `第 ${activeChapter.chapter_index} 章正文修改成功并同步！校验结果已刷新。`, 'system');
    loadChapterDetails(activeProject.id, activeChapter.chapter_index);
    loadChapters(activeProject.id);
  } catch (e) {
    showToast(e.message);
  } finally {
    setSavingContent(false);
  }
};
  return {
    handlePause, handleResume, handleInsertPrompt, handleForcePublish, handleProjectSelect,
    handleCreateProject, handleDeleteProject, openContinueModal,
    handleConfirmContinue, handleUpdateProjectConfig, handleRewriteChapter, handleDeleteChapter,
    handleSaveOutline, handleSaveContent,
  };
}

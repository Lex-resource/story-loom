import { create } from 'zustand';

export const useUIStore = create((set) => ({
  workspaceStep: 'planner',
  setWorkspaceStep: (step) => set({ workspaceStep: step }),
  
  writerSubTab: 'compare',
  setWriterSubTab: (tab) => set({ writerSubTab: tab }),
  
  outlineMode: 'visual',
  setOutlineMode: (mode) => set({ outlineMode: mode }),
  
  customPrompt: '',
  setCustomPrompt: (prompt) => set({ customPrompt: prompt }),
}));

export const useProjectStore = create((set) => ({
  activeProject: null,
  setActiveProject: (update) => set((state) => ({
    activeProject: typeof update === 'function' ? update(state.activeProject) : update
  })),

  activeProjectStatus: null,
  setActiveProjectStatus: (update) => set((state) => ({
    activeProjectStatus: typeof update === 'function' ? update(state.activeProjectStatus) : update
  })),

  currentFlowStep: '',
  setCurrentFlowStep: (step) => set({ currentFlowStep: step }),

  chapters: [],
  setChapters: (update) => set((state) => ({
    chapters: typeof update === 'function' ? update(state.chapters) : update
  })),

  activeChapter: null,
  setActiveChapter: (update) => set((state) => ({
    activeChapter: typeof update === 'function' ? update(state.activeChapter) : update
  })),

  editedOutline: '',
  setEditedOutline: (update) => set((state) => ({
    editedOutline: typeof update === 'function' ? update(state.editedOutline) : update
  })),

  editedTitle: '',
  setEditedTitle: (title) => set({ editedTitle: title }),

  editedContent: '',
  setEditedContent: (update) => set((state) => ({
    editedContent: typeof update === 'function' ? update(state.editedContent) : update
  })),

  streamingText: { agent: '', text: '' },
  setStreamingText: (update) => set((state) => ({
    streamingText: typeof update === 'function' ? update(state.streamingText) : update
  })),

  validationResult: { errors: [], warnings: [], infos: [], story_issues: [], streaming: false, passed: null },
  setValidationResult: (update) => set((state) => ({
    validationResult: typeof update === 'function' ? update(state.validationResult) : update
  })),

  streamingEvaluations: null,
  setStreamingEvaluations: (update) => set((state) => ({
    streamingEvaluations: typeof update === 'function' ? update(state.streamingEvaluations) : update
  })),

  validatorStreamLog: '',
  setValidatorStreamLog: (update) => set((state) => ({
    validatorStreamLog: typeof update === 'function' ? update(state.validatorStreamLog) : update
  })),

  isStuckWarning: false,
  setIsStuckWarning: (warning) => set({ isStuckWarning: warning }),

  wsLogs: [],
  setWsLogs: (update) => set((state) => ({
    wsLogs: typeof update === 'function' ? update(state.wsLogs) : update
  })),
  addWsLog: (log) => set((state) => {
    const newLogs = [...state.wsLogs, log];
    if (newLogs.length > 500) newLogs.shift();
    return { wsLogs: newLogs };
  }),
  clearWsLogs: () => set({ wsLogs: [] }),
}));

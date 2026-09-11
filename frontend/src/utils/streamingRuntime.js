export const ROUTED_STREAM_AGENTS = new Set(['writer', 'editor', 'planner', 'validator']);

export function isWatchdogTimedOut({ isGenerating, lastMessageAt, now, timeoutSec = 45 }) {
  if (!isGenerating) return false;
  return (now - lastMessageAt) / 1000 > timeoutSec;
}

export function createPendingStreamUpdates() {
  return {
    text: '',
    textAgent: '',
    outline: '',
    writerText: '',
    writerChapterIndex: null,
    editorContent: '',
    evaluations: null,
    validatorLog: '',
    validationResult: null,
  };
}

export function agentStyleClass(source) {
  if (!source) return 'system';
  const sourceLower = source.toLowerCase();
  if (sourceLower === '校验器' || sourceLower === 'validator') return 'agent-validator';
  if (sourceLower === '提取器' || sourceLower === 'extractor') return 'agent-extractor';
  if (sourceLower === '策划器' || sourceLower === 'planner') return 'agent-planner';
  if (sourceLower === '作家' || sourceLower === 'writer') return 'agent-writer';
  if (sourceLower === '编辑器' || sourceLower === 'editor') return 'agent-editor';
  return `agent-${sourceLower}`;
}

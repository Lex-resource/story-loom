// 前端常量：与后端 services/pipeline_state.py 和 services/constants.py 保持同步。
// 状态字符串集中管理，避免散落在各组件中导致漂移。

export const NovelStatus = {
  PLANNING: 'planning',
  GENERATING: 'generating',
  PAUSED: 'paused',
  FAILED: 'failed',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
};

export const JobStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  PAUSED: 'paused',
  FAILED: 'failed',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
};

export const ChapterStatus = {
  DRAFT: 'draft',
  VALIDATED: 'validated',
  PUBLISHED: 'published',
  POST_PROCESSING: 'post_processing',
  POSTPROCESS_FAILED: 'postprocess_failed',
  AUDIT_FAILED: 'audit_failed',
  PENDING_REVIEW: 'pending_review',
  FAILED: 'failed',
};

export const EditorDecision = {
  REWRITE: 'rewrite',
  REVISE: 'revise',
  PROCEED: 'proceed',
};

// 与后端 services/constants.py 的默认值保持一致
export const DEFAULT_TARGET_CHAPTERS = 100;
export const DEFAULT_WORD_COUNT_PER_CHAPTER = 3000;
export const DEFAULT_SHORT_SECTIONS = 3;
export const DEFAULT_SHORT_TOTAL_WORDS = 12000;
export const DEFAULT_WATCHDOG_TIMEOUT_SECONDS = 45;

export const createDefaultCreativeProfile = (storyLength = 'long') => storyLength === 'short'
  ? {
      story_length: 'short',
      publishing_mode: 'complete',
      prose_style: 'platform_story',
      point_of_view: 'first',
      total_word_count: DEFAULT_SHORT_TOTAL_WORDS,
      target_chapters: DEFAULT_SHORT_SECTIONS,
      word_count_per_chapter: Math.round(DEFAULT_SHORT_TOTAL_WORDS / DEFAULT_SHORT_SECTIONS),
    }
  : {
      story_length: 'long',
      publishing_mode: 'serial',
      prose_style: 'web_novel',
      point_of_view: 'third',
      total_word_count: DEFAULT_TARGET_CHAPTERS * DEFAULT_WORD_COUNT_PER_CHAPTER,
      target_chapters: DEFAULT_TARGET_CHAPTERS,
      word_count_per_chapter: DEFAULT_WORD_COUNT_PER_CHAPTER,
    };

import { useEffect } from 'react';
import { BookOpen, FileText, Loader2, Sparkles } from 'lucide-react';
import {
  DEFAULT_SHORT_TOTAL_WORDS,
  DEFAULT_TARGET_CHAPTERS,
  DEFAULT_WORD_COUNT_PER_CHAPTER,
  createDefaultCreativeProfile,
} from '../utils/constants';

export default function CreateProjectModal({
  isOpen,
  onClose,
  onSubmit,
  newProject,
  setNewProject,
  creating
}) {
  // O-12: Lock body scroll and enable Escape key to close
  useEffect(() => {
    if (!isOpen) return;

    document.body.style.overflow = 'hidden';
    const handleEscape = (e) => {
      if (e.key === 'Escape' && !creating) onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, onClose, creating]);

  if (!isOpen) return null;

  const profile = newProject.creative_profile || createDefaultCreativeProfile(
    newProject.novel_format === 'zhihu_short' ? 'short' : 'long'
  );
  const isShort = profile.story_length === 'short';

  const updateProfile = (changes) => {
    const nextProfile = { ...profile, ...changes };
    setNewProject({
      ...newProject,
      novel_format: nextProfile.story_length === 'short' ? 'zhihu_short' : 'long_webnovel',
      target_chapters: nextProfile.target_chapters,
      word_count_per_chapter: nextProfile.word_count_per_chapter,
      creative_profile: nextProfile,
    });
  };

  const selectLength = (storyLength) => {
    const nextProfile = createDefaultCreativeProfile(storyLength);
    setNewProject({
      ...newProject,
      novel_format: storyLength === 'short' ? 'zhihu_short' : 'long_webnovel',
      target_chapters: nextProfile.target_chapters,
      word_count_per_chapter: nextProfile.word_count_per_chapter,
      creative_profile: nextProfile,
    });
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h2 className="text-gradient font-bold" style={{ margin: 0 }}>天道开卷：创建新小说项目</h2>
        {creating && (
          <div className="modal-loading-hint">
            <Loader2 className="animate-spin" size={18} />
            <span>正在创建项目并启动策划任务，即将进入工作台…</span>
          </div>
        )}
        <form onSubmit={onSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
          <div className="form-group">
            <label className="form-label">小说书名 (Novel Title)</label>
            <input 
              required
              className="form-input" 
              value={newProject.title} 
              onChange={(e) => setNewProject({ ...newProject, title: e.target.value })}
              placeholder="例如：太古仙魔录"
            />
          </div>

          <div className="form-group">
            <label className="form-label">拟定作者 (Author Name)</label>
            <input 
              className="form-input" 
              value={newProject.author} 
              onChange={(e) => setNewProject({ ...newProject, author: e.target.value })}
            />
          </div>

          <div className="form-group">
            <label className="form-label">创作篇幅</label>
            <div className="story-length-control" role="radiogroup" aria-label="创作篇幅">
              <button type="button" role="radio" aria-checked={!isShort} className={`story-length-option ${!isShort ? 'active' : ''}`} onClick={() => selectLength('long')}>
                <BookOpen size={18} />
                <span><strong>长篇连载</strong><small>卷纲推进，持续更新</small></span>
              </button>
              <button type="button" role="radio" aria-checked={isShort} className={`story-length-option ${isShort ? 'active' : ''}`} onClick={() => selectLength('short')}>
                <FileText size={18} />
                <span><strong>短篇完结</strong><small>全文闭环，集中审校</small></span>
              </button>
            </div>
          </div>

          <div className="creative-profile-grid">
            <div className="form-group">
              <label className="form-label">发布形态</label>
              <select className="form-input" value={profile.publishing_mode} onChange={(e) => updateProfile({ publishing_mode: e.target.value })}>
                <option value={isShort ? 'complete' : 'serial'}>{isShort ? '一次完结' : '持续连载'}</option>
                <option value="sections">分节发布</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">文体模板</label>
              <select className="form-input" value={profile.prose_style} onChange={(e) => updateProfile({ prose_style: e.target.value })}>
                <option value="web_novel">网文叙事</option>
                <option value="platform_story">平台故事</option>
                <option value="literary">传统小说</option>
                <option value="suspense">悬疑强化</option>
                <option value="romance">情感强化</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">叙事视角</label>
              <select className="form-input" value={profile.point_of_view} onChange={(e) => updateProfile({ point_of_view: e.target.value })}>
                <option value="first">第一人称</option>
                <option value="third">第三人称</option>
                <option value="limited">第三人称限知</option>
              </select>
            </div>
          </div>

          <div className="creative-profile-grid two-columns">
            <div className="form-group">
              <label className="form-label">{isShort ? '分节数' : '目标章数'}</label>
              <input 
                type="number"
                min="1"
                max={isShort ? 10 : 2000}
                className="form-input" 
                value={profile.target_chapters}
                onChange={(e) => {
                  const target = parseInt(e.target.value) || (isShort ? 3 : DEFAULT_TARGET_CHAPTERS);
                  updateProfile({
                    target_chapters: target,
                    word_count_per_chapter: isShort
                      ? Math.max(1, Math.round(profile.total_word_count / target))
                      : profile.word_count_per_chapter,
                  });
                }}
              />
            </div>
            <div className="form-group">
              <label className="form-label">{isShort ? '全文目标字数' : '单章目标字数'}</label>
              <input 
                type="number"
                min="500"
                className="form-input" 
                value={isShort ? profile.total_word_count : profile.word_count_per_chapter}
                onChange={(e) => {
                  const value = parseInt(e.target.value) || (isShort ? DEFAULT_SHORT_TOTAL_WORDS : DEFAULT_WORD_COUNT_PER_CHAPTER);
                  updateProfile(isShort ? {
                    total_word_count: value,
                    word_count_per_chapter: Math.max(1, Math.round(value / profile.target_chapters)),
                  } : {
                    word_count_per_chapter: value,
                    total_word_count: value * profile.target_chapters,
                  });
                }}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">{isShort ? '核心事件与结尾设想' : '核心卖点与长期主线'}</label>
            <textarea 
              required
              className="form-textarea" 
              value={newProject.user_prompt} 
              onChange={(e) => setNewProject({ ...newProject, user_prompt: e.target.value })}
              placeholder={isShort
                ? '描述核心事件、人物欲望、希望读者感受到的情绪、关键反转和结尾方向...'
                : '描述核心卖点、主角长期目标、成长路径、主要对手、世界规则和阶段性兑现...'}
            />
          </div>

          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="btn btn-primary" disabled={creating}>
              {creating ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />} 开始策划
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

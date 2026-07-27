/**
 * Shared chapter helper functions used by WorkspaceSidebar and Workspace.
 */

export function getReviewFlags(ch) {
  const flags = [];
  if (ch.review_flags && ch.review_flags.length > 0) {
    flags.push(...ch.review_flags);
  }
  const hasForcePublishFlag = flags.some(flag => flag?.type === 'force_corrected');
  if (ch.status === 'pending_review') {
    flags.push({
      type: 'pending_review',
      detail: '本章节格式校验或天道审计异常，等待人工审阅与修复',
      severity: 'error'
    });
  }
  if (ch.validator_auto_force_saved || ch.validator_result?.auto_force_saved) {
    flags.push({
      type: 'validator_auto_force_saved',
      detail: '法则审查未通过但已按配置自动放行，请重点复核右侧审查结果',
      severity: 'warning'
    });
  } else if (ch.force_corrected && !hasForcePublishFlag) {
    flags.push({
      type: 'editor_force_revised',
      detail: '编辑智能体达到重写上限后完成强制精修；这不代表法则审查发现矛盾',
      severity: 'info'
    });
  }
  return flags;
}

// 章节标题里常带有「第N章」前缀（模型生成时写入），而列表/正文已单独渲染章号，
// 直接展示 title 会得到「第30章 第30章 母舰降临」这样的重复。此函数剥掉冗余的章号前缀，
// 仅在剥离后为空时回退到原始 title。纯展示层处理，不改动后端数据。
export function chapterDisplayTitle(title) {
  if (!title || typeof title !== 'string') return '';
  const stripped = title
    .replace(/^\s*第\s*[\d一二三四五六七八九十百千零两]+\s*章\s*[:：、.．\-—\s]*/, '')
    .trim();
  return stripped || title.trim();
}

export function getMaxSeverity(reviewFlags) {
  if (!reviewFlags || !Array.isArray(reviewFlags) || reviewFlags.length === 0) return null;
  let hasError = false;
  let hasWarning = false;
  let hasInfo = false;
  for (const flag of reviewFlags) {
    if (flag.severity === 'error') {
      hasError = true;
    } else if (flag.severity === 'warning') {
      hasWarning = true;
    } else if (flag.severity === 'info') {
      hasInfo = true;
    }
  }
  if (hasError) return 'error';
  if (hasWarning) return 'warning';
  if (hasInfo) return 'info';
  return null;
}

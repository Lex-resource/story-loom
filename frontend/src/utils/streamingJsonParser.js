/** 从流式 JSON 中提取指定字符串字段的值 */
export class StreamingJsonFieldParser {
  constructor(targetKey) {
    this.targetKey = targetKey;
    this.buffer = '';
    this.inTargetValue = false;
    this.valueBuffer = '';
    this.escaped = false;
    this.unicodeEscape = null;
    this.fieldComplete = false;
    this.pos = 0;
  }

  reset() {
    this.buffer = '';
    this.inTargetValue = false;
    this.valueBuffer = '';
    this.escaped = false;
    this.unicodeEscape = null;
    this.fieldComplete = false;
    this.pos = 0;
  }

  append(chunk) {
    this.buffer += chunk;
    while (this.pos < this.buffer.length) {
      if (this.fieldComplete) {
        this.pos = this.buffer.length;
        break;
      }
      const char = this.buffer[this.pos];
      if (!this.inTargetValue) {
        const keyPattern = `"${this.targetKey}"`;
        const keyIndex = this.buffer.indexOf(keyPattern, Math.max(0, this.pos - 50));
        if (keyIndex !== -1 && this.pos >= keyIndex + keyPattern.length) {
          const colonIndex = this.buffer.indexOf(':', keyIndex + keyPattern.length);
          if (colonIndex !== -1 && this.pos >= colonIndex) {
            const quoteIndex = this.buffer.indexOf('"', colonIndex + 1);
            if (quoteIndex !== -1 && this.pos >= quoteIndex) {
              this.inTargetValue = true;
              this.pos = quoteIndex;
              this.pos++;
              continue;
            }
          }
        }
      } else if (this.unicodeEscape !== null) {
        if (/^[0-9a-fA-F]$/.test(char)) {
          this.unicodeEscape += char;
          if (this.unicodeEscape.length === 4) {
            this.valueBuffer += String.fromCharCode(parseInt(this.unicodeEscape, 16));
            this.unicodeEscape = null;
          }
        } else {
          this.valueBuffer += 'u' + this.unicodeEscape + char;
          this.unicodeEscape = null;
        }
      } else if (this.escaped) {
        if (char === 'n') this.valueBuffer += '\n';
        else if (char === 't') this.valueBuffer += '\t';
        else if (char === 'r') this.valueBuffer += '\r';
        else if (char === 'b') this.valueBuffer += '\b';
        else if (char === 'f') this.valueBuffer += '\f';
        else if (char === '/') this.valueBuffer += '/';
        else if (char === 'u') this.unicodeEscape = '';
        else this.valueBuffer += char;
        this.escaped = false;
      } else if (char === '\\') {
        this.escaped = true;
      } else if (char === '"') {
        this.inTargetValue = false;
        this.fieldComplete = true;
      } else {
        this.valueBuffer += char;
      }
      this.pos++;
    }
    // F-16: Trim already-consumed buffer to prevent unbounded memory growth
    if (this.pos > 10000) {
      this.buffer = this.buffer.slice(this.pos);
      this.pos = 0;
    }
    return this.valueBuffer;
  }
}

export const EVALUATION_DIMS = [
  { key: 'plot_progression', label: '剧情推动' },
  { key: 'character_portrayal', label: '人物塑造' },
  { key: 'world_consistency', label: '设定契合' },
  { key: 'writing_quality', label: '文笔表达' },
  { key: 'logical_coherence', label: '逻辑自洽' },
];

/** 从流式 editor JSON 中增量解析五维评分 */
export class EvaluationsStreamParser {
  constructor() {
    this.buffer = '';
    this.done = false;
    this.lastResult = null;
  }

  reset() {
    this.buffer = '';
    this.done = false;
    this.lastResult = null;
  }

  append(chunk) {
    // Once every dimension has a complete (closing-quote-terminated) reason, the
    // evaluations block is final. The editor stream then continues with the large
    // edited_content field; re-scanning it every chunk would be O(n²), so short-circuit.
    if (this.done) return this.lastResult;

    this.buffer += chunk;
    const result = {};
    let completeReasons = 0;
    for (const { key } of EVALUATION_DIMS) {
      // F-17: Use [\s\S]*? (non-greedy, any char) instead of [^}]* to handle nested objects
      const scoreMatch = this.buffer.match(new RegExp(`"${key}"\\s*:\\s*\\{[\\s\\S]*?"score"\\s*:\\s*(\\d+)`));
      const reasonMatch = this.buffer.match(
        new RegExp(`"${key}"\\s*:\\s*\\{[\\s\\S]*?"reason"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"`),
      );
      if (scoreMatch) {
        result[key] = {
          score: parseInt(scoreMatch[1], 10),
          reason: reasonMatch ? reasonMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"') : '',
        };
      }
      if (scoreMatch && reasonMatch) completeReasons++;
    }
    this.lastResult = Object.keys(result).length > 0 ? result : null;
    if (completeReasons === EVALUATION_DIMS.length) {
      this.done = true;
      this.buffer = '';
    }
    return this.lastResult;
  }
}

/** 从流式 validator JSON 中增量解析 issues */
export class ValidatorStreamParser {
  constructor() {
    this.buffer = '';
  }

  reset() {
    this.buffer = '';
  }

  append(chunk) {
    this.buffer += chunk;
    const issues = [];
    const issueRegex =
      /\{\s*"category"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"description"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"severity"\s*:\s*"([^"]*)"/g;
    let m;
    while ((m = issueRegex.exec(this.buffer)) !== null) {
      issues.push({
        category: m[1].replace(/\\"/g, '"'),
        description: m[2].replace(/\\"/g, '"').replace(/\\n/g, '\n'),
        severity: m[3],
      });
    }
    const passedMatch = this.buffer.match(/"passed"\s*:\s*(true|false)/);
    return {
      issues,
      passed: passedMatch ? passedMatch[1] === 'true' : null,
      raw: this.buffer,
    };
  }
}

const STORY_REVIEW_CATEGORIES = new Set(['style', 'pacing', 'character', 'character_portrayal', 'writing_quality']);

/** 将 validator issues 转为 validationResult 格式 */
export function issuesToValidationResult(issues, passed = null) {
  const errors = [];
  const warnings = [];
  const infos = [];
  const storyIssues = [];

  issues.forEach((issue) => {
    const text = `[${issue.category}] ${issue.description}`;
    const sev = (issue.severity || 'block').toLowerCase();
    const category = String(issue.category || '').toLowerCase();
    const issuePayload = { ...issue, message: text };

    // 观察项分流与工作流无关（后端同款：worker_support/validation.py）。这里曾经额外要求
    // novelFormat === 'long_webnovel'，于是短篇和一切自定义工作流的节奏/文风类问题在界面上
    // 退化成 errors/warnings —— 而短篇表面明说这类问题一律 warning、不得触发重写。
    if (STORY_REVIEW_CATEGORIES.has(category)) storyIssues.push(issuePayload);
    else if (sev === 'block') errors.push(text);
    else if (sev === 'warning') warnings.push(text);
    else infos.push(text);
  });
  return {
    passed: passed !== null ? passed : errors.length === 0,
    errors,
    warnings,
    infos,
    story_issues: storyIssues,
    streaming: true,
  };
}

import { describe, it, expect } from 'vitest';

import { StreamingJsonFieldParser, EVALUATION_DIMS } from './streamingJsonParser';

describe('StreamingJsonFieldParser', () => {
  it('extracts the target field from a complete JSON payload', () => {
    const parser = new StreamingJsonFieldParser('content');
    const result = parser.append('{"title": "第1章", "content": "正文内容"}');
    expect(result).toBe('正文内容');
    expect(parser.fieldComplete).toBe(true);
  });

  it('handles values streamed in multiple chunks', () => {
    const parser = new StreamingJsonFieldParser('content');
    let result = '';
    for (const chunk of ['{"content": "第一', '段文字', '结束"}']) {
      result = parser.append(chunk);
    }
    expect(result).toBe('第一段文字结束');
    expect(parser.fieldComplete).toBe(true);
  });

  it('decodes escape sequences', () => {
    const parser = new StreamingJsonFieldParser('content');
    const result = parser.append('{"content": "换行\\n制表\\t引号\\"斜杠\\/"}');
    expect(result).toBe('换行\n制表\t引号"斜杠/');
  });

  it('decodes unicode escapes across chunk boundaries', () => {
    const parser = new StreamingJsonFieldParser('content');
    let result = '';
    for (const chunk of ['{"content": "中', '\\u6587"}']) {
      result = parser.append(chunk);
    }
    expect(result).toBe('中文');
  });

  it('does not confuse the target key with a same-named value', () => {
    const parser = new StreamingJsonFieldParser('content');
    const result = parser.append('{"other": "content-lookalike", "content": "目标"}');
    expect(result).toBe('目标');
  });

  it('keeps streaming after the field is complete', () => {
    const parser = new StreamingJsonFieldParser('content');
    parser.append('{"content": "done"}');
    expect(parser.append('{"tail": "more data"}')).toBe('done');
  });
});

describe('EVALUATION_DIMS', () => {
  it('has exactly five dims with unique keys', () => {
    expect(EVALUATION_DIMS).toHaveLength(5);
    expect(new Set(EVALUATION_DIMS.map((d) => d.key)).size).toBe(5);
  });
});

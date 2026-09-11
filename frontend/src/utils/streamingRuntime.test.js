import { describe, expect, it } from 'vitest';

import {
  agentStyleClass,
  createPendingStreamUpdates,
  isWatchdogTimedOut,
  ROUTED_STREAM_AGENTS,
} from './streamingRuntime';

describe('streaming runtime helpers', () => {
  it('creates a stable empty buffer for each project stream', () => {
    expect(createPendingStreamUpdates()).toEqual({
      text: '',
      textAgent: '',
      outline: '',
      writerText: '',
      writerChapterIndex: null,
      editorContent: '',
      evaluations: null,
      validatorLog: '',
      validationResult: null,
    });
  });

  it('identifies agents whose chunks belong to dedicated panels', () => {
    expect(ROUTED_STREAM_AGENTS.has('writer')).toBe(true);
    expect(ROUTED_STREAM_AGENTS.has('extractor')).toBe(false);
  });

  it('maps localized and canonical agent names to log styles', () => {
    expect(agentStyleClass('校验器')).toBe('agent-validator');
    expect(agentStyleClass('writer')).toBe('agent-writer');
    expect(agentStyleClass('')).toBe('system');
  });

  it('only reports a timeout while generating and after the configured interval', () => {
    expect(
      isWatchdogTimedOut({
        isGenerating: true,
        lastMessageAt: 0,
        now: 44_999,
        timeoutSec: 45,
      }),
    ).toBe(false);
    expect(
      isWatchdogTimedOut({
        isGenerating: true,
        lastMessageAt: 0,
        now: 45_001,
        timeoutSec: 45,
      }),
    ).toBe(true);
    expect(
      isWatchdogTimedOut({
        isGenerating: false,
        lastMessageAt: 0,
        now: 90_000,
        timeoutSec: 45,
      }),
    ).toBe(false);
  });
});

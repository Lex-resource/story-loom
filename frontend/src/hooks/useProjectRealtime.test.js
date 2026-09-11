import { describe, expect, it } from 'vitest';

import { isActiveSocket } from './useProjectRealtime';

describe('project realtime socket guards', () => {
  it('accepts events only from the currently active socket', () => {
    const activeSocket = {};
    const staleSocket = {};

    expect(isActiveSocket(activeSocket, activeSocket)).toBe(true);
    expect(isActiveSocket(activeSocket, staleSocket)).toBe(false);
  });
});

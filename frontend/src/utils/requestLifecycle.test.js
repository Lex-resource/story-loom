import { describe, expect, it } from 'vitest';

import { createRequestGuard, isCurrentProject } from './requestLifecycle';

describe('request lifecycle guard', () => {
  it('invalidates an older request when a newer one starts', () => {
    const guard = createRequestGuard();
    const first = guard.start();
    const second = guard.start();

    expect(first.signal.aborted).toBe(true);
    expect(first.isCurrent()).toBe(false);
    expect(second.isCurrent()).toBe(true);
  });

  it('invalidates the active request when cancelled', () => {
    const guard = createRequestGuard();
    const request = guard.start();

    guard.cancel();

    expect(request.signal.aborted).toBe(true);
    expect(request.isCurrent()).toBe(false);
  });

  it('rejects a response after the active project changes or is cleared', () => {
    const ref = { current: { id: 'project-a' } };

    expect(isCurrentProject(ref, 'project-a')).toBe(true);
    ref.current = { id: 'project-b' };
    expect(isCurrentProject(ref, 'project-a')).toBe(false);
    ref.current = null;
    expect(isCurrentProject(ref, 'project-b')).toBe(false);
  });
});

export function createRequestGuard() {
  let sequence = 0;
  let controller = null;

  return {
    start() {
      controller?.abort();
      controller = new AbortController();
      const requestSequence = ++sequence;
      const { signal } = controller;
      return {
        signal,
        isCurrent: () => requestSequence === sequence && !signal.aborted,
      };
    },
    cancel() {
      sequence += 1;
      controller?.abort();
      controller = null;
    },
  };
}

export function isCurrentProject(activeProjectRef, projectId) {
  return Boolean(projectId) && activeProjectRef.current?.id === projectId;
}

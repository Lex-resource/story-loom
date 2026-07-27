import { requestJson } from './api';

const jsonOptions = (method, body) => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const projectApi = {
  list: () => requestJson('/writing/projects'),
  create: (project) => requestJson('/writing/project', jsonOptions('POST', project)),
  remove: (projectId) => requestJson(`/writing/project/${projectId}`, { method: 'DELETE' }),
  updateConfig: (projectId, config) => requestJson(`/writing/${projectId}/config`, jsonOptions('POST', config)),
};

export const pipelineApi = {
  pause: (projectId) => requestJson(`/writing/${projectId}/pause`, { method: 'POST' }),
  resume: (projectId) => requestJson(`/writing/${projectId}/resume`, { method: 'POST' }),
  intervene: (projectId, text) => requestJson(`/writing/${projectId}/intervention`, jsonOptions('POST', { text })),
  generate: (projectId, payload) => requestJson(`/writing/${projectId}/generate`, jsonOptions('POST', payload)),
  rewrite: (projectId, payload) => requestJson(`/writing/${projectId}/rewrite`, jsonOptions('POST', payload)),
};

export const chapterApi = {
  publish: (projectId, chapterIndex) => requestJson(`/writing/${projectId}/publish/${chapterIndex}`, { method: 'POST' }),
  remove: (projectId, chapterIndex) => requestJson(`/writing/${projectId}/chapters/${chapterIndex}`, { method: 'DELETE' }),
  updateOutline: (projectId, chapterIndex, outline) => requestJson(`/writing/${projectId}/chapters/${chapterIndex}/outline`, jsonOptions('POST', { outline })),
  updateContent: (projectId, chapterIndex, payload) => requestJson(`/writing/${projectId}/chapters/${chapterIndex}/edit`, jsonOptions('POST', payload)),
};

export const outlineApi = {
  update: (projectId, outline) => requestJson(`/writing/${projectId}/outline`, jsonOptions('POST', { outline })),
};

export const livingDocsApi = {
  get: (projectId, docType) => requestJson(`/writing/${projectId}/living-docs/${docType}`),
  getVersion: (projectId, chapterIndex, docType) => requestJson(`/writing/${projectId}/living-docs/versions/${chapterIndex}/${docType}`),
  update: (projectId, docType, content) => requestJson(`/writing/${projectId}/living-docs/${docType}`, jsonOptions('PUT', { content })),
  rollback: (projectId, chapterIndex) => requestJson(`/writing/${projectId}/living-docs/rollback`, jsonOptions('POST', { chapter_index: chapterIndex })),
};

export const settingsApi = {
  watchdogP95: () => requestJson('/settings/watchdog-p95'),
  modelsByProvider: (payload) => requestJson('/settings/models-by-provider', jsonOptions('POST', payload)),
  testProvider: (payload) => requestJson('/settings/test-provider', jsonOptions('POST', payload)),
};

export const systemConfigApi = {
  load: () => Promise.all([
    requestJson('/system-configs/pipeline'),
    requestJson('/system-configs/prompts'),
    requestJson('/system-configs/available-nodes'),
    requestJson('/system-configs/available-docs'),
  ]),
  updatePipeline: (name, payload) => requestJson(`/system-configs/pipeline/${name}`, jsonOptions('PUT', payload)),
};

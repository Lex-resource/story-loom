import { requestJson } from './api';

const jsonOptions = (method, body) => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const projectApi = {
  list: (options = {}) => requestJson('/writing/projects', options),
  // 可选的创作工作流。后端查 pipeline_configs（工作流的权威来源），所以自定义工作流
  // 会自然出现在这里。
  workflows: () => requestJson('/writing/formats'),
  create: (project) => requestJson('/writing/project', jsonOptions('POST', project)),
  remove: (projectId) => requestJson(`/writing/project/${projectId}`, { method: 'DELETE' }),
  updateConfig: (projectId, config) => requestJson(`/writing/${projectId}/config`, jsonOptions('POST', config)),
};

export const pipelineApi = {
  pause: (projectId) => requestJson(`/writing/${projectId}/pause`, { method: 'POST' }),
  resume: (projectId) => requestJson(`/writing/${projectId}/resume`, { method: 'POST' }),
  generate: (projectId, payload) => requestJson(`/writing/${projectId}/generate`, jsonOptions('POST', payload)),
  rewrite: (projectId, payload) => requestJson(`/writing/${projectId}/rewrite`, jsonOptions('POST', payload)),
};

export const chapterApi = {
  publish: (projectId, chapterIndex) =>
    requestJson(`/writing/${projectId}/publish/${chapterIndex}`, { method: 'POST' }),
  remove: (projectId, chapterIndex) =>
    requestJson(`/writing/${projectId}/chapters/${chapterIndex}`, { method: 'DELETE' }),
  updateOutline: (projectId, chapterIndex, outline) =>
    requestJson(`/writing/${projectId}/chapters/${chapterIndex}/outline`, jsonOptions('POST', { outline })),
  updateContent: (projectId, chapterIndex, payload) =>
    requestJson(`/writing/${projectId}/chapters/${chapterIndex}/edit`, jsonOptions('POST', payload)),
  outlines: (projectId, options = {}) => requestJson(`/writing/${projectId}/chapter-outlines`, options),
  submitJsonReview: (projectId, chapterIndex, payload) =>
    requestJson(`/writing/${projectId}/chapters/${chapterIndex}/review_json`, jsonOptions('POST', payload)),
};

export const outlineApi = {
  get: (projectId, options = {}) => requestJson(`/writing/${projectId}/outline`, options),
  update: (projectId, outline) => requestJson(`/writing/${projectId}/outline`, jsonOptions('POST', { outline })),
  rewrite: (projectId, currentOutline, instruction) =>
    requestJson(
      `/writing/${projectId}/outline/chat`,
      jsonOptions('POST', { current_outline: currentOutline, instruction }),
    ),
};

// 知识图谱各视图的只读投影接口（routers/knowledge_views.py）
export const knowledgeGraphApi = {
  characterGraph: (projectId, options = {}) => requestJson(`/writing/${projectId}/character-graph`, options),
  worldRulesTree: (projectId, options = {}) => requestJson(`/writing/${projectId}/world-rules-tree`, options),
  plotTracks: (projectId, options = {}) => requestJson(`/writing/${projectId}/plot-tracks`, options),
  foreshadowingTimeline: (projectId, options = {}) =>
    requestJson(`/writing/${projectId}/foreshadowing-timeline`, options),
};

export const characterApi = {
  list: (projectId, options = {}) => requestJson(`/writing/${projectId}/characters`, options),
  detail: (projectId, characterId, options = {}) =>
    requestJson(`/writing/${projectId}/characters/${characterId}`, options),
  update: (projectId, characterId, payload, options = {}) =>
    requestJson(`/writing/${projectId}/characters/${characterId}`, { ...jsonOptions('PATCH', payload), ...options }),
  states: (projectId, characterId, options = {}) =>
    requestJson(`/writing/${projectId}/characters/${characterId}/states`, options),
  changes: (projectId, characterId, options = {}) =>
    requestJson(`/writing/${projectId}/characters/${characterId}/changes`, options),
  rollback: (projectId, characterId, changeId, options = {}) =>
    requestJson(`/writing/${projectId}/characters/${characterId}/changes/${changeId}/rollback`, {
      ...jsonOptions('POST', {}),
      ...options,
    }),
  arcs: (projectId, characterId, options = {}) =>
    requestJson(`/writing/${projectId}/characters/${characterId}/arcs`, options),
  branches: (projectId, characterId, options = {}) =>
    requestJson(`/writing/${projectId}/characters/${characterId}/branches`, options),
  createBranch: (projectId, characterId, payload) =>
    requestJson(`/writing/${projectId}/characters/${characterId}/branches`, jsonOptions('POST', payload)),
  branchDetail: (projectId, characterId, branchId, options = {}) =>
    requestJson(`/writing/${projectId}/characters/${characterId}/branches/${branchId}`, options),
  generateBranch: (projectId, characterId, branchId, payload = {}) =>
    requestJson(
      `/writing/${projectId}/characters/${characterId}/branches/${branchId}/generate`,
      jsonOptions('POST', payload),
    ),
  editBranchChapter: (projectId, characterId, branchId, chapterIndex, payload) =>
    requestJson(
      `/writing/${projectId}/characters/${characterId}/branches/${branchId}/chapters/${chapterIndex}`,
      jsonOptions('PATCH', payload),
    ),
  archiveBranch: (projectId, characterId, branchId) =>
    requestJson(
      `/writing/${projectId}/characters/${characterId}/branches/${branchId}/archive`,
      jsonOptions('POST', {}),
    ),
  branchSettings: (projectId, options = {}) => requestJson(`/writing/${projectId}/character-branch-settings`, options),
  updateBranchSettings: (projectId, payload) =>
    requestJson(`/writing/${projectId}/character-branch-settings`, jsonOptions('PATCH', payload)),
};

export const settingsApi = {
  modelsByProvider: (payload, options = {}) =>
    requestJson('/settings/models-by-provider', { ...jsonOptions('POST', payload), ...options }),
  testProvider: (payload, options = {}) =>
    requestJson('/settings/test-provider', { ...jsonOptions('POST', payload), ...options }),
};

export const systemConfigApi = {
  // 一次拉齐工作流编辑器需要的全部数据。graph-vocabulary 是角色/裁决/特殊目标/预算的
  // 词表，由后端提供 —— 前端不重写一份，后端加一个角色界面自动跟上。
  load: (options = {}) =>
    Promise.all([
      requestJson('/system-configs/pipeline', options),
      requestJson('/system-configs/prompts', options),
      requestJson('/system-configs/nodes', options),
      requestJson('/system-configs/graph-vocabulary', options),
    ]),

  // 工作流
  createPipeline: (payload) => requestJson('/system-configs/pipeline', jsonOptions('POST', payload)),
  updatePipeline: (name, payload) => requestJson(`/system-configs/pipeline/${name}`, jsonOptions('PUT', payload)),
  deletePipeline: (name) => requestJson(`/system-configs/pipeline/${name}`, { method: 'DELETE' }),
  defaultGraph: (params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).map(([key, value]) => [key, String(Boolean(value))]),
    ).toString();
    return requestJson(`/system-configs/default-graph${query ? `?${query}` : ''}`);
  },

  // 节点库
  listNodes: () => requestJson('/system-configs/nodes'),
  createNode: (payload) => requestJson('/system-configs/nodes', jsonOptions('POST', payload)),
  updateNode: (nodeId, payload) => requestJson(`/system-configs/nodes/${nodeId}`, jsonOptions('PUT', payload)),
  deleteNode: (nodeId) => requestJson(`/system-configs/nodes/${nodeId}`, { method: 'DELETE' }),

  // 提示词
  listPrompts: (category) =>
    requestJson(`/system-configs/prompts${category ? `?category=${encodeURIComponent(category)}` : ''}`),
  createPrompt: (payload) => requestJson('/system-configs/prompts', jsonOptions('POST', payload)),
  updatePrompt: (promptId, payload) => requestJson(`/system-configs/prompts/${promptId}`, jsonOptions('PUT', payload)),
  deletePrompt: (promptId) => requestJson(`/system-configs/prompts/${promptId}`, { method: 'DELETE' }),

  // 运行参数(runtime_tunables):元数据由后端下发,前端不写死任何参数。
  loadTunablesVocabulary: (options = {}) => requestJson('/system-configs/runtime-tunables/vocabulary', options),
  loadTunables: (options = {}) => requestJson('/system-configs/runtime-tunables', options),
  updateTunables: (values, options = {}) =>
    requestJson('/system-configs/runtime-tunables', { ...jsonOptions('PUT', { values }), ...options }),
};

// worker 控制面(routers/worker_admin.py):队列状态、暂停领取、任务取消/重试。
export const workerApi = {
  status: (options = {}) => requestJson('/worker/status', options),
  pauseClaim: () => requestJson('/worker/pause-claim', { method: 'POST' }),
  resumeClaim: () => requestJson('/worker/resume-claim', { method: 'POST' }),
  cancelJob: (jobId) => requestJson(`/worker/jobs/${jobId}/cancel`, { method: 'POST' }),
  retryJob: (jobId) => requestJson(`/worker/jobs/${jobId}/retry`, { method: 'POST' }),
};

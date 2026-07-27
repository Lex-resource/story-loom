import {
  GENERIC_ROLES,
  getRoleNodeStyle,
  getWorldNodeStyle,
  isSectName,
  makeEdgeStyle,
  makeNodeStyle,
  WORLD_ROOT_POSITION,
  WORLD_CATEGORY_KEYS,
  WORLD_CLUSTER_SPREAD,
  WORLD_CLUSTER_GAP,
  WORLD_HUB_MIN_RADIUS,
} from './graphTheme';

const PENTAGON_CHORD_FACTOR = 2 * Math.sin(Math.PI / WORLD_CATEGORY_KEYS.length);
const LEAF_NODE_HALO = 5;

function hashId(id) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = id.charCodeAt(i) + ((h << 5) - h);
  return Math.abs(h);
}

function leafDistanceFromHub(index, nodeId) {
  const h = hashId(nodeId);
  return WORLD_CLUSTER_SPREAD.base
    + Math.pow(index + 1, 0.65) * WORLD_CLUSTER_SPREAD.step
    + (h % WORLD_CLUSTER_SPREAD.jitter);
}

/** 单簇子节点相对枢纽的最远半径（含节点视觉半径） */
function clusterMaxRadius(leaves) {
  if (!leaves.length) return 0;
  let max = 0;
  leaves.forEach((leaf, i) => {
    max = Math.max(max, leafDistanceFromHub(i, leaf.id));
  });
  return max + LEAF_NODE_HALO;
}

/**
 * 根据各簇外缘半径，计算五枢纽正五边形外接圆半径：
 * 相邻两簇满足 枢纽间距 >= r1 + r2 + WORLD_CLUSTER_GAP
 */
function computePentagonHubRadius(radiiByKey) {
  let hubRadius = WORLD_HUB_MIN_RADIUS;
  for (let i = 0; i < WORLD_CATEGORY_KEYS.length; i++) {
    const k0 = WORLD_CATEGORY_KEYS[i];
    const k1 = WORLD_CATEGORY_KEYS[(i + 1) % WORLD_CATEGORY_KEYS.length];
    const r0 = radiiByKey[k0] ?? 0;
    const r1 = radiiByKey[k1] ?? 0;
    const need = (r0 + r1 + WORLD_CLUSTER_GAP) / PENTAGON_CHORD_FACTOR;
    hubRadius = Math.max(hubRadius, need);
  }
  return hubRadius;
}

function buildHubPositions(hubRadius) {
  return Object.fromEntries(
    WORLD_CATEGORY_KEYS.map((key, i) => {
      const angle = (-Math.PI / 2) + (2 * Math.PI * i) / WORLD_CATEGORY_KEYS.length;
      return [key, {
        x: hubRadius * Math.cos(angle),
        y: hubRadius * Math.sin(angle),
      }];
    }),
  );
}

/** 在枢纽周围做 360° 蒲公英星芒散布 */
function computeClusterPositions(leaves, hub) {
  const positions = {};
  const outward = Math.atan2(hub.y, hub.x);
  const golden = Math.PI * (3 - Math.sqrt(5));

  leaves.forEach((leaf, i) => {
    const h = hashId(leaf.id);
    const angle = outward + i * golden + ((h % 100) / 100) * 0.25;
    const radius = leafDistanceFromHub(i, leaf.id);
    positions[leaf.id] = {
      x: hub.x + radius * Math.cos(angle),
      y: hub.y + radius * Math.sin(angle),
    };
  });

  return positions;
}

/** 按搜索词过滤节点与边 */
export function filterBySearch(nodes, edges, query, extraFields = []) {
  if (!query?.trim()) return { nodes, edges };
  const q = query.toLowerCase().trim();
  const filteredNodes = nodes.filter((n) => {
    if (n.label?.toLowerCase().includes(q)) return true;
    if (n.group?.toLowerCase().includes(q)) return true;
    return extraFields.some((field) => n[field]?.toLowerCase().includes(q));
  });
  const ids = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = edges.filter((e) => ids.has(e.from) && ids.has(e.to));
  return { nodes: filteredNodes, edges: filteredEdges };
}

/** 人物图谱：按视图模式转换原始数据 */
export function transformCharacterGraph(raw, filterMode) {
  let nodes = [...(raw.nodes || [])];
  let edges = [...(raw.edges || [])];

  if (filterMode === 'characters') {
    nodes = nodes.filter((n) => !isSectName(n.label));
    const nodeIds = new Set(nodes.map((n) => n.id));
    edges = edges.filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to));
  } else if (filterMode === 'factions') {
    const sectHubs = new Map();
    nodes.forEach((n) => {
      const group = n.group;
      if (group && !GENERIC_ROLES.includes(group) && !sectHubs.has(group)) {
        sectHubs.set(group, { id: `faction_hub_${group}`, label: group, group: 'faction_hub' });
      }
    });
    const charNodes = nodes.filter((n) => !isSectName(n.label));
    nodes = [...charNodes, ...Array.from(sectHubs.values())];
    edges = charNodes
      .filter((c) => c.group && sectHubs.has(c.group))
      .map((c) => ({
        from: c.id,
        to: `faction_hub_${c.group}`,
        label: '所属',
        isFactionEdge: true,
      }));
  }

  return { nodes, edges };
}

/** 将人物图谱数据转为 vis-network 格式 */
export function toVisCharacterData(nodes, edges) {
  const visNodes = nodes.map((n) => {
    const style = getRoleNodeStyle(n.group);
    return {
      id: n.id,
      label: n.label,
      ...makeNodeStyle({
        color: style.color,
        size: style.size,
        shape: style.shape,
        lightFont: n.group === 'faction_hub',
        title: n.title || n.label,
      }),
    };
  });

  const visEdges = edges.map((e) => ({
    from: e.from,
    to: e.to,
    ...makeEdgeStyle({ label: e.label, isFactionEdge: e.isFactionEdge }),
  }));

  return { nodes: visNodes, edges: visEdges };
}

/** 预计算五簇星芒布局（动态五枢纽间距 + 簇内星芒） */
export function toVisWorldData(raw) {
  const nodes = raw.nodes || [];
  const edges = raw.edges || [];

  const leavesByTag = {};
  nodes.forEach((n) => {
    if (n.id === 'root' || n.group === 'category') return;
    const tag = raw.details?.[n.id]?.tag || n.group;
    if (!leavesByTag[tag]) leavesByTag[tag] = [];
    leavesByTag[tag].push(n);
  });

  const clusterRadii = Object.fromEntries(
    WORLD_CATEGORY_KEYS.map((key) => [key, clusterMaxRadius(leavesByTag[key] || [])]),
  );
  const hubRadius = computePentagonHubRadius(clusterRadii);
  const hubPositions = buildHubPositions(hubRadius);

  const positions = { root: { ...WORLD_ROOT_POSITION } };
  WORLD_CATEGORY_KEYS.forEach((key) => {
    positions[`cat_${key}`] = { ...hubPositions[key] };
    const leaves = leavesByTag[key] || [];
    Object.assign(positions, computeClusterPositions(leaves, hubPositions[key]));
  });

  const visNodes = nodes.map((n) => {
    const detail = raw.details?.[n.id];
    const tag = detail?.tag || n.group;
    const style = getWorldNodeStyle(n, tag);
    const pos = positions[n.id] || { x: 0, y: 0 };
    return {
      id: n.id,
      label: n.label,
      x: pos.x,
      y: pos.y,
      physics: false,
      ...makeNodeStyle({
        color: style.color,
        size: style.size,
        shape: style.shape,
        lightFont: style.lightFont,
        title: n.title || n.label,
      }),
    };
  });

  const visEdges = edges.map((e) => ({
    from: e.from,
    to: e.to,
    ...makeEdgeStyle({ label: e.label, showLabel: false }),
  }));

  return { nodes: visNodes, edges: visEdges };
}

/** 图谱统计摘要 */
export function graphStats(nodes, edges) {
  const groups = {};
  nodes.forEach((n) => {
    const g = n.group || '未知';
    groups[g] = (groups[g] || 0) + 1;
  });
  return { nodeCount: nodes.length, edgeCount: edges.length, groups };
}

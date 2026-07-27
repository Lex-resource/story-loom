/** 知识图谱视觉主题与 vis-network 默认配置 */

export const FONT_FACE = 'Noto Serif SC';

export const INK = '#2c1810';
export const INK_MUTED = '#6b5744';
export const PAPER = '#f5f0e8';
export const GOLD = '#b8860b';
export const VERMILION = '#c23a2b';

export const GENERIC_ROLES = [
  '主角', '配角', '反派', '未知', '系统', 'other', '主角团', '反派团',
];

export const SECT_SUFFIXES = ['宗', '阁', '门', '谷', '派', '会', '集市', '大阵', '势力', '盟'];

export const ROLE_NODE_STYLE = {
  protagonist: { color: VERMILION, size: 20 },
  antagonist: { color: '#2c1810', size: 18 },
  factionHub: { color: GOLD, size: 25 },
  default: { color: '#8b5cf6', size: 16 },
};

export const TAG_COLORS = {
  rule: '#2d6a4f',
  location: '#3d5a80',
  faction: '#606c38',
  restriction: '#2c1810',
  confirmed: '#7f5539',
};

export const PALETTE = ['#2d6a4f', '#582f0e', '#1d3557', '#4a3728', '#7f5539', '#3d5a80', '#606c38'];

export function isSectName(name) {
  if (!name) return false;
  return SECT_SUFFIXES.some((s) => name.includes(s));
}

export function getSectColor(sect) {
  if (sect === '主角' || sect === '主角团') return ROLE_NODE_STYLE.protagonist.color;
  if (sect === '反派' || sect === '反派团') return ROLE_NODE_STYLE.antagonist.color;
  if (sect === 'other') return '#7f5539';
  let hash = 0;
  for (let i = 0; i < sect.length; i++) {
    hash = sect.charCodeAt(i) + ((hash << 5) - hash);
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

export function getRoleNodeStyle(group) {
  if (group === 'faction_hub') return { ...ROLE_NODE_STYLE.factionHub, shape: 'box' };
  if (group === '主角' || group === '主角团') return { ...ROLE_NODE_STYLE.protagonist, shape: 'dot' };
  if (group === '反派' || group === '反派团') return { ...ROLE_NODE_STYLE.antagonist, shape: 'dot' };
  return { color: getSectColor(group || 'other'), size: ROLE_NODE_STYLE.default.size, shape: 'dot' };
}

export const CHARACTER_PHYSICS_OPTIONS = {
  layout: { improvedLayout: false },
  physics: {
    enabled: true,
    solver: 'forceAtlas2Based',
    minVelocity: 0,
    forceAtlas2Based: {
      gravitationalConstant: -50,
      centralGravity: 0.01,
      springLength: 100,
      springConstant: 0.03,
      damping: 0.4,
    },
    stabilization: {
      enabled: true,
      iterations: 256,
      updateInterval: 25,
      fit: true,
    },
  },
  interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
};

/** 与人物图谱共用同一套力导向配置（持续模拟） */
export const GRAPH_PHYSICS_OPTIONS = CHARACTER_PHYSICS_OPTIONS;

/** 天地法则：预计算五簇星芒，无物理模拟 */
export const WORLD_CATEGORY_KEYS = ['rule', 'location', 'faction', 'restriction', 'confirmed'];

/** 相邻簇最外缘子节点之间至少保留的间距（px） */
export const WORLD_CLUSTER_GAP = 100;

/** 无子节点或数据极少时的五枢纽最小半径 */
export const WORLD_HUB_MIN_RADIUS = 180;

/** 子节点相对枢纽的星芒散布尺度（仅控制簇内半径，与五枢纽间距无关） */
export const WORLD_CLUSTER_SPREAD = {
  base: 52,
  step: 38,
  jitter: 50,
};

export const WORLD_ROOT_POSITION = { x: 0, y: 0 };

export const WORLD_PHYSICS_OPTIONS = {
  physics: { enabled: false },
  interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
};

export function getWorldNodeStyle(node, tag) {
  if (node.id === 'root') {
    return { color: VERMILION, size: 10, shape: 'dot', lightFont: false };
  }
  if (node.group === 'category') {
    return { color: GOLD, size: ROLE_NODE_STYLE.factionHub.size, shape: 'box', lightFont: true };
  }
  return {
    color: TAG_COLORS[tag] || ROLE_NODE_STYLE.default.color,
    size: 10,
    shape: 'dot',
    lightFont: false,
  };
}

export function makeNodeStyle({ color, size, shape, lightFont = false, title }) {
  return {
    color: {
      background: color,
      border: INK,
      highlight: { background: PAPER, border: color },
    },
    shape,
    size,
    font: {
      color: lightFont ? PAPER : INK,
      size: shape === 'box' ? 13 : 12,
      face: FONT_FACE,
    },
    borderWidth: shape === 'box' ? 2 : 1.5,
    title,
  };
}

export function makeEdgeStyle({ label, isFactionEdge = false, fontSize = 11, showLabel = true }) {
  return {
    label: showLabel ? label : undefined,
    arrows: 'to',
    font: { color: INK_MUTED, size: fontSize, face: FONT_FACE, align: 'horizontal' },
    color: {
      color: isFactionEdge ? 'rgba(184, 134, 11, 0.4)' : 'rgba(44, 24, 16, 0.15)',
      highlight: VERMILION,
    },
    width: 0.6,
  };
}

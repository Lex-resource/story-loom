// 后端地址不再是可配项：开发环境固定直连本机 8000(与 vite.config.js 的代理目标、
// uvicorn 的监听端口一致),生产环境前端由后端自身托管,所以用当前 origin。
const DEV_BACKEND_URL = 'http://127.0.0.1:8000';

export function getBackendUrl() {
  // 早期版本允许在「设置」页覆盖后端地址并存进 localStorage。入口已删除,残留值
  // 只会把请求打到一个不存在的端口上,所以启动时清掉。
  try {
    localStorage.removeItem('BACKEND_URL');
  } catch {
    // 隐私模式等场景下 localStorage 不可用,忽略即可。
  }

  return import.meta.env.DEV ? DEV_BACKEND_URL : window.location.origin;
}

export const BACKEND_URL = getBackendUrl();
export const API_BASE = `${BACKEND_URL}/api`;

export async function requestJson(path, options = {}) {
  const response = await fetch(path.startsWith('http') ? path : `${API_BASE}${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    let detail;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || '';
    } catch {
      detail = await response.text().catch(() => '');
    }
    throw new Error(detail || `请求失败 (${response.status})`);
  }

  if (response.status === 204) return null;
  return response.json();
}

export function getBackendUrl() {
  const stored = localStorage.getItem('BACKEND_URL');
  if (stored) {
    return stored.trim().replace(/\/$/, '').replace('localhost', '127.0.0.1');
  }

  const { protocol, hostname, port, origin } = window.location;
  if (port === '5173' || port === '4173') {
    const targetHost = hostname === 'localhost' ? '127.0.0.1' : hostname;
    return `${protocol}//${targetHost}:8000`;
  }
  return origin;
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

export function saveBackendUrl(url) {
  const normalized = url?.trim();
  if (!normalized) {
    localStorage.removeItem('BACKEND_URL');
    return;
  }
  localStorage.setItem(
    'BACKEND_URL',
    /^https?:\/\//i.test(normalized) ? normalized : `http://${normalized}`,
  );
}

// Client for the oj-rest public API.

const BASE = '/api/v1';
const TOKEN_KEY = 'oj.adminToken';

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/** Turn FastAPI / gateway error payloads into one readable string. */
export function formatDetail(detail) {
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const loc = (d.loc || []).filter((p) => p !== 'body').join('.');
        return loc ? `${loc}: ${d.msg}` : d.msg;
      })
      .join('; ');
  }
  return JSON.stringify(detail);
}

function storage(kind) {
  try {
    return kind === 'session' ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

export function getAdminToken() {
  try {
    return storage('session')?.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setAdminToken(token) {
  try {
    if (token) storage('session')?.setItem(TOKEN_KEY, token);
    else storage('session')?.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: token simply isn't remembered */
  }
}

export function toQuery(params = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}

async function request(method, path, { body, admin = false, fetchImpl = globalThis.fetch } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (admin) {
    const token = getAdminToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  let res;
  try {
    res = await fetchImpl(BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Network error: is the server reachable?');
  }
  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const retry = res.headers?.get?.('Retry-After');
    let msg = formatDetail(data?.detail) || `${res.status} ${res.statusText || 'error'}`;
    if (res.status === 429 && retry) msg = `Too many requests. Try again in ${retry}s.`;
    throw new ApiError(res.status, msg);
  }
  return data;
}

export const api = {
  request,
  status: () => request('GET', '/status'),
  languages: () => request('GET', '/languages'),
  problems: () => request('GET', '/problems'),
  problem: (id) => request('GET', `/problems/${encodeURIComponent(id)}`),
  submissions: (params) => request('GET', `/submissions${toQuery(params)}`),
  submission: (id) => request('GET', `/submissions/${encodeURIComponent(id)}`),
  submit: (body) => request('POST', '/submissions', { body }),
  run: (body) => request('POST', '/run', { body }),
  admin: {
    verify: () => request('GET', '/admin/verify', { admin: true }),
    createProblem: (body) => request('POST', '/admin/problems', { body, admin: true }),
    updateProblem: (id, body) => request('PUT', `/admin/problems/${id}`, { body, admin: true }),
    deleteProblem: (id) => request('DELETE', `/admin/problems/${id}`, { admin: true }),
    testcases: (id) => request('GET', `/admin/problems/${id}/testcases`, { admin: true }),
  },
};

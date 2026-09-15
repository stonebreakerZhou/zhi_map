import type { State, BranchMeta, TopicMeta, Entry } from './types.js';
export type Compact = { revision: number; active: string | null; affectedIds?: string[]; entryIds?: string[]; undoToken?: string | null };
export type Page<T> = { items: T[]; nextCursor: number | null; cursor?: number };

export type Snapshot = { state: State; revision: number };
export type AiConfig = { configured: boolean; provider?: string; maxTokens?: number; temperature?: number | null; baseUrl: string | null; model: string | null; timeoutMs: number | null; updatedAt: string | null; source: 'user' | 'environment' | 'default' | 'none' };
export class ConflictError extends Error {}
export class RequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) }, ...init });
  const body = await response.json() as { error?: string } & T;
  if (!response.ok) {
    if (response.status === 409) throw new ConflictError(body.error ?? '工作区已更新。');
    throw new RequestError(body.error ?? '请求失败。', response.status);
  }
  return body;
}

/** Same as request() but also returns the response headers — needed for
 *  the dev-mode X-Dev-Auth-Code hint returned by /api/auth/email/start. */
export async function requestWithHeaders<T>(url: string, init?: RequestInit): Promise<{ body: T; headers: Headers }> {
  const response = await fetch(url, { credentials: 'same-origin', headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) }, ...init });
  const body = await response.json() as { error?: string } & T;
  if (!response.ok) {
    if (response.status === 409) throw new ConflictError(body.error ?? '工作区已更新。');
    throw new RequestError(body.error ?? '请求失败。', response.status);
  }
  return { body, headers: response.headers };
}

export const api = {
  view: () => request<Compact>('/api/workspace/view'),
  branch: (id: string, signal?: AbortSignal) => request<BranchMeta>(`/api/branches/${encodeURIComponent(id)}`, signal ? { signal } : undefined),
  topics: (cursor = -1, search = '') => request<Page<TopicMeta>>(`/api/topics?limit=40&cursor=${cursor}&search=${encodeURIComponent(search)}`),
  entries: (id: string, cursor = -1, anchor = '', before = '', signal?: AbortSignal) => request<Page<Entry>>(`/api/branches/${encodeURIComponent(id)}/entries?limit=40&cursor=${cursor}&anchor=${encodeURIComponent(anchor)}&before=${encodeURIComponent(before)}`, signal ? { signal } : undefined),
  status: () => request<{ mode: string; model: string | null }>('/api/status'),
  aiConfig: () => request<AiConfig>('/api/ai/config'),
  saveAiConfig: (body: { baseUrl: string; model: string; apiKey: string; timeoutMs?: number; provider?: string; maxTokens?: number; temperature?: number | null }) => request<AiConfig>('/api/ai/config', { method: 'POST', body: JSON.stringify(body) }),
  clearAiConfig: () => request<AiConfig>('/api/ai/config/clear', { method: 'POST', body: JSON.stringify({ confirm: true }) }),
  testAiConfig: () => request<{ ok: true }>('/api/ai/config/test', { method: 'POST', body: JSON.stringify({}) }),
  action: (body: Record<string, unknown>) => request<Compact>('/api/workspace/actions?response=compact', { method: 'POST', body: JSON.stringify(body) }),
  undo: (token: string, revision: number) => request<Compact>('/api/workspace/undo', { method: 'POST', body: JSON.stringify({ token, revision }) }),
  rerank: (query: string, candidates: { id: string; title: string; summary: string }[]) => request<{ ids: string[] }>('/api/ai/rerank', { method: 'POST', body: JSON.stringify({ query, candidates }) }),
  import: (body: unknown, revision: number) => request<Snapshot>('/api/import', { method: 'POST', body: JSON.stringify({ ...(body as object), revision }) }),
  // ─── email auth ───
  authMe: () => request<{ isLoggedIn: boolean; userId?: string; email?: string | null }>('/api/auth/me'),
  emailStart: (email: string) => requestWithHeaders<{ ok: true }>('/api/auth/email/start', { method: 'POST', body: JSON.stringify({ email }) }),
  emailRegister: (body: { email: string; code: string; password: string }) => request<{ ok: true; userId: string }>('/api/auth/email/register', { method: 'POST', body: JSON.stringify(body) }),
  emailLogin: (body: { email: string; password: string }) => request<{ ok: true; userId: string }>('/api/auth/email/login', { method: 'POST', body: JSON.stringify(body) }),
  emailLogout: () => request<{ ok: true }>('/api/auth/logout', { method: 'POST', body: '{}' }),
  changePassword: (body: { oldPassword: string; newPassword: string }) => request<{ ok: true }>('/api/auth/password/change', { method: 'POST', body: JSON.stringify(body) }),
  resetPassword: (body: { email: string; code: string; newPassword: string }) => request<{ ok: true }>('/api/auth/password/reset', { method: 'POST', body: JSON.stringify(body) }),
};

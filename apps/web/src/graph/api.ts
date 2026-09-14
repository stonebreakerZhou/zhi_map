import { request, type Compact } from '../api.js';

export type Point = { x: number; y: number };
export type Preview = { text: string; entryId: string; branchId: string; start: number; end: number; version: number };
export type GraphNode = Point & { id: string; title: string; parent: string | null; kind: 'root' | 'branch'; revision: number; layoutVersion: number; previews: Preview[]; childrenCount: number; visibleChildren: number };
export type GraphEdge = { id: string; type: 'parent' | 'contact' | 'reference'; source: string; target: string };
export type Projection = Compact & { nodes: GraphNode[]; edges: GraphEdge[]; aggregate: number; total: number; nextCursor: number | null; path: string[]; pathContinuation: string | null; childNextCursor: number | null };
export type Receipt = { operationId: string; targets: { id: string; title: string }[]; committedAt: number; expiresAt: number; status: 'removed' | 'restored' | 'expired' };
export type RemovalResult = Receipt & Compact;
const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

export const graphApi = {
  root: (id: string) => request<{ rootId: string | null; depth: number; continuationId?: string }>(`/api/graph/root/${encodeURIComponent(id)}`),
  query: async (params: URLSearchParams, signal: AbortSignal): Promise<Projection> => {
    const data = await request<Projection>(`/api/graph?${params}`, { signal });
    if (!Array.isArray(data.nodes) || data.nodes.length > 200 || !Array.isArray(data.edges) || data.edges.length > 400 || data.nodes.some(n => typeof n.id !== 'string' || !Number.isFinite(n.x) || !Number.isFinite(n.y) || !Array.isArray(n.previews) || n.previews.length > 2)) throw new Error('图投影格式无效。');
    return data;
  },
  position: (node: GraphNode, point: Point) => request('/api/graph/positions', post({ branchId: node.id, ...point, version: node.layoutVersion })),
  contact: (source: string, targets: string[], unlink = false) => request('/api/graph/contacts', post({ source, targets, unlink })),
  remove: (operationId: string, targets: { id: string; revision: number }[]) => request<RemovalResult>('/api/graph/removals', post({ operationId, targets })),
  receipt: (id: string) => request<Receipt>(`/api/graph/removals/${encodeURIComponent(id)}`),
  recent: (cursor = '') => request<{ items: Receipt[]; count: number; nextCursor: string | null }>(`/api/graph/removals?cursor=${encodeURIComponent(cursor)}`),
  restore: (id: string, asRoot = false) => request<RemovalResult>(`/api/graph/removals/${encodeURIComponent(id)}/restore`, post({ asRoot })),
};

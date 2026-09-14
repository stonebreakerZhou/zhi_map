import { api, ConflictError, RequestError, type Compact, type Page } from './api.js';
import type { Action, BranchMeta, Entry } from './types.js';
import { chatStream } from './services/chat-stream.js';
import { graphApi, type Receipt } from './graph/api.js';

/** LRU pages, never a workspace snapshot. At most 3 pages per branch, 8 total. */
export class QueryCache {
  constructor(private notify = () => {}) {}
  private pages = new Map<string, { branch: string; page: Page<Entry> }>();
  private epoch = 0;
  get size() { return this.pages.size; }
  get entryCount() { return [...this.pages.values()].reduce((n, p) => n + p.page.items.length, 0); }
  clear(branch?: string) { this.epoch++; for (const [k, v] of this.pages) if (!branch || v.branch === branch) this.pages.delete(k); }
  async page(branch: string, cursor = -1, anchor = '', before = '') {
    const key = JSON.stringify([branch, cursor, anchor, before]);
    const cached = this.pages.get(key);
    if (cached) { this.pages.delete(key); this.pages.set(key, cached); return cached.page; }
    const epoch = this.epoch;
    const page = await api.entries(branch, cursor, anchor, before);
    if (epoch !== this.epoch) return page;
    this.pages.set(key, { branch, page });
    while ([...this.pages.values()].filter(v => v.branch === branch).length > 3) this.pages.delete([...this.pages].find(([, v]) => v.branch === branch)![0]);
    while (this.pages.size > 8) this.pages.delete(this.pages.keys().next().value!);
    this.notify();
    return page;
  }
}

export class WorkspaceController {
  revision = 0;
  initialized = false;
  topicRevision = 0;
  branch?: BranchMeta;
  page: Page<Entry> = { items: [], nextCursor: null, cursor: -1 };
  notice = '';
  undoToken?: string;
  undoBusy = false;
  removal?: Receipt;
  removalBusy = false;
  unknownRemoval?: { operationId: string; targets: { id: string; revision: number }[] };
  readonly cache = new QueryCache(() => this.changed());
  private dirty = new Map<string, string>();
  private runs = new Map<string, { abort: AbortController; id?: string; text: string }>();
  private listeners = new Set<() => void>();
  private version = 0;
  private queue: Promise<unknown> = Promise.resolve();
  private timer?: number;
  private undoTimer?: number;
  private frame = 0;
  private generation = 0;
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  getVersion = () => this.version;
  changed = () => { this.version++; this.listeners.forEach(fn => fn()); };
  report = (error: unknown) => { this.notice = error instanceof Error ? error.message : String(error); this.changed(); };
  private accept(result: Compact) {
    if (result.revision > this.revision) { this.undoToken = undefined; clearTimeout(this.undoTimer); }
    this.revision = Math.max(this.revision, result.revision);
    for (const id of result.affectedIds ?? []) this.cache.clear(id);
    if (result.undoToken) {
      this.undoToken = result.undoToken;
      clearTimeout(this.undoTimer);
      this.undoTimer = window.setTimeout(() => { this.undoToken = undefined; this.changed(); }, 600000);
    }
  }
  async load() {
    const view = await api.view(); this.accept(view);
    this.topicRevision++;
    if (view.active) await this.open(view.active); else { this.branch = undefined; this.page = { items: [], nextCursor: null }; this.changed(); }
    this.initialized = true; this.changed();
  }
  async open(id: string, anchor = '') {
    const generation = ++this.generation;
    const [branch, page] = await Promise.all([api.branch(id), this.cache.page(id, -1, anchor)]);
    if (generation !== this.generation) return;
    this.branch = { ...branch, draft: this.dirty.get(id) ?? branch.draft };
    this.page = page; this.changed();
  }
  async navigate(cursor: number) { const id = this.branch?.id; if (!id) return; const generation = ++this.generation; const page = await this.cache.page(id, cursor); if (this.branch?.id === id && generation === this.generation) { this.page = page; this.changed(); } }
  draft(text: string) {
    if (!this.branch) return;
    this.dirty.set(this.branch.id, text); this.branch = { ...this.branch, draft: text }; this.changed();
    clearTimeout(this.timer); this.timer = window.setTimeout(() => void this.flush().catch(this.report), 500);
  }
  private serial<T>(run: () => Promise<T>): Promise<T> { const next = this.queue.then(run).catch(async error => { if (error instanceof ConflictError) { this.accept(await api.view()); this.report('工作区版本已更新；草稿保留，请重试保存。'); } throw error; }); this.queue = next.catch(() => {}); return next; }
  async flush() {
    clearTimeout(this.timer);
    return this.serial(async () => {
      for (const [branchId, text] of [...this.dirty]) {
        const result = await api.action({ type: 'draft', branchId, text, revision: this.revision }); this.accept(result);
        if (this.dirty.get(branchId) === text) this.dirty.delete(branchId);
      }
      this.changed();
    });
  }
  async action(action: Action, anchor = '') {
    if (action.type === 'delete' && action.kind !== 'session' && typeof action.targetId === 'string') {
      return this.remove([action.targetId]);
    }
    await this.flush(); // Failure deliberately prevents switching or overwriting a draft.
    return this.serial(async () => {
      const result = await api.action({ ...action, revision: this.revision }); this.accept(result);
      if (['create', 'sample', 'metadata', 'keep', 'fork', 'expand', 'delete'].includes(action.type)) this.topicRevision++;
      if (result.active) await this.open(result.active, anchor || result.entryIds?.at(-1));
      else { this.branch = undefined; this.page = { items: [], nextCursor: null }; }
      this.changed(); return result;
    });
  }
  async undo() {
    if (this.undoBusy) return;
    this.undoBusy = true; this.changed();
    try { await this.flush(); await this.serial(async () => { if (!this.undoToken) return; const result = await api.undo(this.undoToken, this.revision); this.undoToken = undefined; this.accept(result); this.topicRevision++; if (result.active) await this.open(result.active); }); }
    finally { this.undoBusy = false; this.changed(); }
  }
  async remove(ids: string[], operationId: string = crypto.randomUUID()) {
    if (this.unknownRemoval) {
      const previous = this.unknownRemoval;
      if (JSON.stringify(previous.targets.map(t => t.id)) !== JSON.stringify(ids)) throw new Error('请先核实上次移除，再操作其他目标。');
      await this.reconcileRemoval();
      if (this.unknownRemoval) throw new Error('上次移除结果尚未核实，请点击“核实移除”。');
      if (this.removal?.operationId === previous.operationId) return { ...await api.view(), ...this.removal };
      operationId = previous.operationId;
    }
    if (this.removalBusy) throw new Error('正在核实移除结果，请稍候。');
    this.removalBusy = true; this.changed();
    try {
      await this.flush();
      return await this.serial(async () => {
        const targets = await Promise.all(ids.map(async id => ({ id, revision: (await api.branch(id)).revision })));
        for (const id of ids) this.cancel(id);
        let result;
        try { result = await graphApi.remove(operationId, targets); }
        catch (error) {
          if (!(error instanceof TypeError) && !(error instanceof RequestError && error.status >= 500)) throw error;
          this.report('正在核实移除结果…');
          // Same operation identity on the single transient retry, never another deletion.
          try { result = await graphApi.remove(operationId, targets); }
          catch (retryError) { this.unknownRemoval = { operationId, targets }; this.changed(); throw retryError; }
        }
        this.accept(result); this.removal = result; this.topicRevision++;
        if (ids.includes(this.branch?.id ?? '')) {
          if (result.active) await this.open(result.active);
          else { this.branch = undefined; this.page = { items: [], nextCursor: null }; }
        }
        this.changed();
        return result;
      });
    } finally { this.removalBusy = false; this.changed(); }
  }
  async restore(id: string, asRoot = false) {
    return this.serial(async () => {
      let result;
      try { result = await graphApi.restore(id, asRoot); }
      catch (error) { if (!(error instanceof TypeError)) throw error; result = await graphApi.restore(id, asRoot); }
      this.accept(result); this.topicRevision++;
      if (this.removal?.operationId === id) this.removal = undefined;
      this.changed(); return result;
    });
  }
  async reconcileRemoval() {
    const pending = this.unknownRemoval;
    if (!pending || this.removalBusy) return;
    this.removalBusy = true; this.changed();
    try {
      const receipt = await graphApi.receipt(pending.operationId);
      this.unknownRemoval = undefined;
      if (receipt.status === 'removed') this.removal = receipt;
      await this.load();
    } catch (error) {
      if (error instanceof RequestError && error.status === 404) {
        this.unknownRemoval = undefined;
        this.report('服务器尚无此操作记录，主题未被确认移除。可重新检查目标后重试。');
      } else this.report(error);
    } finally { this.removalBusy = false; this.changed(); }
  }
  running(id = this.branch?.id) { return Boolean(id && this.runs.has(id)); }
  partial(id = this.branch?.id) { return id ? this.runs.get(id)?.text ?? '' : ''; }
  async ask(id = this.branch?.id) {
    if (!id || this.runs.has(id)) return;
    if (this.runs.size >= 3) throw new Error('最多同时生成 3 个主题，请先等待或停止已有回答。');
    await this.flush();
    if (this.runs.has(id)) return;
    const run = { abort: new AbortController(), id: undefined as string | undefined, text: '' }; this.runs.set(id, run); this.changed();
    try {
      const result = await chatStream(id, this.revision, run.abort.signal, event => {
        if (this.runs.get(id) !== run) return;
        run.id = event.runId;
        if (event.type === 'started' && event.contextTruncated) { this.notice = 'AI 背景已按最近 100 条 / 64,000 字符裁剪；选区原文始终保留，完整历史仍可分页查看。'; this.changed(); }
        if (event.type === 'delta') {
          run.text += event.text ?? '';
          if (run.text.length > 256000) { run.abort.abort(); throw new Error('回答超过 256,000 字符预算。'); }
          if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.changed(); });
        }
      });
      this.accept(result);
      if (this.branch?.id === id && !run.abort.signal.aborted) await this.open(id, result.entryIds?.at(-1));
    } catch (error) { if ((error as Error).name !== 'AbortError') this.report(error); }
    finally { if (this.runs.get(id) === run) this.runs.delete(id); this.changed(); }
  }
  cancel(id = this.branch?.id) { if (!id) return; const run = this.runs.get(id); if (run?.id) void fetch('/api/ai/chat/cancel', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ branchId: id, runId: run.id }) }).catch(this.report); run?.abort.abort(); }
  dispose() { clearTimeout(this.timer); clearTimeout(this.undoTimer); cancelAnimationFrame(this.frame); for (const id of this.runs.keys()) this.cancel(id); this.generation++; this.listeners.clear(); this.cache.clear(); }
}

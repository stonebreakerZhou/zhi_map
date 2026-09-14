import { useEffect, useRef, useState } from 'react';
import type { WorkspaceController } from '../controller.js';
import { ConfirmDialog, Dialog } from '../components/Dialog.js';
import { graphApi, type Point, type Receipt } from './api.js';

export function Recovery({ app, anchor }: { app: WorkspaceController; anchor?: Point }) {
  const [items, setItems] = useState<Receipt[]>([]), [count, setCount] = useState(0);
  const [cursor, setCursor] = useState(''), [next, setNext] = useState<string | null>(null);
  const [open, setOpen] = useState(false), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [root, setRoot] = useState<Receipt>();
  const [restored, setRestored] = useState<Receipt>();
  const [now, setNow] = useState(Date.now()), [dismissed, setDismissed] = useState('');
  const bubble = useRef<HTMLDivElement>(null);
  const [point, setPoint] = useState<Point>({ x: 16, y: 120 });
  const refresh = () => graphApi.recent(cursor).then(r => { setItems(r.items); setCount(r.count); setNext(r.nextCursor); setError(''); }).catch(e => setError(String(e)));
  useEffect(() => { let live = true; void graphApi.recent(cursor).then(r => { if (live) { setItems(r.items); setCount(r.count); setNext(r.nextCursor); } }).catch(e => { if (live) setError(String(e)); }); return () => { live = false; }; }, [app.topicRevision, cursor]);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const current = app.removal?.status === 'removed' && app.removal.expiresAt * 1000 > now && app.removal.operationId !== dismissed ? app.removal : undefined;
  useEffect(() => {
    const clamp = () => {
      const rect = bubble.current?.getBoundingClientRect();
      setPoint({ x: Math.max(16, Math.min(anchor?.x ?? 16, innerWidth - (rect?.width ?? 360) - 16)), y: Math.max(112, Math.min((anchor?.y ?? 160) - (rect?.height ?? 80) - 8, innerHeight * .5)) });
    };
    clamp(); window.addEventListener('resize', clamp); return () => window.removeEventListener('resize', clamp);
  }, [current?.operationId, anchor]);
  const restore = async (receipt: Receipt, asRoot = false) => {
    if (busy) return;
    setBusy(true); setError('');
    try { await app.restore(receipt.operationId, asRoot); setRestored(receipt); setRoot(undefined); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); if (!asRoot) setRoot(receipt); }
    finally { setBusy(false); }
  };
  return <>
    <button onClick={() => setOpen(true)}>最近移除（{count}）</button>
    {restored && <button title={restored.targets.map(t => t.title).join('、')} onClick={() => {
      const id = restored.targets[0]?.id;
      if (id) void app.action({ type: 'switch', branchId: id }).then(() => setRestored(undefined)).catch(app.report);
    }}>打开已恢复主题</button>}
    {app.unknownRemoval && <button disabled={app.removalBusy} onClick={() => void app.reconcileRemoval()}>核实移除</button>}
    {current && <div ref={bubble} className="graph-recovery" style={{ left: point.x, top: point.y }} role="status">
      <span>已移除「{current.targets.map(t => t.title).join('、')}」</span>
      <button disabled={busy} onClick={() => void restore(current)}>恢复</button>
      <button aria-label="关闭恢复浮窗" onClick={() => setDismissed(current.operationId)}>关闭</button>
      {error && <p role="alert">{error}</p>}
    </div>}
    {open && <Dialog title="最近移除" close={() => setOpen(false)} locked={busy}>
      <p>服务器保留十分钟；恢复不会切换当前讨论。无关草稿与问答不影响恢复。</p>
      {error && <p role="alert">{error}<button onClick={() => void refresh()}>重试</button></p>}
      {items.map(r => <div key={r.operationId}><p>{r.targets.map(t => t.title).join('、')} · {Math.max(0, Math.ceil((r.expiresAt * 1000 - now) / 1000))} 秒</p><button disabled={busy || r.expiresAt * 1000 <= now} onClick={() => void restore(r)}>恢复</button></div>)}
      <button disabled={!cursor} onClick={() => setCursor('')}>首页</button><button disabled={!next} onClick={() => next && setCursor(next)}>下一页</button>
    </Dialog>}
    {root && <ConfirmDialog title="仅恢复主题和消息？" label="作为独立根恢复" close={() => setRoot(undefined)} confirm={() => restore(root, true)}>
      <p>{error}</p><p>将「{root.targets.map(t => t.title).join('、')}」作为独立根恢复，不恢复旧父子归属和联系，不覆盖子分支的后续修改。</p>
    </ConfirmDialog>}
  </>;
}

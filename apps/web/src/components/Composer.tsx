import type { WorkspaceController } from '../controller.js';
import { useEffect, useRef, useState } from 'react';

export function Composer({ app, references }: { app: WorkspaceController; references: () => void }) {
  const guard = useRef(false), [busy, setBusy] = useState(false), host = useRef<HTMLDivElement>(null);
  // The dock floats over the reading column, so the transcript reserves its real height.
  useEffect(() => {
    const element = host.current, stage = element?.closest('.conversation-stage');
    if (!element || !stage) return;
    const observer = new ResizeObserver(() => (stage as HTMLElement).style.setProperty('--composer-height', `${element.getBoundingClientRect().height}px`));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const b = app.branch; if (!b) return null;
  const send = async () => { if (guard.current || !b.draft.trim()) return; guard.current = true; setBusy(true); try { await app.action({ type: 'send', branchId: b.id }); if (app.branch?.awaiting) void app.ask().catch(app.report); } finally { guard.current = false; setBusy(false); } };
  return <div className="bottom" ref={host}>
    <div className="composer-topic">正在编辑：{b.title}</div>
    {b.pendingPrompt && <div id="history-gate"><strong>这次想参考哪段旧讨论？</strong><p>{b.pendingPrompt}</p><p>仅确认当前待发送问题；不新增引用不会清除已有引用。</p><button onClick={references}>选择并确认引用</button><button onClick={() => void app.action({ type: 'resolveHistory', branchId: b.id, decision: 'skip' }).then(() => app.ask()).catch(app.report)}>不新增引用，继续</button></div>}
    {b.awaiting && <div id="request-status"><span>{app.running() ? '正在思考，请稍候…' : '问题已保留，尚未收到回答。'}</span>{!app.running() && <><button data-retry-answer onClick={() => void app.ask().catch(app.report)}>重试回答</button><button data-edit-question onClick={() => void app.action({ type: 'retryToDraft', branchId: b.id }).catch(app.report)}>返回草稿编辑</button></>}</div>}
    <form id="composer" onSubmit={e => { e.preventDefault(); void send().catch(app.report); }}><label className="sr-only" htmlFor="draft">继续这条思路</label><textarea id="draft" rows={2} maxLength={64000} placeholder="继续提问，或选中回答中的一段展开讨论" value={b.draft} disabled={Boolean(b.pendingPrompt)} onChange={e => app.draft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) { e.preventDefault(); if (!b.awaiting && !b.pendingPrompt) void send().catch(app.report); } }} /><div className="composer-bottom"><button type="button" className="composer-tool" onClick={references}>引用</button><span>Ctrl / Cmd + Enter</span>{app.running() ? <button type="button" className="composer-stop" data-cancel onClick={() => app.cancel()}>停止</button> : <button id="send" type="submit" className="primary composer-send" disabled={busy || !b.draft.trim() || Boolean(b.awaiting || b.pendingPrompt)}>发送</button>}</div></form>
  </div>;
}

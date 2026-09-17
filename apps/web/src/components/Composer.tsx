import type { WorkspaceController } from '../controller.js';
import { useEffect, useRef, useState } from 'react';
import { IconButton } from './UI.js';

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
  const sendable = !busy && Boolean(b.draft.trim()) && !b.awaiting && !b.pendingPrompt;
  return <div className="bottom" ref={host}>
    {b.pendingPrompt && <div id="history-gate"><strong>要参考哪段旧讨论？</strong><p>{b.pendingPrompt}</p><button onClick={references}>选择引用</button><button onClick={() => void app.action({ type: 'resolveHistory', branchId: b.id, decision: 'skip' }).then(() => app.ask()).catch(app.report)}>不引用，继续发送</button></div>}
    {b.awaiting && <div id="request-status"><span>{app.running() ? '正在生成…' : '已保留问题，还没有回答。'}</span>{!app.running() && <><button data-retry-answer onClick={() => void app.ask().catch(app.report)}>重试</button><button data-edit-question onClick={() => void app.action({ type: 'retryToDraft', branchId: b.id }).catch(app.report)}>返回草稿</button></>}</div>}
    <form id="composer" onSubmit={e => { e.preventDefault(); void send().catch(app.report); }}>
      <label className="sr-only" htmlFor="draft">继续这条思路</label>
      <textarea id="draft" rows={1} maxLength={64000} placeholder="有什么可以帮你的？" value={b.draft} disabled={Boolean(b.pendingPrompt)} onChange={e => app.draft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) { e.preventDefault(); if (!b.awaiting && !b.pendingPrompt) void send().catch(app.report); } }} />
      <div className="composer-bottom">
        <IconButton icon="plus" label="引用资料" onClick={references} />
        {app.running()
          ? <IconButton className="composer-send composer-stop" data-cancel icon="stop" label="停止生成" onClick={() => app.cancel()} />
          : <IconButton id="send" className="composer-send" type="submit" icon="send" label="发送（Ctrl / Cmd + Enter）" disabled={!sendable} />}
      </div>
    </form>
  </div>;
}

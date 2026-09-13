import { createContext, useContext, useEffect, useRef, useState, useId, type ReactNode } from 'react';
import { Button, IconButton } from './UI.js';
const NestedDialog = createContext(false);

export function Dialog({ title, close, children, confirm, label = '保存', disabled = false, dirty = false, locked = false }: { title: string; close: () => void; children: ReactNode; confirm?: () => Promise<void>; label?: string; disabled?: boolean; dirty?: boolean; locked?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const nested = useContext(NestedDialog);
  const titleId = useId(), formId = useId(), guard = useRef(false);
  const [discard, setDiscard] = useState(false);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { const previous = document.activeElement as HTMLElement | null; const dialog = ref.current!; dialog.showModal(); dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus(); return () => { dialog.close(); previous?.focus(); }; }, []);
  const requestClose = () => { if (busy || locked) return; if (dirty) setDiscard(true); else close(); };
  const submit = async () => { if (guard.current || disabled) return; guard.current = true; setBusy(true); try { await confirm?.(); close(); } catch (e) { setError((e as Error).message); } finally { guard.current = false; setBusy(false); } };
  return <NestedDialog.Provider value={true}><dialog id={nested ? undefined : 'modal'} ref={ref} aria-labelledby={titleId} onCancel={e => { e.preventDefault(); e.stopPropagation(); requestClose(); }}>
    <div className="modal-head"><h2 id={titleId}>{title}</h2><IconButton id={nested ? undefined : 'close-modal'} icon="close" disabled={busy || locked} onClick={requestClose} label="关闭" /></div>
    {confirm && <form id={formId} onSubmit={e => { e.preventDefault(); void submit(); }} />}
    <fieldset className="dialog-content" disabled={busy} onKeyDown={e => { if (confirm && e.key === 'Enter' && e.target instanceof HTMLInputElement && e.target.type !== 'checkbox' && !e.nativeEvent.isComposing) { e.preventDefault(); e.stopPropagation(); void submit(); } }}>
    <div id={nested ? undefined : 'modal-body'} className="modal-body">{children}</div><p id={nested ? undefined : 'modal-error'} className="modal-error" role="alert">{error}</p>
    {confirm && <div id={nested ? undefined : 'modal-actions'} className="modal-actions"><Button onClick={requestClose} disabled={busy}>取消</Button><Button id={nested ? undefined : 'modal-confirm'} type="submit" form={formId} className="primary" disabled={disabled || busy}>{busy ? '处理中…' : label}</Button></div>}
    </fieldset>
    {discard && <ConfirmDialog title="放弃未保存的修改？" close={() => setDiscard(false)} label="放弃修改" confirm={async () => { close(); }}><p>关闭后本次输入不会保存。</p></ConfirmDialog>}
  </dialog></NestedDialog.Provider>;
}

export function ConfirmDialog(props: { title: string; close: () => void; confirm: () => Promise<void>; label: string; children: ReactNode; disabled?: boolean }) {
  return <Dialog {...props} />;
}

export function Pager({ cursor, next, change }: { cursor: number; next: number | null; change: (cursor: number) => void }) {
  return <div className="toolbar"><button disabled={cursor < 0} onClick={() => change(Math.max(-1, cursor - 40))}>上一页</button><span>每页最多 40 条</span><button disabled={next === null} onClick={() => next !== null && change(next)}>下一页</button></div>;
}

import { useEffect, useRef, useState } from 'react';
import type { Entry, Selection } from '../types.js';
import type { WorkspaceController } from '../controller.js';
import { renderMarkdown } from '../render.js';
import { readSelection, restoreSelection } from '../selection.js';
import { Pager } from './Dialog.js';
import { Button, Icon, IconButton } from './UI.js';

export type Jump = { branchId: string; entryId: string; start: number; end: number };

function Message({ entry, app, jump, locate, select }: { entry: Entry; app: WorkspaceController; jump?: Jump; locate: (j: Jump) => void; select: (s: Selection) => void }) {
  const [raw, setRaw] = useState(false); const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (jump?.entryId === entry.id) setRaw(true); }, [jump, entry.id]);
  useEffect(() => { if (raw && jump?.entryId === entry.id && ref.current) { restoreSelection(ref.current, jump.start, jump.end); ref.current.scrollIntoView({ block: 'center' }); } }, [raw, jump, entry.id]);
  return <article className={entry.kind === 'reference' ? 'reference' : `message ${entry.role}`} data-entry={entry.id} data-kind={entry.kind}>
    <header>{entry.kind === 'reference' ? '引用快照' : entry.role === 'user' ? '你' : '知树'}{entry.inherited && ' · 继承背景'}{entry.simulated && ' · 人工示例'}</header>
    <div ref={ref} className="message-text" data-source={entry.text} dangerouslySetInnerHTML={{ __html: raw ? `<span data-source-start="0">${entry.text.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]!)}</span>` : renderMarkdown(entry.text) }} />
    <div className="toolbar"><button aria-pressed={raw} onClick={() => setRaw(!raw)}>{raw ? '返回排版阅读' : '选择原文'}</button>
      {entry.kind === 'message' && <button data-fork disabled={!entry.text.trim()} onClick={() => select({ entryId: entry.id, start: 0, end: entry.text.length, text: entry.text })}>从这里分叉</button>}
      {(entry.kind === 'reference' || entry.inherited) && <button data-jump onClick={() => locate({ branchId: entry.source.branchId, entryId: entry.source.messageId, start: entry.range?.start ?? 0, end: entry.range?.end ?? entry.text.length })}>返回原文</button>}
      {entry.kind === 'reference' && <button className="danger-block" onClick={() => void app.action({ type: 'removeReference', branchId: app.branch!.id, entryId: entry.id }).catch(app.report)}>移除引用</button>}
    </div>
  </article>;
}

export function MessageViewport({ app, select, jump, locate }: { app: WorkspaceController; select: (s: Selection) => void; jump?: Jump; locate: (j: Jump) => void }) {
  const [picked, setPicked] = useState<Selection>();
  const container = useRef<HTMLDivElement>(null), toolbar = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: 0, top: 0 }), [hint, setHint] = useState('');
  useEffect(() => { if (!hint) return; const timer = window.setTimeout(() => setHint(''), 4000); return () => clearTimeout(timer); }, [hint]);
  useEffect(() => {
    let timer = 0;
    const update = () => {
      const selection = window.getSelection(), root = container.current;
      if (!root || document.querySelector('dialog[open]') || !selection || selection.isCollapsed) { setPicked(undefined); return; }
      try {
        const value = readSelection(selection, root), rect = selection.getRangeAt(0).getBoundingClientRect();
        const viewport = root.closest('.chat')!.getBoundingClientRect();
        if (rect.bottom < Math.max(0, viewport.top) || rect.top > Math.min(innerHeight, viewport.bottom) || rect.right < 0 || rect.left > innerWidth) { setPicked(undefined); return; }
        const width = toolbar.current?.offsetWidth || 210, height = toolbar.current?.offsetHeight || 48;
        setPosition({ left: Math.max(8, Math.min(innerWidth - width - 8, rect.left + (rect.width - width) / 2)), top: Math.max(8, Math.min(innerHeight - height - 8, rect.top - height - 8 >= Math.max(8, viewport.top) ? rect.top - height - 8 : rect.bottom + 8)) });
        setPicked(value);
      } catch { setPicked(undefined); }
    };
    const schedule = () => { clearTimeout(timer); timer = window.setTimeout(update, 40); };
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') { clearTimeout(timer); setPicked(undefined); window.getSelection()?.removeAllRanges(); } };
    const outside = (e: PointerEvent) => { if (!toolbar.current?.contains(e.target as Node)) setPicked(undefined); };
    document.addEventListener('selectionchange', schedule); document.addEventListener('pointerup', schedule); document.addEventListener('keydown', escape); document.addEventListener('pointerdown', outside); window.addEventListener('resize', schedule); window.addEventListener('scroll', schedule, true);
    return () => { clearTimeout(timer); document.removeEventListener('selectionchange', schedule); document.removeEventListener('pointerup', schedule); document.removeEventListener('keydown', escape); document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', schedule); window.removeEventListener('scroll', schedule, true); };
  }, []);
  useEffect(() => setPicked(undefined), [app.branch?.id, app.page]);
  return <div id="messages" ref={container}>
    <p className="selection-help">在单条消息中选择文字可展开讨论或复制；公式请切换“选择原文”。</p>
    <Pager cursor={app.page.cursor ?? -1} next={app.page.nextCursor} change={cursor => void app.navigate(cursor).catch(app.report)} />
    {app.page.items.map(entry => <Message key={entry.id} entry={entry} app={app} jump={jump} locate={locate} select={select} />)}
    {picked && <div ref={toolbar} className="selection-toolbar" role="toolbar" aria-label="选区操作" style={position} onPointerDown={e => e.preventDefault()}><Button id="expand-selection" className="primary" onClick={() => { select(picked); setPicked(undefined); }}><Icon name="expand" />展开讨论</Button><IconButton icon="copy" label="复制选中文字" onClick={async () => { try { await navigator.clipboard.writeText(picked.text); setHint('已复制选中文字'); } catch { setHint('复制失败，请使用系统复制菜单或 Ctrl / Cmd + C。'); } }} /></div>}
    {hint && <p className="selection-feedback" role="status">{hint}</p>}
     {app.partial() && <article className="message assistant" id="stream-output" aria-live="polite"><header>知树 · 正在生成</header><div className="message-text" dangerouslySetInnerHTML={{ __html: renderMarkdown(app.partial()) }} /></article>}
  </div>;
}

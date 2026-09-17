import { useEffect, useRef, useState } from 'react';
import { BrandMark, Button, Icon } from './UI.js';
import { useTopics } from '../hooks.js';
import type { WorkspaceController } from '../controller.js';
import { Pager } from './Dialog.js';
import { api } from '../api.js';
import type { BranchMeta } from '../types.js';
import { TopicSettings } from './TopicSettings.js';

export function TopicNavigator({ app, settings, account, logout, references, context, manageCurrent, accountLabel, navigated }: { app: WorkspaceController; settings: () => void; account: () => void; logout?: () => void; references: () => void; context: () => void; manageCurrent: () => void; accountLabel: string; navigated: () => void }) {
  const guard = useRef(false), [busy, setBusy] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const drawer = useRef<HTMLDivElement>(null), closeTimer = useRef(0);
  // Leaving the drawer only schedules a close: the pointer may be travelling towards the menu,
  // and crossing the visual gap between them must not dismiss it.
  const keepAccount = () => clearTimeout(closeTimer.current);
  const closeAccountSoon = () => { clearTimeout(closeTimer.current); closeTimer.current = window.setTimeout(() => setAccountOpen(false), 180); };
  useEffect(() => () => clearTimeout(closeTimer.current), []);
  useEffect(() => {
    if (!accountOpen) return;
    const outside = (event: PointerEvent) => { if (!drawer.current?.contains(event.target as Node)) setAccountOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setAccountOpen(false); };
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [accountOpen]);
  const [managed, setManaged] = useState<BranchMeta>();
  const manageTopic = async (id: string) => { if (guard.current) return; guard.current = true; setBusy(true); try { await app.flush(); setManaged(await api.branch(id)); } catch (e) { app.report(e); } finally { guard.current = false; setBusy(false); } };
  const go = async (id?: string) => { if (guard.current) return; guard.current = true; setBusy(true); try { if (id) await app.action({ type: 'switch', branchId: id }); else if (!(app.branch?.title === '新的学习问题' && !app.branch.parent && !app.branch.draft && !app.page.items.length && app.page.nextCursor === null)) await app.action({ type: 'create', title: '新的学习问题' }); navigated(); } catch (e) { app.report(e); } finally { guard.current = false; setBusy(false); } };
  const [cursor, setCursor] = useState(-1), [search, setSearch] = useState(''), [retry, setRetry] = useState(0);
  const { page, error, loading } = useTopics(cursor, search, app.topicRevision + retry);
  return <nav className="sidebar" aria-label="学习主题">
    <div className="sidebar-head"><a className="brand" href="/" aria-label="知树 首页"><span className="brand-mark"><BrandMark /></span><span className="brand-name">知树</span></a></div>
    <div className="sidebar-scroll">
      <button id="create" className="menu-row" disabled={busy} onClick={() => void go()}><Icon name="new" /><span>新的学习问题</span></button>
      <label className="menu-row menu-row-input"><Icon name="search" /><input id="topic-search" aria-label="搜索主题或标签" placeholder="搜索主题" maxLength={120} value={search} onChange={e => { setSearch(e.target.value); setCursor(-1); }} /></label>
      {search && <button className="menu-row" onClick={() => { setSearch(''); setCursor(-1); }}><Icon name="close" /><span>清除搜索</span></button>}
      <p className="sidebar-label">主题</p>
      <div id="tree" aria-busy={loading}>
        {page.items.map(b => <div className="topic-row" key={b.id}>
          <button data-switch={b.id} disabled={busy} aria-current={app.branch?.id === b.id ? 'page' : undefined} className={`menu-row branch-button ${app.branch?.id === b.id ? 'active' : ''}`} onClick={() => void go(b.id)} title={b.title}>
            <span className="branch-title">{b.kept ? '★ ' : ''}{b.title}</span>
          </button>
          <button className="topic-more" disabled={busy} aria-label={`更多：${b.title}`} title={`整理 ${b.title}`} onClick={() => void manageTopic(b.id)}>···</button>
        </div>)}
        {search && !loading && !page.items.length && !error && <p className="sidebar-note">没有匹配的主题</p>}
        {loading && <p className="sidebar-note" role="status">正在加载…</p>}
        {error && <p className="sidebar-note" role="alert">{error}<Button onClick={() => setRetry(retry + 1)}>重试</Button></p>}
      </div>
      {(cursor >= 0 || page.nextCursor !== null) && <Pager cursor={cursor} next={page.nextCursor} change={setCursor} />}
    </div>
    <div className="sidebar-bottom">
      <span id="connection">本地保存</span>
      <div className="account-drawer" ref={drawer} onPointerEnter={keepAccount} onPointerLeave={closeAccountSoon}>
        <button id="conversation-actions-button" className="menu-row account-trigger" aria-expanded={accountOpen} onClick={() => setAccountOpen(!accountOpen)}>
          <span className="account-avatar">{accountLabel.slice(0, 1).toUpperCase()}</span><span className="branch-title">{accountLabel}</span>
        </button>
        {accountOpen && <div className="account-menu">
          <button id="related-button" disabled={!app.branch} onClick={() => { setAccountOpen(false); references(); }}>引用资料</button>
          <button id="context-button" disabled={!app.branch} onClick={() => { setAccountOpen(false); context(); }}>当前上下文</button>
          <button id="manage-button" disabled={!app.branch} onClick={() => { setAccountOpen(false); manageCurrent(); }}>管理主题</button>
          <hr />
          <button id="settings-button" onClick={() => { setAccountOpen(false); settings(); }}>设置</button>
          <button onClick={() => { setAccountOpen(false); account(); }}>账户</button>
          {logout && <button onClick={() => { setAccountOpen(false); logout(); }}>登出</button>}
        </div>}
      </div>
    </div>
    {managed && <TopicSettings app={app} target={managed} close={() => setManaged(undefined)} />}
  </nav>;
}

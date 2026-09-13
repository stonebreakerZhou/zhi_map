import { useRef, useState } from 'react';
import { Button, Icon } from './UI.js';
import { useTopics } from '../hooks.js';
import type { WorkspaceController } from '../controller.js';
import { Pager } from './Dialog.js';
import { api } from '../api.js';
import type { BranchMeta } from '../types.js';
import { TopicSettings } from './TopicSettings.js';

export function TopicNavigator({ app, settings, navigated }: { app: WorkspaceController; settings: () => void; navigated: () => void }) {
  const guard = useRef(false), [busy, setBusy] = useState(false);
  const [managed, setManaged] = useState<BranchMeta>();
  const manage = async (id: string) => { if (guard.current) return; guard.current = true; setBusy(true); try { await app.flush(); setManaged(await api.branch(id)); } catch (e) { app.report(e); } finally { guard.current = false; setBusy(false); } };
  const go = async (id?: string) => { if (guard.current) return; guard.current = true; setBusy(true); try { if (id) await app.action({ type: 'switch', branchId: id }); else if (!(app.branch?.title === '新的学习问题' && !app.branch.parent && !app.branch.draft && !app.page.items.length && app.page.nextCursor === null)) await app.action({ type: 'create', title: '新的学习问题' }); navigated(); } catch (e) { app.report(e); } finally { guard.current = false; setBusy(false); } };
  const [cursor, setCursor] = useState(-1), [search, setSearch] = useState(''), [retry, setRetry] = useState(0);
  const { page, error, loading } = useTopics(cursor, search, app.topicRevision + retry);
  return <nav className="sidebar" aria-label="学习主题"><a className="brand" href="/">知树<span>把问题想明白</span></a>
    <Button id="create" className="primary" busy={busy} onClick={() => void go()}><Icon name="plus" />新的学习问题</Button>
    <label>搜索主题 / 标签<input id="topic-search" maxLength={120} value={search} onChange={e => { setSearch(e.target.value); setCursor(-1); }} /></label>
    {search && <Button onClick={() => { setSearch(''); setCursor(-1); }}>清除搜索</Button>}
    <div id="tree" aria-busy={loading}>
      {page.items.map(b => <div className="topic-row" key={b.id}>
        <button data-switch={b.id} disabled={busy} aria-current={app.branch?.id === b.id ? 'page' : undefined} className={`branch-button ${app.branch?.id === b.id ? 'active' : ''}`} onClick={() => void go(b.id)}>
          <span>{b.parent ? '↳ ' : ''}{b.title}<small>{b.kept ? '★ ' : ''}{b.tags.join(' · ')}</small></span>
        </button>
        <Button className="topic-more" disabled={busy} aria-label={`更多：${b.title}`} title={`整理 ${b.title}`} onClick={() => void manage(b.id)}>···</Button>
      </div>)}
      {search && !loading && !page.items.length && !error && <p>未找到匹配主题</p>}
    </div>
    {loading && <p role="status">正在加载主题…</p>}<p role="alert">{error}</p>{error && <Button onClick={() => setRetry(retry + 1)}>重试加载主题</Button>}<Pager cursor={cursor} next={page.nextCursor} change={setCursor} />
    <div className="sidebar-bottom"><span id="connection">本地分页存储</span><button id="settings-button" onClick={settings}>设置与数据</button></div>
    {managed && <TopicSettings app={app} target={managed} close={() => setManaged(undefined)} />}
  </nav>;
}

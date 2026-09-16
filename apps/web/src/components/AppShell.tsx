import { Component, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, type AiConfig } from '../api.js';
import { WorkspaceController } from '../controller.js';
import { useWorkspace } from '../hooks.js';
import type { Selection } from '../types.js';
import { TopicNavigator } from './TopicNavigator.js';
import { MessageViewport, type Jump } from './MessageViewport.js';
import { Composer } from './Composer.js';
import { SelectionDialog } from './SelectionDialog.js';
import { ReferencesDialog } from './ReferencesDialog.js';
import { TopicSettings } from './TopicSettings.js';
import { Dialog, ConfirmDialog } from './Dialog.js';
import { AuthModal } from './AuthModal.js';
import { Constellation } from '../graph/Constellation.js';
import { SettingsCenter } from './SettingsCenter.js';
import { TutorialOverlay } from './TutorialOverlay.js';
import { Recovery } from '../graph/Recovery.js';

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false };
  static getDerivedStateFromError() { return { error: true }; }
  render() { return this.state.error ? <main role="alert"><h1>界面暂时无法显示</h1><button onClick={() => location.reload()}>重新加载</button></main> : this.props.children; }
}

export function AppShell() {
  const [controller] = useState(() => new WorkspaceController()); const app = useWorkspace(controller);
  const [modal, setModal] = useState<'' | 'settings' | 'references' | 'topic' | 'context' | 'auth'>(''), [selection, setSelection] = useState<Selection>(), [jump, setJump] = useState<Jump>(), [nav, setNav] = useState(false);
  const [mode, setMode] = useState<'chat' | 'graph'>('chat');
  const [settingsState, setSettingsState] = useState({ dirty: false, busy: false }), [config, setConfig] = useState<AiConfig>();
  const [dataBusy, setDataBusy] = useState(false);
  const [referenceSource, setReferenceSource] = useState<string>();
  const [authState, setAuthState] = useState<{ isLoggedIn: boolean; email?: string | null; name?: string | null }>({ isLoggedIn: false });
  const [logoutConfirm, setLogoutConfirm] = useState(false);
  const [tutorialOpen, setTutorialOpen] = useState(() => localStorage.getItem('zhishu-tutorial-complete') !== '1');
  const createGuard = useRef(false);
  const configChanged = useRef(false);
  const acceptConfig = useCallback((c: AiConfig) => { configChanged.current = true; setConfig(c); }, []);
  // The first workspace response establishes the anonymous session cookie.
  useEffect(() => { if (!app.initialized) return; let live = true; void api.aiConfig().then(c => { if (live && !configChanged.current) setConfig(c); }).catch(() => {}); return () => { live = false; }; }, [app.initialized]);
  const providerState = useCallback((dirty: boolean, busy: boolean) => setSettingsState({ dirty, busy }), []);
  const close = () => { setModal(''); setSelection(undefined); setSettingsState({ dirty: false, busy: false }); };
  const closeConversationModal = () => { close(); requestAnimationFrame(() => document.getElementById('conversation-actions-button')?.focus()); };
  // Refresh auth state whenever the modal closes (covers login/logout).
  const refreshAuth = useCallback(() => { void api.authMe().then(s => setAuthState({ isLoggedIn: s.isLoggedIn, email: s.email ?? null, name: s.name ?? null })).catch(() => {}); }, []);
  useEffect(() => { refreshAuth(); }, [refreshAuth]);
  useEffect(() => {
    if (!nav) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setNav(false); };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', closeOnEscape);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', closeOnEscape); };
  }, [nav]);
  const navigated = () => { setNav(false); setMode('chat'); requestAnimationFrame(() => document.getElementById('draft')?.focus()); };
  const confirmLogout = async () => {
    setLogoutConfirm(false);
    try {
      await api.emailLogout();
      window.location.reload();
    } catch (e) { app.report(e); }
  };
  const newTopic = async () => {
    if (createGuard.current) return;
    createGuard.current = true;
    try {
      if (!(app.branch?.title === '新的学习问题' && !app.branch.parent && !app.branch.draft && !app.page.items.length && app.page.nextCursor === null)) await app.action({ type: 'create', title: '新的学习问题' });
      navigated();
    } catch (e) { app.report(e); }
    finally { createGuard.current = false; }
  };
  const locate = async (target: Jump) => { await app.action({ type: 'switch', branchId: target.branchId }, target.entryId); setJump(target); };
  const branch = app.branch;
  if (!app.initialized) return <main role="status"><h1>正在加载学习空间…</h1><p>{app.notice}</p><button onClick={() => void app.load().catch(app.report)}>重试</button></main>;
  const conversation = <><section className="chat" aria-label="当前讨论"><div id="chat-header"><h1 className="sr-only">{branch?.title ?? '让好奇有迹可循'}</h1>{branch?.selection && <blockquote>{branch.selection.text}</blockquote>}{branch?.parent && <button data-return onClick={() => void locate({ branchId: branch.parent!.branchId, entryId: branch.parent!.entryId, start: branch.selection?.start ?? 0, end: branch.selection?.end ?? 0 }).catch(app.report)}>返回原讨论</button>}{branch?.sourceOrigin && !branch.parent && <p>原父主题已移除；出处快照保留。</p>}</div>
    {branch ? <MessageViewport app={app} select={setSelection} jump={jump} locate={j => void locate(j).catch(app.report)} /> : <div className="onboarding"><p className="onboarding-kicker">把一个问题想清楚</p><h2>从一个问题开始</h2><p>输入问题，得到回答；选中其中一段，就能把思路继续展开。</p><button className="primary" onClick={() => { if (config?.configured) void newTopic(); else setModal('settings'); }}>{config?.configured ? `开始新问题 · ${config.model}` : '先连接模型'}</button></div>}
  </section><Composer app={app} references={() => setModal('references')} /></>;
  return <div className={`graph-workspace mode-${mode} ${nav ? 'nav-open' : ''}`} data-cache-pages={app.cache.size} data-cache-entries={app.cache.entryCount}>
    <a className="skip" href="#draft">跳到输入框</a><TopicNavigator app={app} navigated={navigated} accountLabel={authState.name ?? authState.email ?? '访客'} settings={() => { setNav(false); setModal('settings'); }} account={() => { setNav(false); setModal('auth'); }} logout={authState.isLoggedIn ? () => setLogoutConfirm(true) : undefined} references={() => setModal('references')} context={() => setModal('context')} manageCurrent={() => setModal('topic')} />
    {nav && <button className="nav-backdrop" aria-label="收起主题导航" onClick={() => { setNav(false); document.getElementById('nav-toggle')?.focus(); }} />}
     <main className="workspace"><header className="topbar"><button id="nav-toggle" aria-expanded={nav} onClick={() => setNav(!nav)}>菜单</button><div className="conversation-heading"><strong>{branch?.title ?? '知树'}</strong></div><div className="top-actions"><button className="mode-toggle" disabled={!branch} onClick={() => setMode(mode === 'chat' ? 'graph' : 'chat')}>{mode === 'chat' ? '探索图谱' : '返回对话'}</button></div></header>
       {mode === 'graph' ? <Constellation app={app} restoreReading={setJump} modal={Boolean(modal || selection)} references={source => { setReferenceSource(source); setModal('references'); }} newTopic={() => void newTopic()}>{conversation}</Constellation> : <div className="conversation-stage">{conversation}</div>}
     </main><div id="notice" role="status">{app.notice && <>{app.notice}<button aria-label="关闭提示" onClick={() => { app.notice = ''; app.changed(); }}>关闭</button></>}</div>{app.undoToken && <div id="undo-bar">已删除主题 · 下一次修改前可撤销（最长 10 分钟）<button id="undo" disabled={app.undoBusy} onClick={() => void app.undo().catch(app.report)}>撤销</button></div>}
    <div className="global-recovery"><Recovery app={app} /></div>
    {selection && branch && <SelectionDialog app={app} selection={selection} close={close} />}
    {modal === 'references' && branch && <ReferencesDialog app={app} initialSource={referenceSource} close={() => { setReferenceSource(undefined); closeConversationModal(); }} />}
    {modal === 'topic' && branch && <TopicSettings app={app} close={closeConversationModal} />}
    {modal === 'settings' && <Dialog title="设置" close={close} dirty={settingsState.dirty} locked={settingsState.busy || dataBusy}><SettingsCenter app={app} providerState={providerState} configChanged={acceptConfig} dataBusyChanged={setDataBusy} replayTutorial={() => { close(); setTutorialOpen(true); }} /></Dialog>}
    {modal === 'context' && <Dialog title="当前上下文" close={closeConversationModal}><p>选区原文始终发送并计入 64,000 字符预算；剩余预算保留最近最多 100 条消息。较早背景和历史引用可能被裁剪，发生裁剪时会提示；完整历史仍可分页查看。选区与最新问题超出预算时会阻止生成。</p><button onClick={() => { void app.navigate(-1).catch(app.report); closeConversationModal(); }}>查看最早一页</button></Dialog>}
    {modal === 'auth' && <Dialog title="账户" close={() => { close(); refreshAuth(); }}><AuthModal close={() => { close(); refreshAuth(); }} /></Dialog>}
    {logoutConfirm && <ConfirmDialog title="确认登出？" close={() => setLogoutConfirm(false)} label="确认登出" confirm={confirmLogout}><p>登出后会回到匿名状态。你已保存的内容不会丢失——它们仍归属当前账号，重新登录同邮箱即可继续访问。</p></ConfirmDialog>}
    <TutorialOverlay open={tutorialOpen} close={() => setTutorialOpen(false)} />
  </div>;
}

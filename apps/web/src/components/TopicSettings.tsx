import { useState } from 'react';
import type { WorkspaceController } from '../controller.js';
import { ConfirmDialog, Dialog } from './Dialog.js';
import { Button, InputField } from './UI.js';
import type { BranchMeta } from '../types.js';

export function TopicSettings({ app, close, target }: { app: WorkspaceController; close: () => void; target?: BranchMeta }) {
  const [branch] = useState(target ?? app.branch!);
  const [kept, setKept] = useState(branch.kept);
  const [title, setTitle] = useState(branch.title), [tags, setTags] = useState(branch.tags.join(', ')), [deleting, setDeleting] = useState<'branch' | 'session'>(), [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  return <Dialog title={`整理主题 · ${branch.title}`} close={close} locked={busy} dirty={title !== branch.title || tags !== branch.tags.join(', ')} disabled={!title.trim() || busy} confirm={async () => { await app.action({ type: 'metadata', branchId: branch.id, title: title.trim(), tags: [...new Set(tags.split(/[,，]/).map(t => t.trim()).filter(Boolean))] }); }}>
    <InputField label="标题" id="topic-title" required maxLength={120} value={title} onChange={e => setTitle(e.target.value)} /><InputField label="标签（逗号分隔）" id="topic-tags" maxLength={1000} value={tags} onChange={e => setTags(e.target.value)} />
    <Button busy={busy} onClick={async () => { setBusy(true); try { await app.action({ type: 'keep', branchId: branch.id }); setKept(!kept); } catch (e) { app.report(e); } finally { setBusy(false); } }}>{kept ? '取消收藏' : '收藏主题'}</Button>
    <div className="danger-zone"><h3>移除与删除</h3><p>移除后十分钟内可恢复，独立子分支保留。</p><Button className="danger-block" data-delete-branch onClick={() => { setDeleting('branch'); setConfirmed(false); }}>移除此主题</Button><Button className="danger-block" data-delete-session onClick={() => { setDeleting('session'); setConfirmed(false); }}>删除整个会话主线</Button></div>
    {deleting && <ConfirmDialog title={deleting === 'branch' ? '移除此主题？' : '永久删除整个会话主线？'} close={() => setDeleting(undefined)} label={deleting === 'branch' ? '确认移除主题' : '永久删除会话'} disabled={deleting === 'session' && !confirmed} confirm={async () => { await app.action({ type: 'delete', kind: deleting, targetId: deleting === 'branch' ? branch.id : branch.sessionId }); close(); }}><p>当前主题：<strong>{branch.title}</strong></p><p>{deleting === 'branch' ? '移除该主题及其消息，独立子分支保留并成为根。十分钟内可从最近移除恢复；无关草稿和问答不会使恢复失效。' : '删除该主题所属的整个会话主线及其消息，独立子分支保留。此操作不可撤销。'}</p>{deleting === 'session' && <label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />我确认永久删除整个会话主线</label>}</ConfirmDialog>}
  </Dialog>;
}

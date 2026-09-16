import { useEffect, useState } from 'react';

type KnowledgeItem = { id: string; name: string; type: string; size: number; text: string; addedAt: string };
const DB = 'zhishu-local-knowledge', STORE = 'documents';

function database() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'id' });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function listItems() {
  const db = await database();
  return new Promise<KnowledgeItem[]>((resolve, reject) => { const request = db.transaction(STORE).objectStore(STORE).getAll(); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
}
async function putItem(item: KnowledgeItem) {
  const db = await database();
  return new Promise<void>((resolve, reject) => { const request = db.transaction(STORE, 'readwrite').objectStore(STORE).put(item); request.onsuccess = () => resolve(); request.onerror = () => reject(request.error); });
}
async function deleteItem(id: string) {
  const db = await database();
  return new Promise<void>((resolve, reject) => { const request = db.transaction(STORE, 'readwrite').objectStore(STORE).delete(id); request.onsuccess = () => resolve(); request.onerror = () => reject(request.error); });
}

export function KnowledgeSettings() {
  const [items, setItems] = useState<KnowledgeItem[]>([]), [status, setStatus] = useState('');
  const load = () => void listItems().then(setItems).catch(error => setStatus(error.message));
  useEffect(load, []);
  const add = async (files: FileList | null) => {
    if (!files) return;
    setStatus('正在读取本地资料…');
    try {
      for (const file of Array.from(files)) {
        if (file.size > 4 * 1024 * 1024) throw new Error(`${file.name} 超过 4 MiB，本地资料暂不接收。`);
        const text = await file.text();
        await putItem({ id: crypto.randomUUID(), name: file.name, type: file.type || 'text/plain', size: file.size, text, addedAt: new Date().toISOString() });
      }
      setStatus('资料已保存在此设备。'); load();
    } catch (error) { setStatus((error as Error).message); }
  };
  return <section className="settings-section settings-page"><div className="settings-page-head"><p className="settings-eyebrow">本机数据</p><h3>本地知识库</h3><p>导入 TXT、Markdown、JSON、CSV 等文本文件。内容只保存在当前设备的 IndexedDB，不上传服务器。</p></div><div className="knowledge-note">当前版本用于本地资料管理和后续检索准备，尚不会自动把文件内容加入模型上下文。</div><label className="knowledge-import">添加本地资料<input type="file" multiple accept=".txt,.md,.markdown,.json,.csv,text/plain,text/markdown,application/json,text/csv" onChange={event => void add(event.target.files)} /></label><p role="status">{status}</p><div className="knowledge-list">{items.length ? items.map(item => <article key={item.id}><div><strong>{item.name}</strong><small>{Math.ceil(item.size / 1024)} KiB · {new Date(item.addedAt).toLocaleDateString()}</small></div><button className="danger" onClick={() => void deleteItem(item.id).then(load)}>删除</button></article>) : <p className="empty-state">还没有本地资料。</p>}</div></section>;
}

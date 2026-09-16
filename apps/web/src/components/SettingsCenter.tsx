import { useState } from 'react';
import type { AiConfig } from '../api.js';
import type { WorkspaceController } from '../controller.js';
import { AppearanceSettings } from './AppearanceSettings.js';
import { DataSettings } from './DataSettings.js';
import { KnowledgeSettings } from './KnowledgeSettings.js';
import { ProviderSettings } from './ProviderSettings.js';

type Page = 'general' | 'models' | 'knowledge' | 'data' | 'tutorial';

export function SettingsCenter({ app, providerState, configChanged, dataBusyChanged, replayTutorial }: { app: WorkspaceController; providerState: (dirty: boolean, busy: boolean) => void; configChanged: (config: AiConfig) => void; dataBusyChanged: (busy: boolean) => void; replayTutorial: () => void }) {
  const [page, setPage] = useState<Page>('general');
  const pages: [Page, string, string][] = [['general', '外观与系统', '主题与界面'], ['models', '模型服务', '服务商与默认模型'], ['knowledge', '本地知识库', '设备内资料'], ['data', '数据与备份', '导入和导出'], ['tutorial', '新手教程', '重新查看引导']];
  return <div className="settings-center"><nav className="settings-nav" aria-label="设置分类">{pages.map(([id, label, description]) => <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}><strong>{label}</strong><small>{description}</small></button>)}</nav><div className="settings-panel">
    {page === 'general' && <AppearanceSettings />}
    {page === 'models' && <ProviderSettings state={providerState} changed={configChanged} />}
    {page === 'knowledge' && <KnowledgeSettings />}
    {page === 'data' && <DataSettings app={app} busyChanged={dataBusyChanged} />}
    {page === 'tutorial' && <section className="settings-section settings-page"><div className="settings-page-head"><p className="settings-eyebrow">帮助</p><h3>新手教程</h3><p>重新播放首次进入时的功能提示，不会修改任何数据。</p></div><button className="primary" onClick={replayTutorial}>重新播放教程</button></section>}
  </div></div>;
}

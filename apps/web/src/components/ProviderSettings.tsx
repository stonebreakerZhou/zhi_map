import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { api, type AiConfig } from '../api.js';
import { ConfirmDialog } from './Dialog.js';
import { brandColor, ProviderIcon } from './ProviderIcon.js';
import { Button, InputField } from './UI.js';

const presets = [
  { id: 'openai', name: 'OpenAI', protocol: 'openai', url: 'https://api.openai.com/v1', model: 'gpt-4.1-mini', models: ['gpt-4.1-mini', 'gpt-4.1', 'gpt-4o-mini'], kind: '云端' },
  { id: 'anthropic', name: 'Anthropic', protocol: 'anthropic', url: 'https://api.anthropic.com', model: 'claude-sonnet-4-5', models: ['claude-sonnet-4-5', 'claude-haiku-4-5'], kind: '云端' },
  { id: 'gemini', name: 'Google Gemini', protocol: 'gemini', url: 'https://generativelanguage.googleapis.com/v1beta', model: 'gemini-2.5-flash', models: ['gemini-2.5-flash', 'gemini-2.5-pro'], kind: '云端' },
  { id: 'deepseek', name: 'DeepSeek', protocol: 'openai', url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', models: ['deepseek-chat', 'deepseek-reasoner'], kind: '兼容' },
  { id: 'qwen', name: '阿里云百炼', protocol: 'openai', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', models: ['qwen-plus', 'qwen-max', 'qwen-turbo'], kind: '兼容' },
  { id: 'openrouter', name: 'OpenRouter', protocol: 'openai', url: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4.1-mini', models: ['openai/gpt-4.1-mini', 'anthropic/claude-sonnet-4.5'], kind: '聚合' },
  { id: 'ollama', name: 'Ollama', protocol: 'openai', url: 'http://127.0.0.1:11434/v1', model: 'qwen3:8b', models: ['qwen3:8b', 'llama3.2', 'deepseek-r1:8b'], kind: '本地' },
  { id: 'lmstudio', name: 'LM Studio', protocol: 'openai', url: 'http://127.0.0.1:1234/v1', model: 'local-model', models: ['local-model'], kind: '本地' },
  { id: 'custom', name: '自定义服务商', protocol: 'openai', url: 'https://example.com/v1', model: '', models: [], kind: '自定义' },
];
const defaults = { provider: 'openai', baseUrl: presets[0].url, model: '', timeoutMs: '60000', maxTokens: '4096', temperature: '' };
export function ProviderSettings({ state, changed }: { state: (dirty: boolean, busy: boolean) => void; changed: (c: AiConfig) => void }) {
  const [form, setForm] = useState(defaults), [saved, setSaved] = useState(defaults), [config, setConfig] = useState<AiConfig>();
  const [key, setKey] = useState(''), [visible, setVisible] = useState(false), [feedback, setFeedback] = useState(''), [busy, setBusy] = useState(false), [failed, setFailed] = useState(false), [clear, setClear] = useState(false);
  const guard = useRef(false), live = useRef(false), formRef = useRef<HTMLFormElement>(null);
  const dirty = JSON.stringify(form) !== JSON.stringify(saved) || key !== '';
  const selectedPreset = presets.find(p => p.url.replace(/\/$/, '') === form.baseUrl.replace(/\/$/, '')) ?? presets.find(p => p.id === 'custom')!;
  const identityChanged = form.provider !== saved.provider || form.baseUrl.replace(/\/$/, '') !== saved.baseUrl.replace(/\/$/, '');
  const isHordeDefault = config?.source === 'default';
  const needKey = (config?.source !== 'user' && !isHordeDefault) || identityChanged;
  useEffect(() => { state(dirty, busy); }, [dirty, busy, state]);
  const accept = (c: AiConfig) => { if (!live.current) return; const horde = c.source === 'default'; const f = { provider: horde ? 'openai' : (c.provider ?? 'openai'), baseUrl: horde ? defaults.baseUrl : (c.baseUrl ?? defaults.baseUrl), model: horde ? '' : (c.model ?? ''), timeoutMs: String(c.timeoutMs ?? 60000), maxTokens: String(c.maxTokens ?? 4096), temperature: c.temperature == null ? '' : String(c.temperature) }; setConfig(c); setForm(f); setSaved(f); setKey(''); setVisible(false); changed(c); };
  const load = async (active = () => live.current) => { if (guard.current) return; guard.current = true; setBusy(true); setFailed(false); try { const c = await api.aiConfig(); if (active()) { accept(c); setFeedback(''); } } catch (e) { if (active()) { setFailed(true); setFeedback((e as Error).message); } } finally { if (active()) { guard.current = false; setBusy(false); } } };
  useEffect(() => { live.current = true; let active = true; void load(() => active); return () => { active = false; live.current = false; guard.current = false; }; }, []);
  const field = (name: keyof typeof form, value: string) => setForm(f => ({ ...f, [name]: value }));
  const choosePreset = (id: string) => { const p = presets.find(item => item.id === id); if (!p) return; setKey(''); setVisible(false); setForm(f => ({ ...f, provider: p.protocol, baseUrl: p.url, model: p.model })); };
  const chooseProtocol = (provider: string) => { setKey(''); setVisible(false); setForm(f => ({ ...f, provider, baseUrl: presets.some(p => p.url === f.baseUrl) ? presets.find(p => p.protocol === provider)!.url : f.baseUrl })); };
  const save = async (test: boolean) => {
    if (guard.current || !formRef.current?.reportValidity()) return;
    if (!form.model.trim() || (needKey && !key.trim()) || (key && !key.trim())) { setFeedback('请填写有效模型名称和 API key，不能只有空白。'); return; }
    try { const u = new URL(form.baseUrl); if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password || u.search || u.hash) throw Error(); } catch { setFeedback('地址须为不含凭据、查询参数和片段的 HTTP(S) URL。'); return; }
    guard.current = true; setBusy(true); let persisted = false;
    try {
      accept(await api.saveAiConfig({ ...form, model: form.model.trim(), apiKey: key, timeoutMs: Number(form.timeoutMs), maxTokens: Number(form.maxTokens), temperature: form.temperature === '' ? null : Number(form.temperature) }));
      persisted = true; setFeedback(test ? '配置已保存，正在测试…' : '已保存。密钥不会再次显示。');
      if (test && live.current) { await api.testAiConfig(); if (live.current) setFeedback('配置已保存，连接成功。'); }
    } catch (e) { setFeedback(`${persisted ? '保存成功，但连接测试失败：' : '保存失败：'}${(e as Error).message}`); }
    finally { guard.current = false; setBusy(false); }
  };
  return <section className="settings-section settings-page"><div className="settings-page-head"><p className="settings-eyebrow">AI</p><h3>模型服务</h3><p>先选择服务商，再配置连接和默认模型。当前版本保存一个生效连接，个人配置优先于服务器默认。</p></div><p className="config-status">{config?.configured ? `当前 · ${config.model} · ${config.source === 'user' ? '个人配置' : config.source === 'default' ? '默认免费服务' : '服务器配置'}` : '尚未配置模型'}</p>
    {failed && <Button onClick={() => void load()}>重新加载模型配置</Button>}
    <form ref={formRef} id="ai-settings" onSubmit={e => { e.preventDefault(); void save(false); }}><fieldset disabled={!config || busy}>
      <div className="provider-grid">{presets.map(p => <button type="button" key={p.id} className={`provider-card ${selectedPreset.id === p.id ? 'active' : ''}`} style={{ '--brand': brandColor(p.id) } as CSSProperties} aria-pressed={selectedPreset.id === p.id} onClick={() => choosePreset(p.id)}><ProviderIcon id={p.id} /><strong>{p.name}</strong><small>{p.kind}</small></button>)}</div>
      <label className="field">协议<select id="ai-provider" value={form.provider} onChange={e => chooseProtocol(e.target.value)}><option value="openai">OpenAI compatible</option><option value="anthropic">Anthropic Messages</option><option value="gemini">Gemini</option></select><small>切换协议保留自定义地址，清空本次输入的密钥；使用品牌预设可明确替换地址。</small></label>
      <InputField label="Base URL" id="ai-base-url" type="url" required maxLength={2048} value={form.baseUrl} onChange={e => { setKey(''); setVisible(false); field('baseUrl', e.target.value); }} />
      <label className="field">默认模型<input id="ai-model" required maxLength={200} list="provider-models" value={form.model} onChange={e => field('model', e.target.value)} /><datalist id="provider-models">{selectedPreset.models.map(model => <option key={model} value={model} />)}</datalist><small>模型列表是常用示例，可直接填写账号或本地服务实际提供的模型 ID。</small></label>
      <InputField label={isHordeDefault && !identityChanged ? 'API key（留空使用公网 AI Horde，无需密钥）' : needKey ? 'API key（此连接必须填写）' : 'API key（留空保留当前连接密钥）'} hint={identityChanged ? '协议或地址已更改：必须输入该服务的密钥，不会自动使用旧密钥。' : isHordeDefault ? '当前使用公网 AI Horde，无需密钥；配置个人模型时才需要填写。' : '密钥加密保存，已保存的密钥不会返回浏览器。'} id="ai-key" type={visible ? 'text' : 'password'} autoComplete="new-password" required={needKey} maxLength={4096} value={key} onChange={e => setKey(e.target.value)} />
      <Button aria-pressed={visible} disabled={!key} onClick={() => setVisible(!visible)}>{visible ? '隐藏本次输入' : '显示本次输入'}</Button>
      <details><summary>高级参数</summary><InputField label="超时（毫秒）" id="ai-timeout" type="number" required min={100} max={600000} step={1} value={form.timeoutMs} onChange={e => field('timeoutMs', e.target.value)} /><InputField label="最大输出 tokens" type="number" required min={1} max={65536} step={1} value={form.maxTokens} onChange={e => field('maxTokens', e.target.value)} /><InputField label="Temperature（可选）" type="number" min={0} max={1} step={0.1} value={form.temperature} onChange={e => field('temperature', e.target.value)} /></details>
      <div className="settings-actions toolbar"><Button id="save-ai-config" type="submit" busy={busy}>保存</Button><Button className="primary" busy={busy} onClick={() => void save(true)}>保存并测试</Button></div>
      <div className="danger-zone"><Button className="danger" disabled={config?.source !== 'user'} onClick={() => setClear(true)}>清除个人模型配置</Button></div>
    </fieldset></form><p id="ai-settings-feedback" role="status">{busy && !config ? '正在加载配置…' : feedback}</p>
    {clear && <ConfirmDialog title="清除个人模型配置？" close={() => setClear(false)} label="确认清除" confirm={async () => { accept(await api.clearAiConfig()); setFeedback('个人配置已清除，已刷新当前生效状态。'); }}><p>将删除加密保存的个人密钥及模型参数，并放弃本次表单修改。服务器环境配置若存在将重新生效；会话和消息不受影响。</p></ConfirmDialog>}
  </section>;
}

import { useEffect, useState } from 'react';

export type ThemePreference = 'system' | 'light' | 'dark';

export function applyTheme(preference: ThemePreference) {
  document.documentElement.dataset.theme = preference;
  localStorage.setItem('zhishu-theme', preference);
}

export function AppearanceSettings() {
  const [theme, setTheme] = useState<ThemePreference>(() => (localStorage.getItem('zhishu-theme') as ThemePreference | null) ?? 'system');
  useEffect(() => applyTheme(theme), [theme]);
  return <section className="settings-section settings-page"><div className="settings-page-head"><p className="settings-eyebrow">界面</p><h3>外观</h3><p>跟随系统，或固定使用浅色与深色主题。</p></div><div className="theme-grid">
    {([['system', '跟随系统', '根据设备外观自动切换'], ['light', '浅色', '明亮、适合长文阅读'], ['dark', '深色', '低光环境下减少眩光']] as const).map(([value, title, description]) => <button key={value} className={`theme-choice ${theme === value ? 'active' : ''}`} aria-pressed={theme === value} onClick={() => setTheme(value)}><span className={`theme-preview theme-${value}`} /><strong>{title}</strong><small>{description}</small></button>)}
  </div></section>;
}

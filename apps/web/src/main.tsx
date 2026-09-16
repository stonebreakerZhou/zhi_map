import { createRoot } from 'react-dom/client';
import { AppShell, ErrorBoundary } from './components/AppShell.js';
import { applyTheme, type ThemePreference } from './components/AppearanceSettings.js';
import './style.css';

applyTheme((localStorage.getItem('zhishu-theme') as ThemePreference | null) ?? 'system');
createRoot(document.getElementById('root')!).render(<ErrorBoundary><AppShell /></ErrorBoundary>);

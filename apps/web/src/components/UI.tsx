import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react';

export function Icon({ name }: { name: 'copy' | 'expand' | 'plus' | 'close' | 'settings' }) {
  const paths = { copy: 'M9 9h11v11H9z M15 5V3H3v12h2', expand: 'M4 4h16v12H9l-5 4z M8 9h8 M12 6v6', plus: 'M12 5v14 M5 12h14', close: 'M6 6l12 12 M18 6L6 18', settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6' };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
export function Button({ busy, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) {
  return <button type="button" {...props} disabled={props.disabled || busy} aria-busy={busy || undefined}>{children}</button>;
}
export function IconButton({ label, icon, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; icon: Parameters<typeof Icon>[0]['name'] }) {
  return <Button {...props} className={`icon-button ${props.className ?? ''}`} aria-label={label} title={label}><Icon name={icon} /></Button>;
}
export function InputField({ label, hint, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: ReactNode }) {
  return <label className="field">{label}<input {...props} />{hint && <small>{hint}</small>}</label>;
}

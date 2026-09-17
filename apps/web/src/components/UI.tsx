import { useEffect, useRef } from 'react';
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react';

export function Icon({ name }: { name: 'copy' | 'check' | 'expand' | 'plus' | 'close' | 'settings' | 'link' | 'chevron' | 'source' | 'branch' | 'jump' | 'trash' | 'send' | 'stop' | 'search' | 'new' }) {
  const paths = {
    copy: 'M9 9h11v11H9z M15 5V3H3v12h2',
    check: 'M5 13l4 4L19 7',
    expand: 'M4 4h16v12H9l-5 4z M8 9h8 M12 6v6',
    plus: 'M12 5v14 M5 12h14',
    close: 'M6 6l12 12 M18 6L6 18',
    settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
    link: 'M10 13a4 4 0 0 0 5.66 0l2.83-2.83a4 4 0 0 0-5.66-5.66l-1.41 1.41 M14 11a4 4 0 0 0-5.66 0L5.51 13.83a4 4 0 0 0 5.66 5.66l1.41-1.41',
    chevron: 'M6 9l6 6 6-6',
    source: 'M4 6h16 M4 11h16 M4 16h9',
    branch: 'M7 4v7a4 4 0 0 0 4 4h6 M14 12l3 3-3 3',
    jump: 'M19 12H5 M11 6l-6 6 6 6',
    trash: 'M4 7h16 M9 7V5h6v2 M6 7l1 13h10l1-13',
    send: 'M12 19V5 M6 11l6-6 6 6',
    stop: 'M7 7h10v10H7z',
    search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16 M21 21l-4.3-4.3',
    new: 'M4 20h4L18 10l-4-4L4 16z M14 6l4 4',
  };
  const ref = useRef<SVGSVGElement>(null), first = useRef(true);
  useEffect(() => { if (first.current) { first.current = false; return; } const el = ref.current; if (!el) return; el.classList.remove('icon-swap'); void el.getBoundingClientRect(); el.classList.add('icon-swap'); }, [name]);
  return <svg ref={ref} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
/** Zhishu mark: a trunk whose crown is three connected nodes — a tree and a constellation at once. */
export function BrandMark({ size = 24 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
    <path d="M12 21V10" /><path d="M12 15.5 6.6 11.6" /><path d="M12 15.5 17.4 11.6" />
    <circle cx="12" cy="7.8" r="2.2" /><circle cx="6.6" cy="10.4" r="1.7" /><circle cx="17.4" cy="10.4" r="1.7" />
  </svg>;
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

import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { Button, InputField } from './UI.js';

type Mode = 'login' | 'register' | 'password' | 'reset';
type Step = 'form' | 'code';

/** Zhihu's app mark — blue rounded square with the white 「知乎」 characters.
 *  Drawn inline so the button needs no image request and works offline. */
function ZhihuMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: 0 }}>
      <defs>
        <linearGradient id="zhihu-mark-gradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3FA9FF" />
          <stop offset="1" stopColor="#0084FF" />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="6" fill="url(#zhihu-mark-gradient)" />
      <text
        x="12" y="12.4" textAnchor="middle" dominantBaseline="central"
        fill="#ffffff" fontSize="10" fontWeight="700"
        fontFamily="'PingFang SC','Microsoft YaHei','Noto Sans SC',sans-serif"
      >
        知乎
      </text>
    </svg>
  );
}

export function AuthModal({ close }: { close: () => void }) {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);
  const [mode, setMode] = useState<Mode>('login');
  const [step, setStep] = useState<Step>('form');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [hint, setHint] = useState('');
  const [busy, setBusy] = useState(false);
  const guard = useRef(false);

  // Detect whether we are already logged in so the "change password" tab shows.
  useEffect(() => {
    let live = true;
    void api.authMe().then(s => {
      if (!live) return;
      setLoggedIn(s.isLoggedIn);
      if (s.isLoggedIn) {
        setMode('password');
        setEmail(s.email ?? '');
      }
    }).catch(() => {});
    return () => { live = false; };
  }, []);

  const switchMode = (next: Mode) => {
    setMode(next);
    setStep('form');
    setPassword('');
    setCode('');
    setOldPassword('');
    setNewPassword('');
    setHint('');
  };

  const startCode = async () => {
    if (guard.current) return;
    guard.current = true;
    setBusy(true);
    setHint('');
    try {
      await api.emailStart(email.trim());
      const subject = mode === 'reset' ? '【知树】密码重置验证码' : '【知树】邮箱验证码';
      setHint(`${subject}已发送至你的邮箱，请查收。`);
      setStep('code');
    } catch (e) {
      setHint((e as Error).message);
    } finally {
      guard.current = false;
      setBusy(false);
    }
  };

  const submit = async () => {
    if (guard.current) return;
    if ((mode === 'register' || mode === 'reset') && step === 'form') { void startCode(); return; }
    guard.current = true;
    setBusy(true);
    setHint('');
    try {
      if (mode === 'password') {
        if (newPassword !== newPassword.trim() || newPassword.length < 8) {
          throw new Error('新密码至少 8 位。');
        }
        await api.changePassword({ oldPassword, newPassword });
        setHint('密码已更新，请重新登录。');
        setTimeout(() => window.location.reload(), 800);
        return;
      }
      if (mode === 'reset') {
        if (newPassword !== newPassword.trim() || newPassword.length < 8) {
          throw new Error('新密码至少 8 位。');
        }
        await api.resetPassword({ email: email.trim(), code: code.trim(), newPassword });
        setHint('密码已重置，请用新密码登录。');
        setTimeout(() => window.location.reload(), 800);
        return;
      }
      if (mode === 'register') {
        await api.emailRegister({ email: email.trim(), code: code.trim(), password });
      } else {
        await api.emailLogin({ email: email.trim(), password });
      }
      window.location.reload();
    } catch (e) {
      setHint((e as Error).message);
    } finally {
      guard.current = false;
      setBusy(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !busy) { e.preventDefault(); void submit(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy, mode, step, email, password, code, oldPassword, newPassword]);

  const isError = /不正确|错误|失败|过期|已注册|不能/.test(hint);

  const tab = (id: Mode, label: string) => (
    <button role="tab" aria-selected={mode === id} className={mode === id ? 'primary' : ''} onClick={() => switchMode(id)}>{label}</button>
  );

  return <>
    {loggedIn !== true && (
      <a
        href="/api/auth/zhihu/start"
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          width: '100%', boxSizing: 'border-box',
          padding: '10px 14px', marginBottom: 12,
          background: 'var(--accent)', color: 'var(--on-accent)',
          borderRadius: 8,
          textDecoration: 'none', fontSize: 14, fontWeight: 600,
          boxShadow: '0 5px 14px rgba(78, 80, 168, .2)',
        }}
      >
        <ZhihuMark />
        用知乎账号登录
      </a>
    )}
    <div className="toolbar" role="tablist" aria-label="账户操作" style={{ marginBottom: 8 }}>
      {tab('login', '登录')}
      {tab('register', '邮箱注册')}
      {tab('reset', '忘记密码')}
      {loggedIn === true && tab('password', '修改密码')}
    </div>

    {mode === 'password' ? (
      <>
        <p className="config-status">当前账号：{email}</p>
        <InputField label="当前密码" id="auth-old-password" type="password" required minLength={8} maxLength={128} autoComplete="current-password" value={oldPassword} onChange={e => setOldPassword(e.target.value)} />
        <InputField label="新密码（至少 8 位）" id="auth-new-password" type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={newPassword} onChange={e => setNewPassword(e.target.value)} />
        <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--muted)' }}>修改成功后所有设备会自动登出，需要用新密码重新登录。</p>
      </>
    ) : mode === 'reset' && step === 'code' ? (
      <>
        <p className="config-status">重置验证码已发送至 {email}</p>
        <InputField label="验证码（6 位）" id="auth-code" inputMode="numeric" autoComplete="one-time-code" required pattern="\d{6}" maxLength={6} value={code} onChange={e => setCode(e.target.value)} />
        <InputField label="新密码（至少 8 位）" id="auth-new-password" type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={newPassword} onChange={e => setNewPassword(e.target.value)} />
        <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--muted)' }}>重置成功后该账号所有设备会自动登出。</p>
      </>
    ) : mode === 'register' && step === 'code' ? (
      <>
        <p className="config-status">验证码已发送至 {email}</p>
        <InputField label="验证码（6 位）" id="auth-code" inputMode="numeric" autoComplete="one-time-code" required pattern="\d{6}" maxLength={6} value={code} onChange={e => setCode(e.target.value)} />
        <InputField label="设置密码（至少 8 位）" id="auth-password" type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} />
      </>
    ) : (
      <>
        <InputField label="邮箱" id="auth-email" type="email" required maxLength={254} autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} />
        {mode === 'login' && (
          <>
            <InputField label="密码" id="auth-password" type="password" required minLength={8} maxLength={128} autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} />
            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--muted)' }}>
              忘了密码？<button type="button" onClick={() => switchMode('reset')} style={{ background: 'none', border: 0, padding: 0, color: 'var(--accent-text)', cursor: 'pointer', textDecoration: 'underline' }}>用邮箱重置</button>
            </p>
          </>
        )}
        {mode === 'reset' && (
          <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--muted)' }}>我们会向该邮箱发送 6 位验证码，凭验证码重设密码。该邮箱必须已经注册。</p>
        )}
      </>
    )}

    <p id="auth-hint" role="status" style={{ minHeight: '1.5em', margin: '8px 0 16px', color: isError ? 'var(--danger)' : 'var(--muted)' }}>{hint}</p>

    <div className="toolbar" style={{ justifyContent: 'flex-end' }}>
      {(mode === 'register' || mode === 'reset') && step === 'code' && (
        <Button onClick={() => { setStep('form'); setCode(''); setHint(''); }}>返回修改邮箱</Button>
      )}
      <Button onClick={close}>取消</Button>
      <Button className="primary" busy={busy} onClick={() => void submit()}>
        {mode === 'login' ? '登录' : mode === 'password' ? '更新密码' : mode === 'reset' ? (step === 'form' ? '发送重置验证码' : '完成重置') : (step === 'form' ? '发送验证码' : '完成注册')}
      </Button>
    </div>
  </>;
}
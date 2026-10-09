import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { KeyRound, LogOut } from 'lucide-react';
import seal from '../assets/brand/crms-seal.svg';
import { useAuth } from '../contexts/AuthContext';
import { getErrorMessage } from '../services/api';
import { FieldHint } from '../components/ui';
import { PASSWORD_MIN_LENGTH } from '../utils/constants';

export default function ChangePassword() {
  const { user, changePassword, logout } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ current: '', next: '', confirm: '' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const forced = Boolean(user?.must_change_password);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (form.next !== form.confirm) { setError('The new passwords do not match.'); return; }
    if (form.next.length < PASSWORD_MIN_LENGTH) { setError(`Use at least ${PASSWORD_MIN_LENGTH} characters.`); return; }
    setSaving(true);
    try {
      await changePassword(form.current, form.next);
      toast.success('Password changed. Other sessions have been signed out.');
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(getErrorMessage(err, 'Could not change the password.'));
    } finally {
      setSaving(false);
    }
  };

  const field = (key, label, autoComplete) => (
    <div className="form-group">
      <label className="form-label" htmlFor={`pw-${key}`}>{label}</label>
      <input id={`pw-${key}`} className="form-control" type="password" required autoComplete={autoComplete}
        value={form[key]} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))} />
    </div>
  );

  return (
    <main className="auth-page">
      <div className="auth-card">
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <img className="auth-emblem" src={seal} alt="" aria-hidden="true" width="56" height="56" />
          <h1 className="auth-title">{forced ? 'Set a new password' : 'Change password'}</h1>
          <p className="auth-subtitle">
            {forced
              ? 'Your password was issued by an administrator or is a published demo password. Choose a new one to continue.'
              : 'Changing your password signs out your other sessions.'}
          </p>
        </div>
        <form onSubmit={submit} noValidate>
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          {field('current', 'Current password', 'current-password')}
          {field('next', 'New password', 'new-password')}
          <FieldHint>At least {PASSWORD_MIN_LENGTH} characters. Long passphrases are best; common or published passwords are rejected.</FieldHint>
          <div style={{ height: 12 }} />
          {field('confirm', 'Confirm new password', 'new-password')}
          <button className="btn btn-primary btn-lg" style={{ width: '100%' }} disabled={saving}>
            {saving ? <><span className="spinner" aria-hidden="true" /> Saving…</> : <><KeyRound size={15} aria-hidden="true" /> Update password</>}
          </button>
        </form>
        <div style={{ textAlign: 'center', marginTop: 16 }}>
          {forced ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={logout}><LogOut size={13} aria-hidden="true" /> Sign out</button>
          ) : (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate(-1)}>Cancel</button>
          )}
        </div>
      </div>
    </main>
  );
}

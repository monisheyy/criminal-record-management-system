import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { AlertTriangle, BrainCircuit, FileLock2, KeyRound, Lock, ScrollText, Shield, User } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { getErrorMessage } from '../services/api';

// Demo shortcuts exist only in development builds (or when explicitly enabled
// for a demo deployment). Production bundles never advertise credentials.
const SHOW_DEMO_LOGIN = import.meta.env.DEV || import.meta.env.VITE_SHOW_DEMO_LOGIN === 'true';
const DEMO_ACCOUNTS = [
  ['Admin', 'admin', 'admin123'],
  ['Officer', 'officer1', 'officer123'],
  ['Clerk', 'clerk1', 'clerk123'],
];

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ username: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (user) return <Navigate to={user.must_change_password ? '/change-password' : '/dashboard'} replace />;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const signedIn = await login(form.username.trim(), form.password);
      if (signedIn.must_change_password) {
        navigate('/change-password', { replace: true });
      } else {
        toast.success('Signed in');
        navigate(location.state?.from || '/dashboard', { replace: true });
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Sign-in failed.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-brand" aria-label="About AI-CRMS">
        <div className="login-logo">
          <span className="login-logo-mark" aria-hidden="true"><Shield size={20} /></span>
          AI-CRMS
        </div>
        <div>
          <h2 className="login-headline">Case intelligence with <span>accountability built in.</span></h2>
          <p className="login-lede">
            One secure workspace for offender records, FIR case files, evidence custody and human-reviewed
            AI decision support.
          </p>
          <ul className="login-features">
            <li><span className="login-feature-icon" aria-hidden="true"><FileLock2 size={16} /></span>
              <span><strong>Role- and case-level access</strong>Officers see their own investigations; every export is audited.</span></li>
            <li><span className="login-feature-icon" aria-hidden="true"><ScrollText size={16} /></span>
              <span><strong>Tamper-evident audit trail</strong>Append-only, signed entries you can verify at any time.</span></li>
            <li><span className="login-feature-icon" aria-hidden="true"><BrainCircuit size={16} /></span>
              <span><strong>AI that stays advisory</strong>Every model output needs a reasoned human review.</span></li>
          </ul>
        </div>
        <p className="login-foot">Restricted system · Unauthorised access is prohibited and monitored.</p>
      </section>

      <div className="login-panel">
      <div className="login-card">
        <div style={{ marginBottom: 26 }}>
          <h1 className="auth-title">Welcome back</h1>
          <p className="auth-subtitle">Sign in to the Criminal Records Management System.</p>
        </div>

        {SHOW_DEMO_LOGIN && (
          <div className="demo-access" role="note">
            <div className="demo-access-title"><KeyRound size={12} aria-hidden="true" /> Development demo accounts</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
              {DEMO_ACCOUNTS.map(([role, username, password]) => (
                <button key={username} type="button" className="btn btn-secondary btn-sm"
                  onClick={() => setForm({ username, password })} aria-label={`Fill in the ${role} demo account`}>
                  {role}
                </button>
              ))}
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {error && (
            <div className="alert alert-error" role="alert">
              <AlertTriangle size={14} aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}

          <div className="form-group">
            <label className="form-label" htmlFor="login-username">Username</label>
            <div className="input-with-icon">
              <User size={15} aria-hidden="true" />
              <input id="login-username" className="form-control" type="text" value={form.username}
                onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                required autoComplete="username" autoFocus />
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: 24 }}>
            <label className="form-label" htmlFor="login-password">Password</label>
            <div className="input-with-icon">
              <Lock size={15} aria-hidden="true" />
              <input id="login-password" className="form-control" type="password" value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                required autoComplete="current-password" />
            </div>
          </div>

          <button type="submit" className="btn btn-primary btn-lg" style={{ width: '100%' }} disabled={loading}>
            {loading ? <><span className="spinner" aria-hidden="true" /> Signing in…</> : 'Sign in'}
          </button>
        </form>

        <div style={{ textAlign: 'right', marginTop: 12 }}>
          <Link to="/forgot-password" style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Forgot password?</Link>
        </div>

        <p className="auth-footer">Authorized personnel only. All activity is audited.</p>
      </div>
      </div>
    </main>
  );
}

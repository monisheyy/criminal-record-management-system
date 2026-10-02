import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { AlertTriangle, KeyRound, Lock, Shield, User } from 'lucide-react';
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
    <main className="auth-page">
      <div className="auth-card">
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div className="auth-logo" aria-hidden="true"><Shield size={20} /></div>
          <h1 className="auth-title">AI-CRMS</h1>
          <p className="auth-subtitle">Criminal Records Management System</p>
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
    </main>
  );
}

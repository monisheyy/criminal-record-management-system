import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Lock, User } from 'lucide-react';
import monogram from '../assets/brand/crms-monogram.svg';
import seal from '../assets/brand/crms-seal.svg';
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
    <div className="signin">
      <header className="signin-bar">
        <img className="brand-mark" src={monogram} alt="" aria-hidden="true" width="24" height="24" />
        AI-CRMS
      </header>

      <main className="signin-main">
        <div className="signin-card">
          <img className="signin-emblem" src={seal} alt="AI-CRMS seal" width="112" height="112" />
          <h1 className="signin-title">Sign in to AI-CRMS</h1>
          <p className="signin-sub">Criminal records, case files and evidence — in one place.</p>

          <form onSubmit={handleSubmit}>
            {error && <div className="alert alert-error" role="alert"><span>{error}</span></div>}

            <div className="form-group">
              <label className="form-label" htmlFor="login-username">Username</label>
              <div className="input-with-icon">
                <User size={16} aria-hidden="true" />
                <input id="login-username" className="form-control" type="text" value={form.username}
                  onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                  required autoComplete="username" autoFocus />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: 22 }}>
              <label className="form-label" htmlFor="login-password">Password</label>
              <div className="input-with-icon">
                <Lock size={16} aria-hidden="true" />
                <input id="login-password" className="form-control" type="password" value={form.password}
                  onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                  required autoComplete="current-password" />
              </div>
            </div>

            <button type="submit" className="btn btn-primary btn-lg" style={{ width: '100%' }} disabled={loading}>
              {loading ? <><span className="spinner" aria-hidden="true" /> Signing in…</> : 'Sign in'}
            </button>
          </form>

          <p style={{ marginTop: 20, fontSize: '0.9rem' }}>
            <Link to="/forgot-password">Forgot password?</Link>
          </p>

          {SHOW_DEMO_LOGIN && (
            <p className="signin-demo" role="note">
              Development accounts:
              {DEMO_ACCOUNTS.map(([role, username, password]) => (
                <button key={username} type="button" onClick={() => setForm({ username, password })}
                  aria-label={`Fill in the ${role} demo account`}>{role}</button>
              ))}
            </p>
          )}
        </div>
      </main>

      <footer className="signin-foot">
        <span>Authorized personnel only. All activity is recorded.</span>
        <span>Restricted system</span>
      </footer>
    </div>
  );
}

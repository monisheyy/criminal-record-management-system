import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import toast from 'react-hot-toast';
import { Lock, User, Shield, KeyRound, AlertTriangle, FileKey } from 'lucide-react';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(form.username, form.password);
      toast.success('Authentication verified');
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid system credentials');
    } finally {
      setLoading(false);
    }
  };

  const quickLogin = (username, password) => {
    setForm({ username, password });
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-base)',
      padding: '20px',
      position: 'relative'
    }}>
      {/* Precision Grid Pattern Background Overlay */}
      <div style={{
        position: 'absolute',
        inset: 0,
        backgroundImage: 'linear-gradient(to right, rgba(255, 255, 255, 0.03) 1px, transparent 1px), linear-gradient(to bottom, rgba(255, 255, 255, 0.03) 1px, transparent 1px)',
        backgroundSize: '24px 24px',
        pointerEvents: 'none'
      }} />

      <div style={{
        width: '100%',
        maxWidth: '400px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-overlay)',
        padding: '28px 24px',
        position: 'relative',
        zIndex: 1
      }}>
        {/* Security Classification Badge Header */}
        <div style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '0.62rem',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          background: 'var(--bg-base)',
          color: 'var(--status-amber)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          padding: '4px 8px',
          textAlign: 'center',
          marginBottom: '20px'
        }}>
          RESTRICTED SYSTEM // AUTHENTICATION GATEWAY
        </div>

        {/* Branding & Logo */}
        <div style={{ textAlign: 'center', marginBottom: '20px' }}>
          <div style={{
            width: '40px',
            height: '40px',
            background: 'var(--accent-blue)',
            color: 'white',
            borderRadius: 'var(--radius-md)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '10px'
          }}>
            <Shield size={20} />
          </div>
          <h1 style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            AI-CRMS
          </h1>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '2px' }}>
            Criminal Intelligence Management Platform
          </p>
        </div>

        {/* System Access Presets Panel */}
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '10px 12px',
          marginBottom: '18px'
        }}>
          <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <FileKey size={12} /> System Access Presets
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px' }}>
            {[
              ['Admin', 'admin', 'admin123'],
              ['Officer', 'officer1', 'officer123'],
              ['Clerk', 'clerk1', 'clerk123'],
            ].map(([role, u, p]) => (
              <button
                key={u}
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => quickLogin(u, p)}
                style={{ fontSize: '0.72rem', padding: '3px 4px' }}
              >
                {role}
              </button>
            ))}
          </div>
        </div>

        {/* Login Form */}
        <form onSubmit={handleSubmit}>
          {error && (
            <div className="alert alert-error">
              <AlertTriangle size={14} />
              <span>{error}</span>
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Username</label>
            <div style={{ position: 'relative' }}>
              <User size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                className="form-control"
                style={{ paddingLeft: '32px' }}
                type="text"
                placeholder="Enter username"
                value={form.username}
                onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                required
                autoComplete="username"
              />
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: '20px' }}>
            <label className="form-label">Password</label>
            <div style={{ position: 'relative' }}>
              <Lock size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                className="form-control"
                style={{ paddingLeft: '32px' }}
                type="password"
                placeholder="Enter password"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                required
                autoComplete="current-password"
              />
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-lg"
            style={{ width: '100%' }}
            disabled={loading}
          >
            {loading ? (
              <><span className="spinner" /> Authenticating...</>
            ) : (
              <><Shield size={15} /> Verify Access</>
            )}
          </button>
        </form>

        <div className="mono" style={{
          textAlign: 'center',
          fontSize: '0.62rem',
          color: 'var(--text-muted)',
          marginTop: '18px',
          paddingTop: '12px',
          borderTop: '1px solid var(--border)'
        }}>
          COMPLIANCE NOTICE: ALL SESSIONS LOGGED & AUDITED
        </div>
      </div>
    </div>
  );
}

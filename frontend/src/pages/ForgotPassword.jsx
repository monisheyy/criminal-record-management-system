import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, KeyRound, Shield } from 'lucide-react';
import { authAPI, getErrorMessage } from '../services/api';
import { FieldHint } from '../components/ui';
import { PASSWORD_MIN_LENGTH } from '../utils/constants';

const STEP_LABEL = { request: 'Step 1 of 3', otp: 'Step 2 of 3', reset: 'Step 3 of 3' };

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [step, setStep] = useState('request');
  const [identifier, setIdentifier] = useState('');
  const [otp, setOtp] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (step === 'reset') {
      if (password !== confirmation) { setError('The passwords do not match.'); return; }
      if (password.length < PASSWORD_MIN_LENGTH) { setError(`Use at least ${PASSWORD_MIN_LENGTH} characters.`); return; }
    }
    setLoading(true);
    try {
      if (step === 'request') {
        await authAPI.requestRecovery(identifier.trim());
        toast.success('If the account exists, a verification code has been issued.');
        setStep('otp');
      } else if (step === 'otp') {
        const res = await authAPI.verifyRecovery(identifier.trim(), otp);
        setResetToken(res.data.reset_token);
        setStep('reset');
      } else {
        await authAPI.resetPassword(resetToken, password);
        toast.success('Password reset. All previous sessions were signed out.');
        navigate('/login');
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to complete recovery.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-page">
      <div className="auth-card">
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div className="auth-logo" aria-hidden="true"><Shield size={20} /></div>
          <h1 className="auth-title">Account recovery</h1>
          <p className="auth-subtitle">{STEP_LABEL[step]}</p>
        </div>
        <form onSubmit={submit}>
          {error && <div className="alert alert-error" role="alert"><span>{error}</span></div>}
          {step === 'request' && (
            <div className="form-group">
              <label className="form-label" htmlFor="recovery-identifier">Username or email</label>
              <input id="recovery-identifier" className="form-control" value={identifier} onChange={(e) => setIdentifier(e.target.value)}
                required autoComplete="username" />
            </div>
          )}
          {step === 'otp' && (
            <div className="form-group">
              <label className="form-label" htmlFor="recovery-otp">Verification code</label>
              <input id="recovery-otp" className="form-control" value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                required inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" />
              <FieldHint>Enter the 6-digit code. It expires shortly and can only be used once.</FieldHint>
            </div>
          )}
          {step === 'reset' && (
            <>
              <div className="form-group">
                <label className="form-label" htmlFor="recovery-password">New password</label>
                <input id="recovery-password" className="form-control" type="password" value={password}
                  onChange={(e) => setPassword(e.target.value)} required minLength={PASSWORD_MIN_LENGTH} autoComplete="new-password" />
                <FieldHint>At least {PASSWORD_MIN_LENGTH} characters; common passwords are rejected.</FieldHint>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="recovery-confirm">Confirm new password</label>
                <input id="recovery-confirm" className="form-control" type="password" value={confirmation}
                  onChange={(e) => setConfirmation(e.target.value)} required minLength={PASSWORD_MIN_LENGTH} autoComplete="new-password" />
              </div>
            </>
          )}
          <button className="btn btn-primary btn-lg" style={{ width: '100%' }} disabled={loading}>
            {loading ? <><span className="spinner" aria-hidden="true" /> Processing…</>
              : step === 'request' ? 'Send verification code'
              : step === 'otp' ? <><KeyRound size={15} aria-hidden="true" /> Verify code</>
              : 'Set new password'}
          </button>
        </form>
        <div className="auth-footer">
          <Link to="/login" style={{ color: 'var(--text-secondary)', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <ArrowLeft size={13} aria-hidden="true" /> Back to sign in
          </Link>
        </div>
      </div>
    </main>
  );
}

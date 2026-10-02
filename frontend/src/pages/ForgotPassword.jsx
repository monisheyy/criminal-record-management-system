import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, KeyRound, Shield } from 'lucide-react';
import { authAPI } from '../services/api';

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
    e.preventDefault(); setError(''); setLoading(true);
    try {
      if (step === 'request') {
        await authAPI.requestRecovery(identifier);
        toast.success('If the account exists, a verification code has been issued.');
        setStep('otp');
      } else if (step === 'otp') {
        const res = await authAPI.verifyRecovery(identifier, otp);
        setResetToken(res.data.reset_token);
        setStep('reset');
      } else {
        if (password !== confirmation) throw new Error('Passwords do not match');
        await authAPI.resetPassword(resetToken, password);
        toast.success('Password reset successful');
        navigate('/login');
      }
    } catch (err) { setError(err.message === 'Passwords do not match' ? err.message : (err.response?.data?.detail || 'Unable to complete recovery')); }
    finally { setLoading(false); }
  };

  return <div style={{ minHeight:'100vh', display:'flex', alignItems:'center', justifyContent:'center', background:'var(--bg-base)', padding:24 }}>
    <div style={{ width:'100%', maxWidth:380, background:'var(--bg-surface)', border:'1px solid var(--border)', borderRadius:'var(--radius-xl)', boxShadow:'var(--shadow-md)', padding:'32px 28px' }}>
      <div style={{ textAlign:'center', marginBottom:24 }}>
        <div style={{ width:40,height:40,background:'var(--text-primary)',color:'white',borderRadius:'var(--radius-lg)',display:'inline-flex',alignItems:'center',justifyContent:'center',marginBottom:12 }}><Shield size={20}/></div>
        <h1 style={{fontSize:'1.25rem',fontWeight:700,color:'var(--text-primary)'}}>Account Recovery</h1>
        <p style={{fontSize:'.8rem',color:'var(--text-secondary)',marginTop:4}}>Secure AI-CRMS password recovery</p>
      </div>
      <form onSubmit={submit}>
        {error && <div className="alert alert-error" style={{marginBottom:16}}><span>{error}</span></div>}
        {step === 'request' && <div className="form-group"><label className="form-label">Username or email</label><input className="form-control" value={identifier} onChange={e=>setIdentifier(e.target.value)} required autoComplete="username" placeholder="Enter your account identifier" /></div>}
        {step === 'otp' && <><div className="form-group"><label className="form-label">Verification code</label><input className="form-control" value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,'').slice(0,6))} required inputMode="numeric" autoComplete="one-time-code" placeholder="6-digit code" /></div><p style={{fontSize:'.72rem',color:'var(--text-muted)'}}>The code expires shortly and can only be used once.</p></>}
        {step === 'reset' && <><div className="form-group"><label className="form-label">New password</label><input className="form-control" type="password" value={password} onChange={e=>setPassword(e.target.value)} required minLength={8} autoComplete="new-password" /></div><div className="form-group"><label className="form-label">Confirm new password</label><input className="form-control" type="password" value={confirmation} onChange={e=>setConfirmation(e.target.value)} required minLength={8} autoComplete="new-password" /></div></>}
        <button className="btn btn-primary btn-lg" style={{width:'100%'}} disabled={loading}>{loading ? <><span className="spinner"/> Processing...</> : step==='request' ? 'Send Verification Code' : step==='otp' ? <><KeyRound size={15}/> Verify Code</> : 'Set New Password'}</button>
      </form>
      <div style={{textAlign:'center',marginTop:20,paddingTop:16,borderTop:'1px solid var(--border-subtle)',fontSize:'.8rem'}}><Link to="/login" style={{color:'var(--text-secondary)',display:'inline-flex',gap:6,alignItems:'center'}}><ArrowLeft size={13}/> Back to sign in</Link></div>
    </div>
  </div>;
}

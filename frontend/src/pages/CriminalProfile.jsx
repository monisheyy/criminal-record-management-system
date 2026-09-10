import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  FileText, Download, Brain, User, Activity, History,
  Shield, ChevronLeft, Clock, AlertTriangle, ExternalLink
} from 'lucide-react';
import toast from 'react-hot-toast';
import { criminalsAPI, aiAPI } from '../services/api';
import { RiskBadge, StatusBadge } from '../components/RiskBadge';
import { useAuth } from '../contexts/AuthContext';

const safeDate = (d) => {
  if (!d) return 'N/A';
  try { return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }); } catch { return 'N/A'; }
};

export default function CriminalProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isAdmin, isOfficer } = useAuth();

  const [profile, setProfile] = useState(null);
  const [history, setHistory] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [predicting, setPredicting] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const fetchAll = useCallback(() => {
    setLoading(true);
    Promise.all([
      criminalsAPI.get(id),
      criminalsAPI.history(id),
      aiAPI.list({ criminal_id: id }),
    ])
      .then(([profileRes, histRes, predRes]) => {
        setProfile(profileRes.data);
        setHistory(histRes.data || []);
        setPredictions(predRes.data || []);
      })
      .catch(() => toast.error('Failed to load criminal dossier profile.'))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handlePredict = async () => {
    setPredicting(true);
    try {
      const res = await aiAPI.predict({ criminal_id: Number(id) });
      setPredictions(prev => [res.data, ...prev]);
      const updated = await criminalsAPI.get(id);
      setProfile(updated.data);
      toast.success('AI risk assessment generated.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'AI risk assessment failed.');
    } finally {
      setPredicting(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const res = await criminalsAPI.report(id);
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `dossier_${profile.crn || id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Dossier PDF downloaded.');
    } catch {
      toast.error('Failed to download PDF dossier.');
    } finally {
      setDownloading(false);
    }
  };

  if (loading) return (
    <div className="empty-state" style={{ minHeight: '60vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      <div className="spinner" style={{ width: 28, height: 28, marginBottom: 12 }} />
      <div className="empty-state-title">Loading Intelligence Dossier...</div>
    </div>
  );

  if (!profile) return (
    <div className="empty-state">
      <User size={36} style={{ opacity: 0.3 }} />
      <div className="empty-state-title">Dossier Not Found</div>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>This record could not be located in database.</p>
      <button className="btn btn-secondary" style={{ marginTop: 16 }} onClick={() => navigate('/criminals')}>
        Back to Records Directory
      </button>
    </div>
  );

  const latestPred = predictions[0] ?? null;
  const initials = `${profile.first_name?.[0] || ''}${profile.last_name?.[0] || ''}`.toUpperCase() || 'CR';

  return (
    <div>
      {/* Dossier Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn btn-secondary btn-icon" onClick={() => navigate('/criminals')}>
            <ChevronLeft size={16} />
          </button>
          <div>
            <h1 className="page-title">
              {profile.first_name} {profile.last_name}
            </h1>
            <p className="page-subtitle">CRN: <span className="mono">{profile.crn}</span> · {profile.crime_type || 'Unclassified'}</p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          {(isAdmin || isOfficer) && (
            <button className="btn btn-primary" onClick={handlePredict} disabled={predicting}>
              <Brain size={14} /> {predicting ? 'Analyzing...' : 'Run Risk Assessment'}
            </button>
          )}
          <button className="btn btn-secondary" onClick={handleDownload} disabled={downloading}>
            <Download size={14} /> {downloading ? 'Generating PDF...' : 'Download Dossier'}
          </button>
        </div>
      </div>

      {/* Identity Banner */}
      <div className="dossier-card">
        <div className="dossier-header">
          <div className="dossier-avatar">{initials}</div>
          <div className="dossier-info">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div className="dossier-name">{profile.first_name} {profile.last_name}</div>
              <StatusBadge status={profile.is_wanted ? 'critical' : profile.is_incarcerated ? 'medium' : 'low'} />
            </div>
            <div className="dossier-aliases">
              Category: <strong style={{ color: 'var(--text-primary)' }}>{profile.crime_type || 'N/A'}</strong> · Registered: {safeDate(profile.created_at)}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 4 }}>
              Calculated Threat Index
            </div>
            <RiskBadge score={profile.risk_score || 0} level={profile.threat_level} showBar />
          </div>
        </div>

        {/* Detailed Attribute Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, paddingTop: 16, borderTop: '1px solid var(--border-subtle)' }}>
          <div>
            <div className="form-label">Date of Birth</div>
            <div className="td-primary">{safeDate(profile.date_of_birth)}</div>
          </div>
          <div>
            <div className="form-label">Gender</div>
            <div className="td-primary">{profile.gender || 'N/A'}</div>
          </div>
          <div>
            <div className="form-label">Nationality</div>
            <div className="td-primary">{profile.nationality || 'N/A'}</div>
          </div>
          <div>
            <div className="form-label">Occupation</div>
            <div className="td-primary">{profile.occupation || 'N/A'}</div>
          </div>
          <div>
            <div className="form-label">Prior Convictions</div>
            <div className="td-mono">{profile.prior_convictions ?? 0} Record(s)</div>
          </div>
          <div>
            <div className="form-label">Gang Affiliation</div>
            <div className="td-primary" style={{ color: profile.gang ? 'var(--status-red)' : 'var(--text-secondary)' }}>
              {profile.gang ? `${profile.gang.name} ${profile.gang_rank ? `(${profile.gang_rank})` : ''}` : 'None'}
            </div>
          </div>
        </div>
      </div>

      {/* Latest AI Assessment */}
      {latestPred ? (
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Brain size={16} style={{ color: 'var(--accent-blue)' }} /> Latest Predictive Intelligence Assessment
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/ai-predictions')}>
              View All Predictions <ExternalLink size={12} />
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
            <div className="stat-card">
              <span className="stat-label">Predicted Crime</span>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>
                {latestPred.predicted_crime_type}
              </div>
            </div>
            <div className="stat-card">
              <span className="stat-label">Model Confidence</span>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent-blue)', marginTop: 4 }}>
                {latestPred.crime_type_confidence?.toFixed(1)}%
              </div>
            </div>
            <div className="stat-card">
              <span className="stat-label">Gang Probability</span>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: 'var(--status-amber)', marginTop: 4 }}>
                {latestPred.gang_affiliation_probability?.toFixed(1)}%
              </div>
            </div>
            <div className="stat-card">
              <span className="stat-label">Risk Rating Score</span>
              <div style={{ marginTop: 4 }}>
                <RiskBadge score={latestPred.risk_score} level={latestPred.risk_level} showBar />
              </div>
            </div>
          </div>

          {latestPred.input_features && (
            <div>
              <div className="form-label" style={{ marginBottom: 6 }}>Evaluated Feature Signals</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {Object.entries(latestPred.input_features).map(([k, v]) => (
                  <span key={k} className="badge badge-gray" style={{ textTransform: 'none' }}>
                    {k.replace(/_/g, ' ')}: <strong style={{ color: 'var(--text-primary)', marginLeft: 4 }}>{typeof v === 'boolean' ? (v ? 'Yes' : 'No') : v}</strong>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        (isAdmin || isOfficer) && (
          <div className="card" style={{ textAlign: 'center', padding: '32px 20px' }}>
            <Brain size={32} style={{ color: 'var(--text-muted)', marginBottom: 8 }} />
            <div className="empty-state-title">No Risk Assessment Generated</div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 16 }}>
              Run the AI prediction model to evaluate threat probabilities and gang affiliation.
            </p>
            <button className="btn btn-primary" onClick={handlePredict} disabled={predicting}>
              <Brain size={14} /> {predicting ? 'Analyzing...' : 'Generate Risk Assessment'}
            </button>
          </div>
        )
      )}

      {/* History Timeline */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 16 }}>
          <History size={16} style={{ color: 'var(--accent-blue)' }} /> Criminal History Event Timeline
        </div>
        {history.length === 0 ? (
          <div className="empty-state" style={{ padding: '20px 0' }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No historical incidents registered for this record.</div>
          </div>
        ) : (
          <div style={{ position: 'relative', paddingLeft: 18 }}>
            {history.map((rec) => (
              <div key={rec.id} style={{ paddingBottom: 16, position: 'relative', borderLeft: '2px solid var(--border)', paddingLeft: 16 }}>
                <div style={{
                  position: 'absolute', left: -5, top: 4, width: 8, height: 8,
                  borderRadius: '50%', background: 'var(--accent-blue)'
                }} />
                <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                  {rec.event_type?.replace(/_/g, ' ')?.toUpperCase()}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 2 }}>
                  {rec.description}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', gap: 12, marginTop: 4, fontFamily: 'JetBrains Mono, monospace' }}>
                  <span><Clock size={11} /> {safeDate(rec.date)}</span>
                  {rec.location && <span>📍 {rec.location}</span>}
                  {rec.case_reference && <span>Case: {rec.case_reference}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

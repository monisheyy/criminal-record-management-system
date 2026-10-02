import { useState, useEffect, useCallback } from 'react';
import { aiAPI } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { RiskBadge, StatusBadge } from '../components/RiskBadge';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  Brain, ChevronRight, Clock, Shield, Activity, AlertTriangle,
  CheckCircle, XCircle, RefreshCw, User, X
} from 'lucide-react';

const statusIcon = (s) => ({
  pending: <Clock size={13} />,
  confirmed: <CheckCircle size={13} />,
  rejected: <XCircle size={13} />,
  overridden: <RefreshCw size={13} />,
}[s] || null);


function ExplanationPanel({ prediction }) {
  const [open, setOpen] = useState(false);
  const explanation = prediction?.input_features?.explanation;
  const features = explanation?.top_features || [];
  const similar = prediction?.similar_criminals || [];

  return (
    <div className="card" style={{ padding: 14, marginTop: 12 }}>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => setOpen(v => !v)}
        style={{ width: '100%', justifyContent: 'space-between', padding: 0 }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
          <Brain size={15} style={{ color: 'var(--accent-blue)' }} />
          Why did the model produce this result?
        </span>
        <ChevronRight size={15} style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
      </button>

      {open && (
        <div style={{ marginTop: 14 }}>
          {prediction?.input_features?.gang_prediction_warning && (
            <div role="alert" style={{ marginBottom: 14, padding: 12, borderRadius: 8, border: '1px solid var(--status-amber)', background: 'var(--bg-elevated)', fontSize: '0.78rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, marginBottom: 5 }}><AlertTriangle size={14} /> Gang prediction unavailable</div>
              <div style={{ color: 'var(--text-secondary)' }}>{prediction.input_features.gang_prediction_warning}</div>
            </div>
          )}
          {prediction?.input_features?.model_validity_warning && (
            <div role="alert" style={{ marginBottom: 14, padding: 12, borderRadius: 8, border: '1px solid var(--status-amber)', background: 'var(--bg-elevated)', fontSize: '0.78rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, marginBottom: 5 }}><AlertTriangle size={14} /> Model validation warning</div>
              <div style={{ color: 'var(--text-secondary)' }}>{prediction.input_features.model_validity_warning}</div>
            </div>
          )}
          {prediction?.input_features?.feature_input_quality && (
            <div role="status" style={{ marginBottom: 14, padding: 12, borderRadius: 8, border: '1px solid var(--status-amber)', background: 'var(--bg-elevated)', fontSize: '0.78rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, marginBottom: 5 }}>
                <AlertTriangle size={14} /> Input completeness: {prediction.input_features.feature_input_quality.coverage_percent}%
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>
                {prediction.input_features.feature_input_quality.warning || 'All model feature fields were supplied or derived; this does not establish evidence quality or model validity.'}
              </div>
              {prediction.input_features.feature_input_quality.defaulted_features?.length > 0 && (
                <div style={{ marginTop: 6, color: 'var(--text-muted)' }}>
                  Defaulted fields: {prediction.input_features.feature_input_quality.defaulted_features.map(name => name.replace(/_/g, ' ')).join(', ')}
                </div>
              )}
            </div>
          )}
          {features.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
                <thead><tr>
                  <th style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid var(--border)' }}>Feature</th>
                  <th style={{ textAlign: 'right', padding: '7px 6px', borderBottom: '1px solid var(--border)' }}>Value</th>
                  <th style={{ textAlign: 'right', padding: '7px 6px', borderBottom: '1px solid var(--border)' }}>Relative Importance</th>
                </tr></thead>
                <tbody>{features.map(item => (
                  <tr key={item.feature}>
                    <td style={{ padding: '7px 6px', color: 'var(--text-secondary)' }}>{item.feature.replace(/_/g, ' ')}</td>
                    <td className="mono" style={{ padding: '7px 6px', textAlign: 'right' }}>{item.value}</td>
                    <td className="mono" style={{ padding: '7px 6px', textAlign: 'right' }}>{(item.relative_importance * 100).toFixed(2)}%</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>No model explanation metadata is available for this prediction.</div>}

          <div style={{ marginTop: 12, fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            These are Random Forest model feature-importance values. They describe relative model importance and do not establish that a feature caused the prediction.
          </div>

          <div style={{ marginTop: 14 }}>
            <div className="form-label" style={{ marginBottom: 7 }}>Similar Records</div>
            {similar.length > 0 ? similar.map(item => (
              <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{item.name || `Record #${item.id}`}</span>
                <span className="mono">{Number(item.score).toFixed(1)}% · {item.crime_type || 'N/A'}</span>
              </div>
            )) : <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>No similar records available.</div>}
          </div>

          <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            <span>Model: <strong>{prediction.model_version}</strong></span>
            <span>Generated: <strong>{prediction.created_at ? new Date(prediction.created_at).toLocaleString() : 'N/A'}</strong></span>
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewModal({ prediction, onClose, onSubmitted }) {
  const { isAdmin, isOfficer } = useAuth();
  const canReview = isAdmin || isOfficer;

  const [decision, setDecision] = useState('confirmed');
  const [remarks, setRemarks] = useState('');
  const [overrideCrime, setOverrideCrime] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const p = prediction;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!remarks.trim()) {
      toast.error('Officer remarks are mandatory for review decisions.');
      return;
    }
    if (decision === 'overridden' && !overrideCrime.trim()) {
      toast.error('Override crime category is required.');
      return;
    }
    setSubmitting(true);
    try {
      await aiAPI.review(p.id, {
        status: decision,
        remarks: remarks.trim(),
        override_crime_type: decision === 'overridden' ? overrideCrime : undefined,
      });
      toast.success(`Prediction decision ${decision} recorded.`);
      onSubmitted();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit review decision.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card" style={{ maxWidth: '720px' }}>
        <div className="modal-header">
          <span className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Brain size={18} style={{ color: 'var(--accent-blue)' }} /> Analytical Decision Support Item #{p.id}
          </span>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="modal-body" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* Left Column - Model Prediction Details */}
          <div>
            <div className="card" style={{ padding: 14, marginBottom: 12 }}>
              <div className="form-label" style={{ marginBottom: 4 }}>Crime Classification Signal</div>
              <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {p.predicted_crime_type || 'Unclassified'}
              </div>
              <div className="mono" style={{ fontSize: '0.78rem', color: 'var(--accent-blue)', marginTop: 4 }}>
                Confidence: {p.crime_type_confidence?.toFixed(1)}%
              </div>
              {p.override_crime_type && (
                <div style={{ marginTop: 6, fontSize: '0.78rem', color: 'var(--status-purple)' }}>
                  Officer Override: <strong>{p.override_crime_type}</strong>
                </div>
              )}
            </div>

            <div className="card" style={{ padding: 14, marginBottom: 12 }}>
              <div className="form-label" style={{ marginBottom: 4 }}>Gang Affiliation Assessment</div>
              <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>
                {p.input_features?.gang_prediction_available === false
                  ? 'Prediction unavailable'
                  : p.predicted_gang_id ? `Gang Association #${p.predicted_gang_id}` : 'No Gang Affiliation Detected'}
              </div>
              <div className="mono" style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 4 }}>
                {p.input_features?.gang_prediction_available === false
                  ? 'No validated gang prediction is available for this model version.'
                  : `Model score: ${p.gang_affiliation_probability?.toFixed(1)}% (not a verified probability)`}
              </div>
            </div>

            <div className="card" style={{ padding: 14 }}>
              <div className="form-label" style={{ marginBottom: 4 }}>Prototype Decision-Support Score</div>
              <RiskBadge score={p.risk_score} level={p.risk_level} showBar />
              <div style={{ marginTop: 8, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                This unvalidated prototype score must not independently determine official status or action.
              </div>
              <div style={{ marginTop: 8, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Model Version: <span className="mono" style={{ color: 'var(--text-primary)' }}>{p.model_version}</span>
              </div>
            </div>
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <ExplanationPanel prediction={p} />
          </div>

          {/* Right Column - Review Decision Input */}
          <div>
            {canReview && p.review_status === 'pending' ? (
              <form onSubmit={handleSubmit}>
                <div className="card" style={{ padding: 14, margin: 0 }}>
                  <div className="form-label" style={{ marginBottom: 10 }}>Officer Decision Assessment</div>
                  
                  <div className="form-group">
                    <label className="form-label">Review Action *</label>
                    <select className="form-select" value={decision} onChange={e => setDecision(e.target.value)}>
                      <option value="confirmed">Confirm Model Prediction</option>
                      <option value="rejected">Reject Prediction</option>
                      <option value="overridden">Override Classification</option>
                    </select>
                  </div>

                  {decision === 'overridden' && (
                    <div className="form-group">
                      <label className="form-label">Override Crime Category *</label>
                      <select className="form-select" value={overrideCrime} onChange={e => setOverrideCrime(e.target.value)} required>
                        <option value="">Select Category...</option>
                        {['Robbery','Assault','Murder','Drug Trafficking','Burglary','Cybercrime',
                          'Fraud','Kidnapping','Arms Trafficking','Extortion','Human Trafficking',
                          'Car Theft','Vandalism','Arson','Money Laundering'].map(c => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  <div className="form-group">
                    <label className="form-label">Investigating Officer Remarks *</label>
                    <textarea
                      className="form-control"
                      rows={3}
                      value={remarks}
                      onChange={e => setRemarks(e.target.value)}
                      placeholder="Enter operational rationale..."
                      required
                    />
                  </div>

                  <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>Cancel</button>
                    <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
                      {submitting ? <><span className="spinner" /> Submitting...</> : 'Submit Decision'}
                    </button>
                  </div>
                </div>
              </form>
            ) : (
              <div className="card" style={{ padding: 14, margin: 0 }}>
                <div className="form-label" style={{ marginBottom: 6 }}>Review Record Status</div>
                <div style={{ marginBottom: 10 }}>
                  <StatusBadge status={p.review_status} />
                </div>
                {p.officer_remarks && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', background: 'var(--bg-elevated)', padding: 10, borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
                    "{p.officer_remarks}"
                  </div>
                )}
                {p.reviewed_at && (
                  <div className="mono" style={{ marginTop: 8, fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    Reviewed: {new Date(p.reviewed_at).toLocaleString()}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="modal-footer" style={{ justifyContent: 'space-between' }}>
          <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            Generated: {new Date(p.created_at).toLocaleString()}
          </span>
          <button className="btn btn-secondary btn-sm" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

export default function AIPredictions() {
  const navigate = useNavigate();
  const { isAdmin, isOfficer } = useAuth();

  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState({ review_status: '', risk_level: '' });

  const fetchPredictions = useCallback(() => {
    setLoading(true);
    const params = {};
    if (filter.review_status) params.review_status = filter.review_status;
    if (filter.risk_level) params.risk_level = filter.risk_level;
    aiAPI.list(params)
      .then(r => setPredictions(r.data || []))
      .catch(() => toast.error('Failed to load predictions.'))
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => { fetchPredictions(); }, [fetchPredictions]);

  const pendingCount = predictions.filter(p => p.review_status === 'pending').length;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">AI Predictive Decision Support</h1>
          <p className="page-subtitle">
            {pendingCount > 0
              ? `${pendingCount} risk prediction items awaiting officer verification`
              : 'All predictions reviewed'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <select className="form-select" style={{ width: 'auto', fontSize: '0.8rem' }}
                  value={filter.review_status}
                  onChange={e => setFilter(f => ({ ...f, review_status: e.target.value }))}>
            <option value="">All Review Statuses</option>
            <option value="pending">Pending</option>
            <option value="confirmed">Confirmed</option>
            <option value="rejected">Rejected</option>
            <option value="overridden">Overridden</option>
          </select>
          <select className="form-select" style={{ width: 'auto', fontSize: '0.8rem' }}
                  value={filter.risk_level}
                  onChange={e => setFilter(f => ({ ...f, risk_level: e.target.value }))}>
            <option value="">All Threat Levels</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>

      <div className="table-container">
        {loading ? (
          <div className="empty-state" style={{ padding: '40px' }}>
            <div className="spinner" style={{ marginBottom: 12 }} />
            <div className="empty-state-title">Loading predictive analysis model output...</div>
          </div>
        ) : predictions.length === 0 ? (
          <div className="empty-state">
            <Brain size={32} style={{ opacity: 0.3 }} />
            <div className="empty-state-title">No AI Predictions Found</div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Execute AI analysis from an Offender Dossier page.
            </p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Subject Dossier</th>
                <th>Predicted Offence</th>
                <th>Model Confidence</th>
                <th>Risk Rating</th>
                <th>Model Ver.</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {predictions.map(p => (
                <tr key={p.id}>
                  <td className="td-mono">#{p.id}</td>
                  <td>
                    {p.criminal_id ? (
                      <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/criminals/${p.criminal_id}`)}>
                        <User size={12} /> Offender #{p.criminal_id}
                      </button>
                    ) : (
                      <span className="mono" style={{ fontSize: '0.78rem' }}>Case #{p.case_id}</span>
                    )}
                  </td>
                  <td className="td-primary">{p.predicted_crime_type || 'Unclassified'}</td>
                  <td className="td-mono">{p.crime_type_confidence?.toFixed(1)}%</td>
                  <td>
                    <RiskBadge score={p.risk_score} level={p.risk_level} showBar />
                  </td>
                  <td className="td-mono" style={{ color: 'var(--text-muted)' }}>{p.model_version}</td>
                  <td>
                    <StatusBadge status={p.review_status} />
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button className="btn btn-secondary btn-sm" onClick={() => setSelected(p)}>
                      {p.review_status === 'pending' && (isAdmin || isOfficer) ? 'Review' : 'Inspect'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <ReviewModal
          prediction={selected}
          onClose={() => setSelected(null)}
          onSubmitted={fetchPredictions}
        />
      )}
    </div>
  );
}

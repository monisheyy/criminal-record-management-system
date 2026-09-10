import { useState, useEffect } from 'react';
import { Brain, RefreshCw, BarChart2, Zap, Target, Layers, Clock, TrendingUp } from 'lucide-react';
import toast from 'react-hot-toast';
import { aiAPI } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const pctDirect = (v) => (v != null ? `${v.toFixed(1)}%` : '—');

export default function AdminAIModels() {
  const { isAdmin } = useAuth();
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [retraining, setRetraining] = useState(false);

  const fetchModels = () => {
    setLoading(true);
    aiAPI.models()
      .then(r => setModels(r.data || []))
      .catch(() => toast.error('Failed to fetch AI model history.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchModels(); }, []);

  const handleRetrain = async () => {
    if (!isAdmin) return;
    setRetraining(true);
    const tid = toast.loading('Retraining predictive models... please wait.');
    try {
      const res = await aiAPI.retrain();
      toast.success(`Model retraining complete: ${res.data.version}`, { id: tid });
      fetchModels();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Retraining failed.', { id: tid });
    } finally {
      setRetraining(false);
    }
  };

  const latest = models[0] ?? null;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">AI Model Governance & Retraining</h1>
          <p className="page-subtitle">
            {latest ? `Active Version: ${latest.version} · Trained ${new Date(latest.trained_at).toLocaleDateString()}` : 'No models trained yet.'}
          </p>
        </div>
        {isAdmin && (
          <button className="btn btn-primary" onClick={handleRetrain} disabled={retraining}>
            <RefreshCw size={14} className={retraining ? 'spinner' : ''} />
            {retraining ? 'Retraining...' : 'Retrain Pipeline Models'}
          </button>
        )}
      </div>

      {/* Model Performance KPI Cards */}
      {latest && (
        <div className="stats-grid">
          <div className="stat-card">
            <span className="stat-label">Model Accuracy</span>
            <div className="stat-value" style={{ color: 'var(--status-emerald)' }}>{pctDirect(latest.accuracy * 100)}</div>
          </div>
          <div className="stat-card">
            <span className="stat-label">Precision Rating</span>
            <div className="stat-value" style={{ color: 'var(--accent-blue)' }}>{pctDirect(latest.precision_score * 100)}</div>
          </div>
          <div className="stat-card">
            <span className="stat-label">Sensitivity / Recall</span>
            <div className="stat-value" style={{ color: 'var(--status-purple)' }}>{pctDirect(latest.recall_score * 100)}</div>
          </div>
          <div className="stat-card">
            <span className="stat-label">Composite F1 Score</span>
            <div className="stat-value" style={{ color: 'var(--status-amber)' }}>{pctDirect(latest.f1_score * 100)}</div>
          </div>
          <div className="stat-card">
            <span className="stat-label">Training Set Size</span>
            <div className="stat-value">{(latest.training_samples ?? 0).toLocaleString()}</div>
          </div>
        </div>
      )}

      {/* Feature Weights Breakdown */}
      {latest?.feature_importances && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>
            <TrendingUp size={15} style={{ color: 'var(--accent-blue)' }} /> Evaluated Feature Signal Weights
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {Object.entries(latest.feature_importances)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 8)
              .map(([name, val]) => {
                const featureNames = {
                  feature_0: 'Prior Convictions',
                  feature_1: 'Age',
                  feature_2: 'Gang Membership',
                  feature_3: 'Weapons Involved',
                  feature_4: 'Drug Involvement',
                  feature_5: 'Financial Motivation',
                  feature_6: 'Tech Involvement',
                  feature_7: 'Violence History',
                  feature_8: 'Location Risk',
                  feature_9: 'Time of Crime',
                  feature_10: 'Associates Count',
                };
                const pctVal = (val * 100).toFixed(1);
                return (
                  <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div style={{ width: 140, fontSize: '0.8rem', color: 'var(--text-secondary)', flexShrink: 0 }}>
                      {featureNames[name] || name}
                    </div>
                    <div style={{ flex: 1, height: 6, borderRadius: 'var(--radius-full)', background: 'var(--bg-elevated)', overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', width: `${Math.min(100, pctVal * 4)}%`,
                        background: 'var(--accent-blue)', borderRadius: 'var(--radius-full)',
                        transition: 'width 0.4s ease',
                      }} />
                    </div>
                    <div className="mono" style={{ width: 48, fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'right', flexShrink: 0 }}>
                      {pctVal}%
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Model History Table */}
      <div className="table-container">
        <div className="table-toolbar">
          <span className="table-title">Model Release History</span>
        </div>
        {loading ? (
          <div className="empty-state" style={{ padding: '40px' }}>
            <div className="spinner" style={{ marginBottom: 12 }} />
            <div className="empty-state-title">Loading model versions...</div>
          </div>
        ) : models.length === 0 ? (
          <div className="empty-state">
            <Brain size={32} style={{ opacity: 0.3 }} />
            <div className="empty-state-title">No Models Trained</div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Version Tag</th>
                <th>Model Architecture</th>
                <th>Accuracy</th>
                <th>Precision</th>
                <th>Recall</th>
                <th>F1 Score</th>
                <th>Samples</th>
                <th>Trained At</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m, i) => (
                <tr key={m.id || i}>
                  <td className="td-mono">
                    {m.version} {i === 0 && <span className="badge badge-green" style={{ marginLeft: 6 }}>ACTIVE</span>}
                  </td>
                  <td>{m.model_type || 'RandomForest'}</td>
                  <td className="td-mono">{pctDirect(m.accuracy * 100)}</td>
                  <td className="td-mono">{pctDirect(m.precision_score * 100)}</td>
                  <td className="td-mono">{pctDirect(m.recall_score * 100)}</td>
                  <td className="td-mono">{pctDirect(m.f1_score * 100)}</td>
                  <td className="td-mono">{(m.training_samples ?? 0).toLocaleString()}</td>
                  <td className="td-mono" style={{ fontSize: '0.78rem' }}>{new Date(m.trained_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

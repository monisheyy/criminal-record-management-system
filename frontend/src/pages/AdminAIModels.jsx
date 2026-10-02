import { useState, useEffect } from 'react';
import { Brain, RefreshCw, TrendingUp, Grid3X3 } from 'lucide-react';
import toast from 'react-hot-toast';
import { aiAPI } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const pctDirect = (v) => (v != null ? `${v.toFixed(1)}%` : '—');

function ConfusionMatrix({ evaluation }) {
  const matrix = evaluation?.confusion_matrix;
  const classes = evaluation?.classes || [];
  if (!Array.isArray(matrix) || !classes.length) return null;

  const max = Math.max(1, ...matrix.flat());
  const cellSize = classes.length > 10 ? 34 : 44;

  return (
    <div className="card" style={{ overflowX: 'auto' }}>
      <div className="card-title" style={{ marginBottom: 6 }}>
        <Grid3X3 size={15} style={{ color: 'var(--accent-blue)' }} /> Confusion Matrix — Crime Classifier
      </div>
      <p className="page-subtitle" style={{ marginBottom: 14 }}>
        Rows = actual class · Columns = predicted class · Values are holdout test samples.
      </p>
      <div style={{ display: 'inline-block', minWidth: '100%' }}>
        <div style={{ marginLeft: 150, display: 'flex' }}>
          {classes.map((label) => (
            <div key={`h-${label}`} title={label} style={{ width: cellSize, writingMode: 'vertical-rl', transform: 'rotate(180deg)', fontSize: 10, color: 'var(--text-muted)', height: 115, textAlign: 'left', padding: 4 }}>
              {label}
            </div>
          ))}
        </div>
        {matrix.map((row, r) => (
          <div key={`r-${classes[r]}`} style={{ display: 'flex', alignItems: 'center' }}>
            <div title={classes[r]} style={{ width: 150, fontSize: 10, color: 'var(--text-secondary)', paddingRight: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {classes[r]}
            </div>
            {row.map((value, c) => (
              <div key={`${r}-${c}`} title={`${classes[r]} → ${classes[c]}: ${value}`} style={{ width: cellSize, height: cellSize, display: 'flex', alignItems: 'center', justifyContent: 'center', margin: 1, borderRadius: 3, background: `color-mix(in srgb, var(--accent-blue) ${Math.round((value / max) * 85)}%, var(--bg-elevated))`, color: value > max * 0.45 ? 'white' : 'var(--text-primary)', fontSize: 10, fontFamily: 'monospace' }}>
                {value}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function EvaluationPanel({ latest }) {
  const meta = latest?.evaluation_metadata;
  if (!meta) return null;
  const crime = meta.crime_classifier || {};
  const gang = meta.gang_predictor || {};
  const cv = crime.cross_validation;

  return (
    <>
      <div className="card">
        <div className="card-title" style={{ marginBottom: 10 }}>
          <Brain size={15} style={{ color: 'var(--accent-blue)' }} /> Rigorous Evaluation
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
          <span className="badge badge-blue">{latest.evaluation_method || 'Holdout evaluation'}</span>
          {meta.dataset_type === 'synthetic_demonstration' && <span className="badge badge-amber">SYNTHETIC / DEMONSTRATION DATA</span>}
          {latest.dataset_version && <span className="badge">Dataset {latest.dataset_version}</span>}
        </div>
        <div className="stats-grid">
          <div className="stat-card"><span className="stat-label">Crime Test Samples</span><div className="stat-value">{crime.test_samples ?? '—'}</div></div>
          <div className="stat-card"><span className="stat-label">Crime Accuracy</span><div className="stat-value">{pctDirect((crime.accuracy ?? 0) * 100)}</div></div>
          <div className="stat-card"><span className="stat-label">Crime Macro F1</span><div className="stat-value">{pctDirect((crime.macro_f1 ?? 0) * 100)}</div></div>
          <div className="stat-card"><span className="stat-label">Balanced Accuracy</span><div className="stat-value">{pctDirect((crime.balanced_accuracy ?? 0) * 100)}</div></div>
          <div className="stat-card"><span className="stat-label">Majority Baseline</span><div className="stat-value">{pctDirect((crime.majority_baseline_accuracy ?? 0) * 100)}</div></div>
          <div className="stat-card"><span className="stat-label">Gang Test Samples</span><div className="stat-value">{gang.test_samples ?? '—'}</div></div>
          <div className="stat-card"><span className="stat-label">Gang Accuracy</span><div className="stat-value">{pctDirect((gang.accuracy ?? 0) * 100)}</div></div>
          <div className="stat-card"><span className="stat-label">Gang Macro F1</span><div className="stat-value">{pctDirect((gang.macro_f1 ?? 0) * 100)}</div></div>
        </div>
        {Array.isArray(crime.zero_recall_classes) && crime.zero_recall_classes.length > 0 && (
          <div role="status" style={{ marginTop: 12, padding: 12, borderRadius: 8, border: '1px solid var(--status-amber)', fontSize: 12 }}>
            <strong><span style={{ color: 'var(--status-amber)' }}>Evaluation warning:</span></strong> zero recall for {crime.zero_recall_classes.length} crime class(es): {crime.zero_recall_classes.join(', ')}. A class with zero recall was not correctly identified in the holdout split.
          </div>
        )}
        {cv?.enabled && (
          <div style={{ marginTop: 14, padding: 12, borderRadius: 8, background: 'var(--bg-elevated)', color: 'var(--text-secondary)', fontSize: 12 }}>
            <strong>Cross-validation:</strong> {cv.folds}-fold stratified · Accuracy {pctDirect(cv.accuracy_mean * 100)} ± {pctDirect(cv.accuracy_std * 100)} · F1 {pctDirect(cv.f1_mean * 100)}
          </div>
        )}
        <div style={{ marginTop: 14, fontSize: 12, color: 'var(--text-muted)' }}>
          Metrics are calculated from the current trained model and stored with its evaluation metadata. Synthetic demonstration data does not establish real-world predictive validity.
        </div>
      </div>
      <ConfusionMatrix evaluation={crime} />
    </>
  );
}

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

      {latest && (
        <div className="stats-grid">
          <div className="stat-card"><span className="stat-label">Model Accuracy</span><div className="stat-value" style={{ color: 'var(--status-emerald)' }}>{pctDirect(latest.accuracy * 100)}</div></div>
          <div className="stat-card"><span className="stat-label">Precision Rating</span><div className="stat-value" style={{ color: 'var(--accent-blue)' }}>{pctDirect(latest.precision_score * 100)}</div></div>
          <div className="stat-card"><span className="stat-label">Sensitivity / Recall</span><div className="stat-value" style={{ color: 'var(--status-purple)' }}>{pctDirect(latest.recall_score * 100)}</div></div>
          <div className="stat-card"><span className="stat-label">Composite F1 Score</span><div className="stat-value" style={{ color: 'var(--status-amber)' }}>{pctDirect(latest.f1_score * 100)}</div></div>
          <div className="stat-card"><span className="stat-label">Training Set Size</span><div className="stat-value">{(latest.training_samples ?? 0).toLocaleString()}</div></div>
        </div>
      )}

      <EvaluationPanel latest={latest} />

      {latest?.feature_importances && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}><TrendingUp size={15} style={{ color: 'var(--accent-blue)' }} /> Evaluated Feature Signal Weights</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {Object.entries(latest.feature_importances).sort(([, a], [, b]) => b - a).slice(0, 8).map(([name, val]) => {
              const featureNames = { feature_0: 'Prior Convictions', feature_1: 'Age', feature_2: 'Gang Membership', feature_3: 'Weapons Involved', feature_4: 'Drug Involvement', feature_5: 'Financial Motivation', feature_6: 'Tech Involvement', feature_7: 'Violence History', feature_8: 'Location Risk', feature_9: 'Time of Crime', feature_10: 'Associates Count' };
              const pctVal = (val * 100).toFixed(1);
              return <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 12 }}><div style={{ width: 140, fontSize: '0.8rem', color: 'var(--text-secondary)', flexShrink: 0 }}>{featureNames[name] || name}</div><div style={{ flex: 1, height: 6, borderRadius: 'var(--radius-full)', background: 'var(--bg-elevated)', overflow: 'hidden' }}><div style={{ height: '100%', width: `${Math.min(100, pctVal * 4)}%`, background: 'var(--accent-blue)', borderRadius: 'var(--radius-full)' }} /></div><div className="mono" style={{ width: 48, fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'right', flexShrink: 0 }}>{pctVal}%</div></div>;
            })}
          </div>
        </div>
      )}

      <div className="table-container">
        <div className="table-toolbar"><span className="table-title">Model Release History</span></div>
        {loading ? <div className="empty-state" style={{ padding: '40px' }}><div className="spinner" style={{ marginBottom: 12 }} /><div className="empty-state-title">Loading model versions...</div></div> : models.length === 0 ? <div className="empty-state"><Brain size={32} style={{ opacity: 0.3 }} /><div className="empty-state-title">No Models Trained</div></div> : (
          <table><thead><tr><th>Version Tag</th><th>Model Architecture</th><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1 Score</th><th>Samples</th><th>Evaluation</th><th>Trained At</th></tr></thead>
            <tbody>{models.map((m, i) => <tr key={m.id || i}><td className="td-mono">{m.version} {i === 0 && <span className="badge badge-green" style={{ marginLeft: 6 }}>ACTIVE</span>}</td><td>{m.model_type || 'RandomForest'}</td><td className="td-mono">{pctDirect(m.accuracy * 100)}</td><td className="td-mono">{pctDirect(m.precision_score * 100)}</td><td className="td-mono">{pctDirect(m.recall_score * 100)}</td><td className="td-mono">{pctDirect(m.f1_score * 100)}</td><td className="td-mono">{(m.training_samples ?? 0).toLocaleString()}</td><td style={{ fontSize: 11 }}>{m.evaluation_method || '—'}</td><td className="td-mono" style={{ fontSize: '0.78rem' }}>{new Date(m.trained_at).toLocaleString()}</td></tr>)}</tbody>
          </table>
        )}
      </div>
    </div>
  );
}

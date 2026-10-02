import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Brain, CheckCircle2, RefreshCw, RotateCcw, ShieldCheck, XCircle } from 'lucide-react';
import { aiAPI, getErrorMessage } from '../services/api';
import { AIAdvisoryBanner, EmptyState, ErrorState, FieldHint, LoadingState, Modal } from '../components/ui';
import { formatDate, formatScore } from '../utils/format';
import { humanize } from '../utils/errors';

const STATUS_BADGE = { active: 'badge-green', awaiting_review: 'badge-amber', retired: 'badge-gray' };

function GateChecklist({ gate }) {
  if (!gate?.checks) return <p className="td-sub">No quality-gate evaluation stored for this model.</p>;
  return (
    <div>
      <div className={`alert ${gate.passed ? 'alert-info' : 'alert-error'}`} role="status">
        {gate.passed ? <CheckCircle2 size={15} aria-hidden="true" /> : <XCircle size={15} aria-hidden="true" />}
        <strong>Release quality gate {gate.passed ? 'passed' : 'FAILED'}</strong>
        <span className="td-sub" style={{ marginLeft: 6 }}>Passing is necessary, not sufficient, for real-world use.</span>
      </div>
      <div className="table-scroll">
        <table className="compact-table">
          <caption className="sr-only">Quality gate checks</caption>
          <thead><tr><th scope="col">Check</th><th scope="col" className="num">Observed</th><th scope="col" className="num">Required</th><th scope="col">Result</th></tr></thead>
          <tbody>{gate.checks.map((c) => (
            <tr key={c.check}>
              <td>{humanize(c.check)}</td>
              <td className="num mono">{typeof c.observed === 'number' ? Number(c.observed).toFixed(3) : String(c.observed)}</td>
              <td className="num mono">{c.operator} {String(c.threshold)}</td>
              <td>{c.passed ? <span className="badge badge-green">Pass</span> : <span className="badge badge-red">Fail</span>}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function ConfusionMatrix({ evaluation }) {
  const matrix = evaluation?.confusion_matrix;
  const classes = evaluation?.classes || [];
  if (!Array.isArray(matrix) || !classes.length) return null;
  const max = Math.max(1, ...matrix.flat());
  return (
    <div className="table-scroll">
      <table className="confusion-matrix">
        <caption>Confusion matrix (holdout). Rows: actual class; columns: predicted class.</caption>
        <thead><tr><th scope="col"><span className="sr-only">Actual \ Predicted</span></th>
          {classes.map((c) => <th key={c} scope="col" className="cm-head"><span>{c}</span></th>)}</tr></thead>
        <tbody>{matrix.map((row, r) => (
          <tr key={classes[r]}>
            <th scope="row">{classes[r]}</th>
            {row.map((value, c) => (
              <td key={c} title={`${classes[r]} → ${classes[c]}: ${value}`}
                style={{ background: `color-mix(in srgb, var(--accent-blue) ${Math.round((value / max) * 80)}%, white)`, color: value > max * 0.45 ? 'white' : 'var(--text-primary)' }}>
                {value}
              </td>
            ))}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function SubgroupTable({ report }) {
  if (!report?.slices) return null;
  return (
    <div>
      <p className="td-sub">{report.limitations} Largest accuracy gap vs. overall: <strong>{formatScore(report.max_abs_accuracy_gap)}</strong>.</p>
      <div className="table-scroll">
        <table className="compact-table">
          <caption className="sr-only">Accuracy by evaluation slice</caption>
          <thead><tr><th scope="col">Slice</th><th scope="col">Group</th><th scope="col" className="num">n</th><th scope="col" className="num">Accuracy</th><th scope="col" className="num">Macro F1</th><th scope="col" className="num">Gap</th></tr></thead>
          <tbody>{Object.entries(report.slices).flatMap(([name, groups]) => groups.map((g) => (
            <tr key={`${name}-${g.group}`}>
              <td>{humanize(name)}</td><td>{g.group}</td><td className="num mono">{g.n}</td>
              <td className="num mono">{g.accuracy != null ? formatScore(g.accuracy) : '—'}</td>
              <td className="num mono">{g.macro_f1 != null ? formatScore(g.macro_f1) : '—'}</td>
              <td className="num mono">{g.accuracy_gap_vs_overall != null ? `${(g.accuracy_gap_vs_overall * 100).toFixed(1)} pp` : <span title={g.note}>n/a</span>}</td>
            </tr>
          )))}</tbody>
        </table>
      </div>
    </div>
  );
}

function ModelDetail({ model }) {
  const meta = model.evaluation_metadata || {};
  const crime = meta.crime_classifier || {};
  const calibration = crime.calibration;
  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title"><Brain size={15} aria-hidden="true" style={{ color: 'var(--accent-blue)' }} /> {model.version}</h2>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {meta.dataset_type && <span className={`badge ${meta.dataset_type === 'synthetic_demonstration' ? 'badge-amber' : 'badge-blue'}`}>{humanize(meta.dataset_type)}</span>}
          <span className="badge">Dataset {model.dataset_version || '?'}</span>
        </div>
      </div>
      <div className="stats-grid">
        <div className="stat-card"><span className="stat-label">Macro F1</span><div className="stat-value-sm">{formatScore(crime.macro_f1)}</div></div>
        <div className="stat-card"><span className="stat-label">Balanced accuracy</span><div className="stat-value-sm">{formatScore(crime.balanced_accuracy)}</div></div>
        <div className="stat-card"><span className="stat-label">Accuracy</span><div className="stat-value-sm">{formatScore(crime.accuracy ?? model.accuracy)}</div></div>
        <div className="stat-card"><span className="stat-label">Majority baseline</span><div className="stat-value-sm">{formatScore(crime.majority_baseline_accuracy)}</div></div>
        <div className="stat-card"><span className="stat-label">Calibration error (ECE)</span><div className="stat-value-sm">{calibration ? calibration.expected_calibration_error.toFixed(3) : '—'}</div></div>
        <div className="stat-card"><span className="stat-label">Holdout samples</span><div className="stat-value-sm">{crime.test_samples ?? '—'}</div></div>
      </div>
      {Array.isArray(crime.zero_recall_classes) && crime.zero_recall_classes.length > 0 && (
        <div className="alert alert-warning" role="note">Zero recall (never correctly identified) for: {crime.zero_recall_classes.join(', ')}.</div>
      )}
      <h3 className="form-label" style={{ marginTop: 12 }}>Quality gate</h3>
      <GateChecklist gate={meta.quality_gate} />
      {crime.subgroup_evaluation && (<><h3 className="form-label" style={{ marginTop: 16 }}>Evaluation by slice</h3><SubgroupTable report={crime.subgroup_evaluation} /></>)}
      {calibration?.reliability_table?.length > 0 && (
        <>
          <h3 className="form-label" style={{ marginTop: 16 }}>Reliability (confidence vs. observed accuracy)</h3>
          <div className="table-scroll"><table className="compact-table">
            <thead><tr><th scope="col">Confidence bin</th><th scope="col" className="num">n</th><th scope="col" className="num">Mean confidence</th><th scope="col" className="num">Observed accuracy</th></tr></thead>
            <tbody>{calibration.reliability_table.map((b) => (
              <tr key={b.bin.join('-')}><td className="mono">{b.bin[0]}–{b.bin[1]}</td><td className="num mono">{b.count}</td><td className="num mono">{formatScore(b.mean_confidence)}</td><td className="num mono">{formatScore(b.accuracy)}</td></tr>
            ))}</tbody>
          </table></div>
        </>
      )}
      <h3 className="form-label" style={{ marginTop: 16 }}>Confusion matrix</h3>
      <ConfusionMatrix evaluation={crime} />
      {meta.activation_justification && <p className="td-sub" style={{ marginTop: 10 }}>Activation justification: “{meta.activation_justification}”</p>}
    </div>
  );
}

function JustifyModal({ title, action, model, onClose, onDone }) {
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await action(model.id, text.trim());
      toast.success(`${model.version} is now the active model.`);
      onDone();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title={title} onClose={onClose} busy={saving}>
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <p className="td-sub">Activation is blocked for synthetic-data models and for candidates that failed the quality gate. Every activation is audited.</p>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" htmlFor="justify">Documented justification *</label>
            <textarea id="justify" className="form-control" rows={4} minLength={20} maxLength={2000} required value={text} onChange={(e) => setText(e.target.value)}
              placeholder="Evaluation reviewed, approvals obtained, data provenance, known limitations…" />
            <FieldHint>At least 20 characters.</FieldHint>
          </div>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving || text.trim().length < 20}>{saving ? 'Working…' : 'Confirm'}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function AdminAIModels() {
  const [models, setModels] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retraining, setRetraining] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [dialog, setDialog] = useState(null);

  const fetchModels = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([aiAPI.models(), aiAPI.status().catch(() => ({ data: null }))])
      .then(([modelsRes, statusRes]) => { setModels(modelsRes.data || []); setStatus(statusRes.data); })
      .catch((err) => setError(getErrorMessage(err, 'Failed to load the model registry.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchModels(); }, [fetchModels]);

  const handleRetrain = async () => {
    setRetraining(true);
    const tid = toast.loading('Training a candidate model… this can take a minute.');
    try {
      const res = await aiAPI.retrain();
      const passed = res.data.quality_gate?.passed;
      toast.success(`Candidate ${res.data.version} saved for review (gate ${passed ? 'passed' : 'failed'}). The active model is unchanged.`, { id: tid, duration: 6000 });
      setSelectedId(res.data.model_id);
      fetchModels();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Training failed.'), { id: tid });
    } finally {
      setRetraining(false);
    }
  };

  const active = models.find((m) => m.is_active);
  const selected = models.find((m) => m.id === selectedId) || active || models[0];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">AI Model Governance</h1>
          <p className="page-subtitle">
            Active: <strong className="mono">{status?.model_version || active?.version || 'none'}</strong>
            {status?.artifact_integrity && <> · artifacts <strong>{humanize(status.artifact_integrity)}</strong></>}
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={handleRetrain} disabled={retraining}>
          <RefreshCw size={14} aria-hidden="true" className={retraining ? 'spin' : ''} /> {retraining ? 'Training…' : 'Train candidate'}
        </button>
      </div>

      <AIAdvisoryBanner status={status} />

      {loading ? <LoadingState label="Loading model registry…" />
        : error ? <ErrorState message={error} onRetry={fetchModels} />
        : models.length === 0 ? <EmptyState icon={Brain} title="No models registered" /> : (
          <>
            <div className="table-container">
              <div className="table-toolbar"><h2 className="table-title">Model registry</h2></div>
              <div className="table-scroll">
                <table>
                  <caption className="sr-only">Model versions</caption>
                  <thead><tr><th scope="col">Version</th><th scope="col">Lifecycle</th><th scope="col">Training data</th><th scope="col" className="num">Macro F1</th><th scope="col">Gate</th><th scope="col">Trained</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                  <tbody>{models.map((m) => {
                    const meta = m.evaluation_metadata || {};
                    const lifecycle = m.is_active ? 'active' : (meta.candidate_status || 'retired');
                    const gate = meta.quality_gate;
                    return (
                      <tr key={m.id} aria-current={selected?.id === m.id ? 'true' : undefined} className={selected?.id === m.id ? 'row-selected' : ''}>
                        <td className="td-mono">{m.version}</td>
                        <td><span className={`badge ${STATUS_BADGE[lifecycle] || 'badge-gray'}`}>{humanize(lifecycle)}</span></td>
                        <td>{humanize(meta.dataset_type || 'unknown')}</td>
                        <td className="num mono">{formatScore(meta.crime_classifier?.macro_f1)}</td>
                        <td>{gate ? (gate.passed ? <span className="badge badge-green">Passed</span> : <span className="badge badge-red">Failed</span>) : '—'}</td>
                        <td className="td-date">{formatDate(m.trained_at, { withTime: true })}</td>
                        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelectedId(m.id)}>Details</button>
                          {lifecycle === 'awaiting_review' && (
                            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDialog({ type: 'activate', model: m })}>
                              <ShieldCheck size={13} aria-hidden="true" /> Activate
                            </button>
                          )}
                          {lifecycle === 'retired' && meta.candidate_path && (
                            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDialog({ type: 'rollback', model: m })}>
                              <RotateCcw size={13} aria-hidden="true" /> Roll back
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              </div>
            </div>
            {selected && <ModelDetail model={selected} />}
          </>
        )}

      {dialog && (
        <JustifyModal title={dialog.type === 'activate' ? `Activate ${dialog.model.version}` : `Roll back to ${dialog.model.version}`}
          action={dialog.type === 'activate' ? aiAPI.activate : aiAPI.rollback} model={dialog.model}
          onClose={() => setDialog(null)} onDone={() => { setDialog(null); fetchModels(); }} />
      )}
    </div>
  );
}

import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Brain, ChevronRight } from 'lucide-react';
import { formatDate, formatScore } from '../utils/format';
import { humanize } from '../utils/errors';

function Warning({ title, children }) {
  return (
    <div className="alert alert-warning" role="note" style={{ alignItems: 'flex-start', marginBottom: 10 }}>
      <AlertTriangle size={14} aria-hidden="true" style={{ marginTop: 2, flexShrink: 0 }} />
      <div><strong>{title}</strong><div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>{children}</div></div>
    </div>
  );
}

/**
 * Explains *how* an AI output was produced and *how far it can be trusted*:
 * validity, calibration and data-completeness warnings come first, then the
 * global feature importances (explicitly not causal), the transparent risk
 * factor breakdown, provenance and similar records.
 */
export default function ExplanationPanel({ prediction, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const regionId = useId();
  const inputs = prediction?.input_features || {};
  const explanation = inputs.explanation || {};
  const features = explanation.top_features || [];
  const factors = inputs.risk_factors || [];
  const method = inputs.risk_score_method || {};
  const learned = method.type === 'learned_logistic_regression';
  const quality = inputs.feature_input_quality;
  const provenance = inputs.provenance;
  const similar = Array.isArray(prediction?.similar_criminals) ? prediction.similar_criminals : [];

  return (
    <div className="explanation-panel">
      <button type="button" className="btn btn-ghost btn-sm explanation-toggle" onClick={() => setOpen((v) => !v)}
        aria-expanded={open} aria-controls={regionId}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
          <Brain size={15} aria-hidden="true" style={{ color: 'var(--accent-blue)' }} /> How was this produced, and how reliable is it?
        </span>
        <ChevronRight size={15} aria-hidden="true" style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
      </button>

      {open && (
        <div id={regionId} style={{ marginTop: 14 }}>
          {inputs.model_validity_warning && <Warning title="Model not validated for real-world use">{inputs.model_validity_warning}</Warning>}
          {inputs.calibration_warning && <Warning title="Scores are not probabilities">{inputs.calibration_warning}</Warning>}
          {inputs.gang_prediction_warning && <Warning title="Gang prediction unavailable">{inputs.gang_prediction_warning}</Warning>}
          {quality && quality.missing_count > 0 && (
            <Warning title={`Incomplete inputs: ${quality.coverage_percent}% of model features observed or derived`}>
              Defaulted (not observed) fields: {(quality.defaulted_features || []).map(humanize).join(', ')}. Predictions built on
              defaulted values are especially unreliable.
            </Warning>
          )}

          <h3 className="form-label" style={{ margin: '14px 0 6px' }}>Model features with the highest global importance</h3>
          {features.length > 0 ? (
            <div className="table-scroll">
              <table className="compact-table">
                <caption className="sr-only">Top model features</caption>
                <thead><tr><th scope="col">Feature</th><th scope="col" className="num">Value used</th><th scope="col" className="num">Relative importance</th></tr></thead>
                <tbody>{features.map((item) => (
                  <tr key={item.feature}>
                    <td>{humanize(item.feature)}{(quality?.defaulted_features || []).includes(item.feature) && <span className="badge badge-amber" style={{ marginLeft: 6 }}>defaulted</span>}</td>
                    <td className="num mono">{item.value}</td>
                    <td className="num mono">{(item.relative_importance * 100).toFixed(1)}%</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : <p className="td-sub">No explanation metadata is stored for this output.</p>}
          <p className="td-sub" style={{ marginTop: 6 }}>
            These are global Random Forest importances: how much the model relies on each feature overall. They do not show
            that a feature caused this result, and they say nothing about an individual's guilt.
          </p>

          {factors.length > 0 && (learned ? (
            <>
              <h3 className="form-label" style={{ margin: '14px 0 6px' }}>Danger score breakdown (learned model)</h3>
              <div className="table-scroll">
                <table className="compact-table">
                  <thead><tr><th scope="col">Factor</th><th scope="col" className="num">Value used</th><th scope="col" className="num">Model weight</th><th scope="col" className="num">Effect on odds</th></tr></thead>
                  <tbody>{factors.map((f) => (
                    <tr key={f.key}>
                      <td>{f.name}{f.imputed && <span className="badge badge-amber" style={{ marginLeft: 6 }}>not recorded</span>}</td>
                      <td className="num mono">{f.normalized_value}</td><td className="num mono">{f.weight}</td>
                      <td className="num mono">{f.contribution > 0 ? '+' : ''}{f.contribution}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              <p className="td-sub" style={{ marginTop: 6 }}>
                Score = chance of re-arrest within two years in the training data{method.holdout_roc_auc ? ` (holdout AUC ${method.holdout_roc_auc})` : ''}.
                Positive effects raised it, negative lowered it. {method.disclaimer}
              </p>
            </>
          ) : (
            <>
              <h3 className="form-label" style={{ margin: '14px 0 6px' }}>Prototype risk score breakdown (fixed weights)</h3>
              <div className="table-scroll">
                <table className="compact-table">
                  <thead><tr><th scope="col">Factor</th><th scope="col" className="num">Normalised value</th><th scope="col" className="num">Weight</th><th scope="col" className="num">Points</th></tr></thead>
                  <tbody>{factors.map((f) => (
                    <tr key={f.key}><td>{f.name}</td><td className="num mono">{f.normalized_value}</td><td className="num mono">{f.weight}</td><td className="num mono">{f.contribution}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </>
          ))}

          <h3 className="form-label" style={{ margin: '14px 0 6px' }}>Similar records (retrieval context, not evidence)</h3>
          {similar.length > 0 ? (
            <ul className="similar-list">
              {similar.map((item) => (
                <li key={item.id ?? item.similar_record_id}>
                  <Link to={`/criminals/${item.id ?? item.similar_record_id}`}>{item.name || `Record #${item.id}`}</Link>
                  <span className="mono td-sub"> {formatScore(item.score ?? item.similarity_score)} similar · {item.crime_type || 'N/A'}</span>
                </li>
              ))}
            </ul>
          ) : <p className="td-sub">None.</p>}

          <div className="provenance">
            <span>Model <strong className="mono">{prediction.model_version}</strong></span>
            <span>Generated {formatDate(prediction.created_at, { withTime: true })}</span>
            {provenance?.model_dataset_type && <span>Training data: <strong>{humanize(provenance.model_dataset_type)}</strong></span>}
            {provenance?.record_last_updated && <span>Record as of {formatDate(provenance.record_last_updated, { withTime: true })}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

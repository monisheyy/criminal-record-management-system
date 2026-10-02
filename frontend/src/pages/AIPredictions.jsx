import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Brain } from 'lucide-react';
import { aiAPI, getErrorMessage } from '../services/api';
import { RiskBadge, StatusBadge } from '../components/RiskBadge';
import ExplanationPanel from '../components/ExplanationPanel';
import { AIAdvisoryBanner, EmptyState, ErrorState, FieldHint, LoadingState, Modal, Pagination } from '../components/ui';
import { CRIME_TYPES, THREAT_LEVELS } from '../utils/constants';
import { formatDate, formatScore } from '../utils/format';
import { humanize } from '../utils/errors';
import { usePagedList } from '../utils/usePagedList';

const DECISIONS = [
  { value: 'confirmed', label: 'Confirm — consistent with the verified record' },
  { value: 'rejected', label: 'Reject — not supported by the record' },
  { value: 'overridden', label: 'Override — record supports a different category' },
];
const MIN_REMARKS = 10;

function subjectLabel(p) {
  if (p.criminal) return `${p.criminal.first_name} ${p.criminal.last_name}`;
  if (p.criminal_id) return `Record #${p.criminal_id}`;
  return `Case #${p.case_id}`;
}

function ReviewModal({ prediction, status, onClose, onSubmitted }) {
  const isCorrection = prediction.review_status !== 'pending';
  const [decision, setDecision] = useState('confirmed');
  const [remarks, setRemarks] = useState('');
  const [override, setOverride] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [correcting, setCorrecting] = useState(!isCorrection);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (remarks.trim().length < MIN_REMARKS) { setError(`Explain your decision in at least ${MIN_REMARKS} characters.`); return; }
    if (decision === 'overridden' && !override) { setError('Choose the category the record supports.'); return; }
    setSubmitting(true);
    try {
      const res = await aiAPI.review(prediction.id, {
        status: decision,
        remarks: remarks.trim(),
        override_crime_type: decision === 'overridden' ? override : undefined,
      });
      toast.success(isCorrection ? 'Correction recorded in the review history.' : 'Review decision recorded.');
      onSubmitted(res.data);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not record the decision.'));
    } finally {
      setSubmitting(false);
    }
  };

  const p = prediction;
  return (
    <Modal title={`AI output #${p.id} — ${subjectLabel(p)}`} onClose={onClose} busy={submitting} maxWidth={820}>
      <div className="modal-body">
        <AIAdvisoryBanner status={status} compact />
        <div className="stats-grid" style={{ marginTop: 12 }}>
          <div className="stat-card"><span className="stat-label">Suggested category</span><div className="stat-value-sm">{p.predicted_crime_type || '—'}</div>
            <div className="td-sub">Model score {formatScore(p.crime_type_confidence)} (uncalibrated)</div></div>
          <div className="stat-card"><span className="stat-label">Gang association</span><div className="stat-value-sm">
            {p.input_features?.gang_prediction_available === false ? 'Unavailable' : formatScore(p.gang_affiliation_probability)}</div></div>
          <div className="stat-card"><span className="stat-label">Prototype risk score</span><div style={{ marginTop: 4 }}><RiskBadge score={p.risk_score} level={p.risk_level} showBar /></div></div>
          <div className="stat-card"><span className="stat-label">Current decision</span><div style={{ marginTop: 4 }}><StatusBadge status={p.review_status} /></div>
            {p.override_crime_type && <div className="td-sub">Override: {p.override_crime_type}</div>}</div>
        </div>
        <ExplanationPanel prediction={p} />

        {p.reviews?.length > 0 && (
          <section style={{ marginTop: 16 }} aria-labelledby={`hist-${p.id}`}>
            <h3 className="form-label" id={`hist-${p.id}`}>Review history (append-only)</h3>
            <ol className="timeline">
              {p.reviews.map((r) => (
                <li key={r.id}>
                  <div className="timeline-title">{humanize(r.previous_status)} → {humanize(r.decision)}{r.override_crime_type ? ` (${r.override_crime_type})` : ''}</div>
                  <div className="timeline-body">“{r.remarks}”</div>
                  <div className="timeline-meta"><span>{r.reviewer_username || 'unknown reviewer'}</span><span>{formatDate(r.created_at, { withTime: true })}</span></div>
                </li>
              ))}
            </ol>
          </section>
        )}

        {!correcting ? (
          <button type="button" className="btn btn-secondary" style={{ marginTop: 12 }} onClick={() => setCorrecting(true)}>
            Record a correction
          </button>
        ) : (
          <form onSubmit={submit} style={{ marginTop: 16 }} aria-labelledby={`decide-${p.id}`}>
            <h3 className="form-label" id={`decide-${p.id}`}>{isCorrection ? 'Correct the earlier decision' : 'Your decision'}</h3>
            {error && <div className="alert alert-error" role="alert">{error}</div>}
            <fieldset className="radio-group">
              <legend className="sr-only">Decision</legend>
              {DECISIONS.map((d) => (
                <label key={d.value}>
                  <input type="radio" name="decision" value={d.value} checked={decision === d.value} onChange={() => setDecision(d.value)} /> {d.label}
                </label>
              ))}
            </fieldset>
            {decision === 'overridden' && (
              <div className="form-group">
                <label className="form-label" htmlFor="override-type">Category supported by the record *</label>
                <select id="override-type" className="form-select" value={override} onChange={(e) => setOverride(e.target.value)} required>
                  <option value="">Select…</option>
                  {CRIME_TYPES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            )}
            <div className="form-group">
              <label className="form-label" htmlFor="review-remarks">Reasoning *</label>
              <textarea id="review-remarks" className="form-control" rows={3} maxLength={2000} value={remarks}
                onChange={(e) => setRemarks(e.target.value)} aria-required="true"
                placeholder="Which records or evidence did you check, and why do they support this decision?" />
              <FieldHint>Stored permanently with your name in the review history and audit log. {remarks.trim().length}/{MIN_REMARKS} minimum characters.</FieldHint>
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? <><span className="spinner" aria-hidden="true" /> Saving…</> : isCorrection ? 'Record correction' : 'Record decision'}
              </button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}

export default function AIPredictions() {
  const [filters, setFilters] = useState({ review_status: 'pending', risk_level: '' });
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState(null);
  const list = usePagedList(aiAPI.list, filters, 20);

  useEffect(() => { aiAPI.status().then((res) => setStatus(res.data)).catch(() => setStatus(null)); }, []);

  const setFilter = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">AI Decision-Support Review</h1>
          <p className="page-subtitle">{list.total} output{list.total === 1 ? '' : 's'} in this view{filters.review_status === 'pending' ? ' awaiting human review' : ''}</p>
        </div>
        <div className="toolbar-filters">
          <label className="sr-only" htmlFor="ai-status">Review status</label>
          <select id="ai-status" className="form-select" value={filters.review_status} onChange={setFilter('review_status')}>
            <option value="">All review statuses</option>
            <option value="pending">Pending review</option>
            <option value="confirmed">Confirmed</option>
            <option value="rejected">Rejected</option>
            <option value="overridden">Overridden</option>
          </select>
          <label className="sr-only" htmlFor="ai-risk">Risk band</label>
          <select id="ai-risk" className="form-select" value={filters.risk_level} onChange={setFilter('risk_level')}>
            <option value="">All risk bands</option>
            {THREAT_LEVELS.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
          </select>
        </div>
      </div>

      <AIAdvisoryBanner status={status} />

      <div className="table-container">
        {list.loading ? <LoadingState label="Loading AI outputs…" />
          : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
          : list.rows.length === 0 ? (
            <EmptyState icon={Brain} title="Nothing to review">Run an assessment from a record or case you are assigned to.</EmptyState>
          ) : (
            <div className="table-scroll">
              <table>
                <caption className="sr-only">AI outputs</caption>
                <thead>
                  <tr>
                    <th scope="col">#</th><th scope="col">Subject</th><th scope="col">Suggested category</th>
                    <th scope="col">Model score</th><th scope="col">Prototype risk</th><th scope="col">Generated</th>
                    <th scope="col">Review</th><th scope="col"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {list.rows.map((p) => (
                    <tr key={p.id}>
                      <td className="td-mono">{p.id}</td>
                      <td>{p.criminal_id ? <Link to={`/criminals/${p.criminal_id}`}>{subjectLabel(p)}</Link>
                        : <Link to={`/cases/${p.case_id}`}>{subjectLabel(p)}</Link>}</td>
                      <td className="td-primary">{p.predicted_crime_type || '—'}</td>
                      <td className="td-mono">{formatScore(p.crime_type_confidence)}</td>
                      <td><RiskBadge score={p.risk_score} level={p.risk_level} showBar /></td>
                      <td className="td-mono">{formatDate(p.created_at)}</td>
                      <td><StatusBadge status={p.review_status} /></td>
                      <td style={{ textAlign: 'right' }}>
                        <button type="button" className={`btn btn-sm ${p.review_status === 'pending' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setSelected(p)}>
                          {p.review_status === 'pending' ? 'Review' : 'Inspect'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {!list.loading && !list.error && list.total > 0 && (
          <Pagination page={list.page} pageSize={list.pageSize} total={list.total} onPageChange={list.setPage} label="outputs" />
        )}
      </div>

      {selected && (
        <ReviewModal key={`${selected.id}-${selected.reviews?.length || 0}`} prediction={selected} status={status}
          onClose={() => setSelected(null)}
          onSubmitted={(updated) => { setSelected(updated); list.reload(); }} />
      )}
    </div>
  );
}

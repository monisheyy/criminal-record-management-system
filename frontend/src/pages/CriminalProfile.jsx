import { useCallback, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Brain, ChevronLeft, Clock, Download, Edit2, FileText, History, Plus, Trash2 } from 'lucide-react';
import { aiAPI, criminalsAPI, getErrorMessage, saveBlob } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { RiskBadge, StatusBadge } from '../components/RiskBadge';
import { AIAdvisoryBanner, ConfirmDialog, ErrorState, FieldHint, LoadingState, Modal } from '../components/ui';
import ExplanationPanel from '../components/ExplanationPanel';
import ProfilePhoto from '../components/ProfilePhoto';
import { CRIME_TYPES, GENDERS, THREAT_LEVELS } from '../utils/constants';
import { formatDate, formatScore, todayInputValue } from '../utils/format';
import { humanize } from '../utils/errors';
import { useApiQuery } from '../utils/useApiQuery';

const HISTORY_TYPES = ['arrest', 'charge', 'conviction', 'acquittal', 'release', 'parole', 'warrant_issued',
  'warrant_cleared', 'bail_granted', 'wanted_notice', 'sighting', 'associate_link', 'note'];

function EditModal({ profile, onClose, onSaved }) {
  const initial = {
    first_name: profile.first_name, last_name: profile.last_name, alias: profile.alias || '',
    date_of_birth: profile.date_of_birth ? profile.date_of_birth.slice(0, 10) : '', gender: profile.gender || '',
    nationality: profile.nationality || '', occupation: profile.occupation || '', crime_type: profile.crime_type || '',
    prior_convictions: profile.prior_convictions ?? 0, threat_level: profile.threat_level || 'low',
    is_wanted: !!profile.is_wanted, is_incarcerated: !!profile.is_incarcerated, modus_operandi: profile.modus_operandi || '',
  };
  const [form, setForm] = useState(initial);
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const changed = Object.keys(form).filter((k) => String(form[k]) !== String(initial[k]));
  const sensitive = changed.some((k) => ['is_wanted', 'threat_level'].includes(k));

  const submit = async (e) => {
    e.preventDefault();
    if (!changed.length) { onClose(); return; }
    setSaving(true);
    setError('');
    const payload = Object.fromEntries(changed.map((k) => {
      let value = form[k];
      if (k === 'prior_convictions') value = Number(value) || 0;
      if (k === 'date_of_birth') value = value ? `${value}T00:00:00Z` : null;
      if (value === '' && !['first_name', 'last_name'].includes(k)) value = null;
      return [k, value];
    }));
    if (reason.trim()) payload.correction_reason = reason.trim();
    try {
      const res = await criminalsAPI.update(profile.id, payload);
      toast.success('Record updated; the change is in the record history.');
      onSaved(res.data);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not update the record.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Edit record" onClose={onClose} busy={saving} maxWidth={640}>
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <div className="form-grid">
            <div className="form-group"><label className="form-label" htmlFor="ed-first">First name *</label>
              <input id="ed-first" className="form-control" required maxLength={50} value={form.first_name} onChange={set('first_name')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="ed-last">Last name *</label>
              <input id="ed-last" className="form-control" required maxLength={50} value={form.last_name} onChange={set('last_name')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="ed-alias">Aliases</label>
              <input id="ed-alias" className="form-control" maxLength={200} value={form.alias} onChange={set('alias')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="ed-dob">Date of birth</label>
              <input id="ed-dob" className="form-control" type="date" max={todayInputValue()} min="1900-01-01" value={form.date_of_birth} onChange={set('date_of_birth')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="ed-gender">Gender</label>
              <select id="ed-gender" className="form-select" value={form.gender} onChange={set('gender')}>
                <option value="">Not recorded</option>{GENDERS.map((g) => <option key={g} value={g}>{g}</option>)}
              </select></div>
            <div className="form-group"><label className="form-label" htmlFor="ed-nat">Nationality</label>
              <input id="ed-nat" className="form-control" maxLength={50} value={form.nationality} onChange={set('nationality')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="ed-occ">Occupation</label>
              <input id="ed-occ" className="form-control" maxLength={100} value={form.occupation} onChange={set('occupation')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="ed-crime">Primary offence</label>
              <select id="ed-crime" className="form-select" value={form.crime_type} onChange={set('crime_type')}>
                <option value="">Not classified</option>{CRIME_TYPES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div className="form-group"><label className="form-label" htmlFor="ed-prior">Prior convictions</label>
              <input id="ed-prior" className="form-control" type="number" min={0} max={100} value={form.prior_convictions} onChange={set('prior_convictions')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="ed-threat">Threat level</label>
              <select id="ed-threat" className="form-select" value={form.threat_level} onChange={set('threat_level')}>
                {THREAT_LEVELS.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </select></div>
          </div>
          <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" checked={form.is_wanted} onChange={set('is_wanted')} /> Wanted</label>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" checked={form.is_incarcerated} onChange={set('is_incarcerated')} /> Incarcerated</label>
          </div>
          <div className="form-group"><label className="form-label" htmlFor="ed-mo">Modus operandi</label>
            <textarea id="ed-mo" className="form-control" rows={2} maxLength={5000} value={form.modus_operandi} onChange={set('modus_operandi')} /></div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" htmlFor="ed-reason">Reason for change {sensitive ? '*' : ''}</label>
            <textarea id="ed-reason" className="form-control" rows={2} maxLength={500} required={sensitive} value={reason} onChange={(e) => setReason(e.target.value)} />
            <FieldHint>Required when changing wanted status or threat level. Stored in the record history and audit log.</FieldHint>
          </div>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : `Save ${changed.length || ''} change${changed.length === 1 ? '' : 's'}`}</button>
        </div>
      </form>
    </Modal>
  );
}

function HistoryModal({ criminalId, onClose, onSaved }) {
  const [form, setForm] = useState({ event_type: 'arrest', description: '', location: '', case_reference: '', date: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = Object.fromEntries(Object.entries({ ...form, date: form.date ? `${form.date}T12:00:00Z` : null })
        .filter(([, v]) => v !== '' && v !== null));
      await criminalsAPI.addHistory(criminalId, payload);
      toast.success('History entry added.');
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title="Add history entry" onClose={onClose} busy={saving}>
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <div className="form-grid">
            <div className="form-group"><label className="form-label" htmlFor="h-type">Event *</label>
              <select id="h-type" className="form-select" value={form.event_type} onChange={set('event_type')}>
                {HISTORY_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </select></div>
            <div className="form-group"><label className="form-label" htmlFor="h-date">Date</label>
              <input id="h-date" className="form-control" type="date" max={todayInputValue()} value={form.date} onChange={set('date')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="h-loc">Location</label>
              <input id="h-loc" className="form-control" maxLength={200} value={form.location} onChange={set('location')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="h-ref">Case reference</label>
              <input id="h-ref" className="form-control" maxLength={50} value={form.case_reference} onChange={set('case_reference')} /></div>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label" htmlFor="h-desc">Description *</label>
            <textarea id="h-desc" className="form-control" rows={3} required minLength={3} maxLength={2000} value={form.description} onChange={set('description')} /></div>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Add entry'}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function CriminalProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isAdmin, isOfficer, isClerk } = useAuth();
  const canUseAI = isAdmin || isOfficer;

  const [predicting, setPredicting] = useState(false);
  const [downloading, setDownloading] = useState('');
  const [dialog, setDialog] = useState(null);

  const loadRecord = useCallback(async () => {
    const [profileRes, histRes] = await Promise.all([criminalsAPI.get(id), criminalsAPI.history(id)]);
    let predictions = [];
    let aiStatus = null;
    if (canUseAI) {
      // AI data is optional context: its failure must not hide the record itself.
      const [preds, status] = await Promise.allSettled([aiAPI.list({ criminal_id: id, limit: 5 }), aiAPI.status()]);
      predictions = preds.status === 'fulfilled' ? preds.value.data || [] : [];
      aiStatus = status.status === 'fulfilled' ? status.value.data : null;
    }
    return { data: { profile: profileRes.data, history: histRes.data || [], predictions, aiStatus } };
  }, [id, canUseAI]);
  const record = useApiQuery(loadRecord, { fallbackError: 'Failed to load the record.' });
  const { loading, error, reload: fetchAll, setData } = record;
  const profile = record.data?.profile ?? null;
  const history = record.data?.history ?? [];
  const predictions = record.data?.predictions ?? [];
  const aiStatus = record.data?.aiStatus ?? null;
  const setProfile = (next) => setData((d) => ({ ...d, profile: next }));
  const setPredictions = (update) => setData((d) => ({ ...d, predictions: update(d.predictions) }));

  const handlePredict = async () => {
    setPredicting(true);
    try {
      const res = await aiAPI.predict({ criminal_id: Number(id) });
      setPredictions((prev) => [res.data, ...prev]);
      toast.success('AI assessment created. It is unverified until a reviewer records a decision.');
    } catch (err) {
      toast.error(getErrorMessage(err, 'AI assessment failed.'));
    } finally {
      setPredicting(false);
    }
  };

  const downloadReport = async (format) => {
    setDownloading(format);
    try {
      const res = format === 'excel' ? await criminalsAPI.reportExcel(id) : await criminalsAPI.report(id);
      saveBlob(res, `record_${profile.crn}.${format === 'excel' ? 'xlsx' : 'pdf'}`);
      toast.success(`${format === 'excel' ? 'Excel' : 'PDF'} downloaded.`);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Download failed.'));
    } finally {
      setDownloading('');
    }
  };

  if (loading && !profile) return <LoadingState label="Loading record…" minHeight="50vh" />;
  if (error || !profile) return (
    <div>
      <ErrorState message={error || 'Record not found.'} onRetry={fetchAll} />
      <div style={{ textAlign: 'center' }}><Link to="/criminals" className="btn btn-secondary">Back to directory</Link></div>
    </div>
  );

  const latest = predictions[0] ?? null;
  const initials = `${profile.first_name?.[0] || ''}${profile.last_name?.[0] || ''}`.toUpperCase() || 'CR';

  return (
    <div>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Link to="/criminals" className="btn btn-secondary btn-icon" aria-label="Back to directory"><ChevronLeft size={16} aria-hidden="true" /></Link>
          <div>
            <h1 className="page-title">{profile.first_name} {profile.last_name}</h1>
            <p className="page-subtitle">CRN <span className="mono">{profile.crn}</span> · {profile.crime_type || 'Not classified'}</p>
          </div>
        </div>
        <div className="header-actions">
          <button type="button" className="btn btn-secondary" onClick={() => setDialog('edit')}><Edit2 size={14} aria-hidden="true" /> Edit</button>
          <button type="button" className="btn btn-secondary" onClick={() => downloadReport('pdf')} disabled={!!downloading}>
            <Download size={14} aria-hidden="true" /> {downloading === 'pdf' ? 'Preparing…' : 'Export PDF'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => downloadReport('excel')} disabled={!!downloading}>
            <FileText size={14} aria-hidden="true" /> {downloading === 'excel' ? 'Preparing…' : 'Export Excel'}
          </button>
          {(isAdmin || isClerk) && (
            <button type="button" className="btn btn-danger" onClick={() => setDialog('delete')}><Trash2 size={14} aria-hidden="true" /> Delete</button>
          )}
        </div>
      </div>

      <div className="dossier-card">
        <div className="dossier-header">
          <ProfilePhoto profile={profile} initials={initials} onChange={(updated) => { setProfile(updated); fetchAll(); }} />
          <div className="dossier-info">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <div className="dossier-name">{profile.first_name} {profile.last_name}</div>
              {profile.is_wanted && <span className="badge badge-red">Wanted</span>}
              {profile.is_incarcerated && <span className="badge badge-gray">Incarcerated</span>}
            </div>
            <div className="dossier-aliases">
              {profile.alias ? <>Also known as <strong>{profile.alias}</strong> · </> : null}Registered {formatDate(profile.created_at)}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="stat-label">Officer-assessed threat level</div>
            <StatusBadge status={profile.threat_level || 'low'} />
          </div>
        </div>
        <dl className="detail-grid" style={{ paddingTop: 16, borderTop: '1px solid var(--border-subtle)' }}>
          <div><dt>Date of birth</dt><dd>{formatDate(profile.date_of_birth)}</dd></div>
          <div><dt>Gender</dt><dd>{profile.gender || '—'}</dd></div>
          <div><dt>Nationality</dt><dd>{profile.nationality || '—'}</dd></div>
          <div><dt>Occupation</dt><dd>{profile.occupation || '—'}</dd></div>
          <div><dt>Prior convictions</dt><dd className="mono">{profile.prior_convictions ?? 0}</dd></div>
          <div><dt>Gang affiliation</dt><dd>{profile.gang ? `${profile.gang.name}${profile.gang_rank ? ` (${profile.gang_rank})` : ''}` : 'None recorded'}</dd></div>
          {profile.modus_operandi && <div style={{ gridColumn: '1 / -1' }}><dt>Modus operandi</dt><dd>{profile.modus_operandi}</dd></div>}
        </dl>
      </div>

      {canUseAI && (
        <section className="card" aria-labelledby="ai-heading">
          <div className="card-header">
            <h2 className="card-title" id="ai-heading"><Brain size={16} aria-hidden="true" style={{ color: 'var(--accent-blue)' }} /> AI decision support</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn btn-primary btn-sm" onClick={handlePredict} disabled={predicting || aiStatus?.predictions_enabled === false}>
                <Brain size={13} aria-hidden="true" /> {predicting ? 'Running…' : 'Run assessment'}
              </button>
              <Link className="btn btn-ghost btn-sm" to="/ai-predictions">Review queue</Link>
            </div>
          </div>
          <AIAdvisoryBanner status={aiStatus} compact={!!latest} />
          {latest ? (
            <>
              <div className="stats-grid" style={{ marginTop: 12 }}>
                <div className="stat-card"><span className="stat-label">Model's suggested category</span><div className="stat-value-sm">{latest.predicted_crime_type}</div></div>
                <div className="stat-card"><span className="stat-label">Model score (uncalibrated)</span><div className="stat-value-sm mono">{formatScore(latest.crime_type_confidence)}</div></div>
                <div className="stat-card"><span className="stat-label">Prototype risk score</span><div style={{ marginTop: 4 }}><RiskBadge score={latest.risk_score} level={latest.risk_level} showBar /></div></div>
                <div className="stat-card"><span className="stat-label">Human review</span><div style={{ marginTop: 4 }}><StatusBadge status={latest.review_status} /></div></div>
              </div>
              <ExplanationPanel prediction={latest} />
            </>
          ) : (
            <p className="td-sub" style={{ marginTop: 12 }}>No assessment has been generated for this record.</p>
          )}
        </section>
      )}

      <section className="card" aria-labelledby="history-heading">
        <div className="card-header">
          <h2 className="card-title" id="history-heading"><History size={16} aria-hidden="true" style={{ color: 'var(--accent-blue)' }} /> Record history</h2>
          {canUseAI && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDialog('history')}><Plus size={13} aria-hidden="true" /> Add entry</button>}
        </div>
        {history.length === 0 ? <p className="td-sub">No history entries.</p> : (
          <ol className="timeline">
            {history.map((rec) => (
              <li key={rec.id}>
                <div className="timeline-title">{humanize(rec.event_type)}</div>
                <div className="timeline-body">{rec.description}</div>
                <div className="timeline-meta">
                  <span><Clock size={11} aria-hidden="true" /> {formatDate(rec.date)}</span>
                  {rec.location && <span>{rec.location}</span>}
                  {rec.case_reference && <span>Case {rec.case_reference}</span>}
                  {rec.recorded_by && <span>Recorded by {rec.recorded_by}</span>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      {dialog === 'edit' && <EditModal profile={profile} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); fetchAll(); }} />}
      {dialog === 'history' && <HistoryModal criminalId={id} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); fetchAll(); }} />}
      {dialog === 'delete' && (
        <ConfirmDialog title="Delete record" danger requireReason confirmLabel="Delete permanently"
          message="Records linked to cases or with AI assessments cannot be deleted; correct them instead. Deletion is audited."
          onCancel={() => setDialog(null)}
          onConfirm={async (reason) => {
            try {
              await criminalsAPI.delete(id, reason);
              toast.success('Record deleted.');
              navigate('/criminals');
            } catch (err) {
              toast.error(getErrorMessage(err));
            }
          }} />
      )}
    </div>
  );
}

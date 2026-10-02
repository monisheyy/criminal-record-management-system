import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  Activity, Brain, Calendar, ChevronLeft, Download, FileText, MapPin, Paperclip, Plus, Shield, Trash2,
  UserPlus, Users,
} from 'lucide-react';
import { aiAPI, casesAPI, criminalsAPI, getErrorMessage, saveBlob, usersAPI } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import NetworkGraph from '../components/NetworkGraph';
import { PriorityBadge, StatusBadge } from '../components/RiskBadge';
import { ConfirmDialog, EmptyState, ErrorState, FieldHint, LoadingState, Modal } from '../components/ui';
import {
  CASE_ROLES, CASE_STATUSES, CASE_STATUS_TRANSITIONS, EVIDENCE_STATUSES, EVIDENCE_TYPES, GENDERS, VICTIM_STATUSES,
} from '../utils/constants';
import { formatDate, localInputToIso, nowLocalInputValue } from '../utils/format';
import { humanize } from '../utils/errors';

const TABS = [
  { id: 'overview', label: 'Overview', icon: FileText },
  { id: 'criminals', label: 'Linked persons', icon: Shield },
  { id: 'victims', label: 'Victims', icon: Users },
  { id: 'evidence', label: 'Evidence', icon: Paperclip },
];

const labelFor = (options, value) => options.find((o) => o.value === value)?.label || humanize(value || '—');

function FormModal({ title, onClose, onSubmit, submitLabel, children, maxWidth }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await onSubmit();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title={title} onClose={onClose} busy={saving} maxWidth={maxWidth}>
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          {children}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? <><span className="spinner" aria-hidden="true" /> Saving…</> : submitLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function LinkCriminalModal({ caseId, linkedIds, onClose, onDone }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [role, setRole] = useState('suspect');

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) { setResults([]); return undefined; }
    let cancelled = false;
    const timer = setTimeout(() => {
      criminalsAPI.list({ search: term, limit: 10 })
        .then((res) => { if (!cancelled) setResults((res.data || []).filter((c) => !linkedIds.includes(c.id))); })
        .catch(() => { if (!cancelled) setResults([]); });
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, linkedIds]);

  return (
    <FormModal title="Link a person to this case" onClose={onClose} submitLabel="Link record"
      onSubmit={async () => {
        if (!selected) throw new Error('Select a record from the search results first.');
        await casesAPI.addCriminal(caseId, selected.id, role);
        toast.success(`${selected.first_name} ${selected.last_name} linked.`);
        onDone();
      }}>
      <div className="form-group">
        <label className="form-label" htmlFor="link-search">Search offender records</label>
        <input id="link-search" className="form-control" type="search" value={query} placeholder="Name, alias or CRN"
          onChange={(e) => { setQuery(e.target.value); setSelected(null); }} />
      </div>
      {results.length > 0 && (
        <ul className="picker-list" role="listbox" aria-label="Matching records">
          {results.map((c) => (
            <li key={c.id} role="option" aria-selected={selected?.id === c.id}>
              <button type="button" className={`picker-item ${selected?.id === c.id ? 'selected' : ''}`} onClick={() => setSelected(c)}>
                <strong>{c.first_name} {c.last_name}</strong> <span className="td-sub">{c.crn} · {c.crime_type || 'Not classified'}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {query.trim().length >= 2 && results.length === 0 && <FieldHint>No unlinked records match.</FieldHint>}
      <div className="form-group" style={{ marginTop: 12 }}>
        <label className="form-label" htmlFor="link-role">Role in case</label>
        <select id="link-role" className="form-select" value={role} onChange={(e) => setRole(e.target.value)}>
          {CASE_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
      </div>
    </FormModal>
  );
}

function VictimModal({ caseId, onClose, onDone }) {
  const [form, setForm] = useState({ first_name: '', last_name: '', age: '', gender: '', status: 'alive', phone: '', injury_description: '', statement: '' });
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  return (
    <FormModal title="Add victim" onClose={onClose} submitLabel="Save victim" maxWidth={600}
      onSubmit={async () => {
        const payload = Object.fromEntries(Object.entries({ ...form, age: form.age === '' ? null : Number(form.age) })
          .filter(([, v]) => v !== '' && v !== null));
        await casesAPI.addVictim(caseId, payload);
        toast.success('Victim added.');
        onDone();
      }}>
      <div className="form-grid">
        <div className="form-group"><label className="form-label" htmlFor="v-first">First name *</label>
          <input id="v-first" className="form-control" required maxLength={50} value={form.first_name} onChange={set('first_name')} /></div>
        <div className="form-group"><label className="form-label" htmlFor="v-last">Last name *</label>
          <input id="v-last" className="form-control" required maxLength={50} value={form.last_name} onChange={set('last_name')} /></div>
        <div className="form-group"><label className="form-label" htmlFor="v-age">Age</label>
          <input id="v-age" className="form-control" type="number" min={0} max={130} value={form.age} onChange={set('age')} /></div>
        <div className="form-group"><label className="form-label" htmlFor="v-gender">Gender</label>
          <select id="v-gender" className="form-select" value={form.gender} onChange={set('gender')}>
            <option value="">Not recorded</option>{GENDERS.map((g) => <option key={g} value={g}>{g}</option>)}
          </select></div>
        <div className="form-group"><label className="form-label" htmlFor="v-status">Condition *</label>
          <select id="v-status" className="form-select" value={form.status} onChange={set('status')}>
            {VICTIM_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select></div>
        <div className="form-group"><label className="form-label" htmlFor="v-phone">Phone</label>
          <input id="v-phone" className="form-control" type="tel" maxLength={20} value={form.phone} onChange={set('phone')} /></div>
      </div>
      <div className="form-group"><label className="form-label" htmlFor="v-injury">Injury description</label>
        <textarea id="v-injury" className="form-control" rows={2} maxLength={5000} value={form.injury_description} onChange={set('injury_description')} /></div>
      <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label" htmlFor="v-statement">Statement</label>
        <textarea id="v-statement" className="form-control" rows={3} maxLength={10000} value={form.statement} onChange={set('statement')} /></div>
    </FormModal>
  );
}

function EvidenceModal({ caseId, onClose, onDone }) {
  const [form, setForm] = useState({ type: 'physical', description: '', location_found: '', collected_by: '', collected_at: '', status: 'collected', file_url: '', file_sha256: '', chain_of_custody: '' });
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  return (
    <FormModal title="Log evidence item" onClose={onClose} submitLabel="Save evidence" maxWidth={620}
      onSubmit={async () => {
        const payload = Object.fromEntries(Object.entries({ ...form, collected_at: localInputToIso(form.collected_at) })
          .filter(([, v]) => v !== '' && v !== null));
        await casesAPI.addEvidence(caseId, payload);
        toast.success('Evidence logged with an initial custody entry.');
        onDone();
      }}>
      <div className="form-group"><label className="form-label" htmlFor="e-desc">Description *</label>
        <input id="e-desc" className="form-control" required minLength={3} maxLength={5000} value={form.description} onChange={set('description')} /></div>
      <div className="form-grid">
        <div className="form-group"><label className="form-label" htmlFor="e-type">Type *</label>
          <select id="e-type" className="form-select" value={form.type} onChange={set('type')}>
            {EVIDENCE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select></div>
        <div className="form-group"><label className="form-label" htmlFor="e-status">Status *</label>
          <select id="e-status" className="form-select" value={form.status} onChange={set('status')}>
            {EVIDENCE_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select></div>
        <div className="form-group"><label className="form-label" htmlFor="e-loc">Location found</label>
          <input id="e-loc" className="form-control" maxLength={200} value={form.location_found} onChange={set('location_found')} /></div>
        <div className="form-group"><label className="form-label" htmlFor="e-by">Collected by</label>
          <input id="e-by" className="form-control" maxLength={100} value={form.collected_by} onChange={set('collected_by')} /></div>
        <div className="form-group"><label className="form-label" htmlFor="e-at">Collected at</label>
          <input id="e-at" className="form-control" type="datetime-local" max={nowLocalInputValue()} value={form.collected_at} onChange={set('collected_at')} /></div>
        <div className="form-group"><label className="form-label" htmlFor="e-url">File reference URL</label>
          <input id="e-url" className="form-control" type="url" maxLength={500} placeholder="https://…" value={form.file_url} onChange={set('file_url')} /></div>
      </div>
      <div className="form-group"><label className="form-label" htmlFor="e-hash">File SHA-256</label>
        <input id="e-hash" className="form-control mono" maxLength={64} pattern="[0-9a-fA-F]{64}" value={form.file_sha256} onChange={set('file_sha256')} />
        <FieldHint>Optional. Record the hash at collection time so later copies can be verified.</FieldHint></div>
      <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label" htmlFor="e-custody">Initial custody notes</label>
        <textarea id="e-custody" className="form-control" rows={2} maxLength={5000} value={form.chain_of_custody} onChange={set('chain_of_custody')} /></div>
    </FormModal>
  );
}

function EvidenceUpdateModal({ caseId, evidence, onClose, onDone }) {
  const [status, setStatus] = useState(evidence.status);
  const [note, setNote] = useState('');
  return (
    <FormModal title={`Update ${evidence.evidence_number}`} onClose={onClose} submitLabel="Record update"
      onSubmit={async () => {
        await casesAPI.updateEvidence(caseId, evidence.id, { status, custody_note: note });
        toast.success('Custody log updated.');
        onDone();
      }}>
      <div className="form-group"><label className="form-label" htmlFor="eu-status">Status</label>
        <select id="eu-status" className="form-select" value={status} onChange={(e) => setStatus(e.target.value)}>
          {EVIDENCE_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select></div>
      <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label" htmlFor="eu-note">Custody note *</label>
        <textarea id="eu-note" className="form-control" rows={3} required minLength={3} maxLength={1000} value={note}
          onChange={(e) => setNote(e.target.value)} placeholder="Who moved it, where, and why" />
        <FieldHint>Appended to the chain of custody; earlier entries are never overwritten.</FieldHint></div>
    </FormModal>
  );
}

function StatusModal({ caseFile, isAdmin, onClose, onDone }) {
  const options = isAdmin ? CASE_STATUSES.map((s) => s.value).filter((v) => v !== caseFile.status)
    : CASE_STATUS_TRANSITIONS[caseFile.status] || [];
  const [status, setStatus] = useState(options[0] || '');
  const [reason, setReason] = useState('');
  return (
    <FormModal title="Change case status" onClose={onClose} submitLabel="Update status"
      onSubmit={async () => {
        await casesAPI.update(caseFile.id, { status, status_reason: reason || undefined });
        toast.success(`Case moved to ${labelFor(CASE_STATUSES, status)}.`);
        onDone();
      }}>
      {options.length === 0 ? <p>No further status changes are available for this case.</p> : (
        <>
          <div className="form-group"><label className="form-label" htmlFor="cs-status">New status</label>
            <select id="cs-status" className="form-select" value={status} onChange={(e) => setStatus(e.target.value)}>
              {options.map((v) => <option key={v} value={v}>{labelFor(CASE_STATUSES, v)}</option>)}
            </select></div>
          <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label" htmlFor="cs-reason">
            Reason {status === 'closed' ? '*' : '(recommended)'}</label>
            <textarea id="cs-reason" className="form-control" rows={3} maxLength={500} required={status === 'closed'}
              value={reason} onChange={(e) => setReason(e.target.value)} /></div>
        </>
      )}
    </FormModal>
  );
}

function AssignModal({ caseFile, isAdmin, userId, onClose, onDone }) {
  const [officers, setOfficers] = useState([]);
  const [officerId, setOfficerId] = useState(isAdmin ? '' : String(userId));
  useEffect(() => {
    if (isAdmin) usersAPI.officers().then((res) => setOfficers(res.data || [])).catch(() => setOfficers([]));
  }, [isAdmin]);
  return (
    <FormModal title="Assign investigating officer" onClose={onClose} submitLabel="Assign"
      onSubmit={async () => {
        if (!officerId) throw new Error('Choose an officer.');
        const res = await casesAPI.assign(caseFile.id, officerId);
        toast.success(res.data.message);
        onDone();
      }}>
      {isAdmin ? (
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label" htmlFor="assign-officer">Officer</label>
          <select id="assign-officer" className="form-select" required value={officerId} onChange={(e) => setOfficerId(e.target.value)}>
            <option value="">Select an active officer…</option>
            {officers.map((o) => <option key={o.id} value={o.id}>{o.full_name}{o.badge_number ? ` (${o.badge_number})` : ''}{o.department ? ` · ${o.department}` : ''}</option>)}
          </select>
        </div>
      ) : <p>Take ownership of this unassigned case? It will move to “Under investigation”.</p>}
    </FormModal>
  );
}

export default function CaseDetails() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, isAdmin, isOfficer } = useAuth();
  const [caseFile, setCaseFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('overview');
  const [dialog, setDialog] = useState(null);
  const [downloading, setDownloading] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    casesAPI.get(id)
      .then((res) => setCaseFile(res.data))
      .catch((err) => setError(getErrorMessage(err, 'Failed to load the case.')))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const done = () => { setDialog(null); load(); };

  const download = async (format) => {
    setDownloading(format);
    try {
      const res = format === 'excel' ? await casesAPI.reportExcel(id) : await casesAPI.report(id);
      saveBlob(res, `case_${id}.${format === 'excel' ? 'xlsx' : 'pdf'}`);
      toast.success(`${format === 'excel' ? 'Excel' : 'PDF'} report downloaded.`);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Report download failed.'));
    } finally {
      setDownloading('');
    }
  };

  const runAssessment = async () => {
    try {
      const res = await aiAPI.predict({ case_id: Number(id) });
      toast.success(`AI assessment #${res.data.id} created — it requires human review.`);
      navigate('/ai-predictions');
    } catch (err) {
      toast.error(getErrorMessage(err, 'AI assessment failed.'));
    }
  };

  if (loading && !caseFile) return <LoadingState label="Loading case workspace…" minHeight="50vh" />;
  if (error && !caseFile) return (
    <div>
      <ErrorState message={error} onRetry={load} />
      <div style={{ textAlign: 'center' }}><Link to="/cases" className="btn btn-secondary">Back to cases</Link></div>
    </div>
  );

  const canWrite = isAdmin || (isOfficer && [null, user.id].includes(caseFile.assigned_officer_id ?? null));
  const canAssign = isAdmin || (isOfficer && caseFile.assigned_officer_id == null);
  const canAssess = isAdmin || (isOfficer && caseFile.assigned_officer_id === user.id);
  const linkedIds = caseFile.criminals.map((cc) => cc.criminal_id);

  return (
    <div>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Link to="/cases" className="btn btn-secondary btn-icon" aria-label="Back to cases"><ChevronLeft size={16} aria-hidden="true" /></Link>
          <div>
            <h1 className="page-title">{caseFile.title}</h1>
            <p className="page-subtitle"><span className="mono">{caseFile.case_number}</span> · {caseFile.crime_type || 'Unclassified'}</p>
          </div>
        </div>
        <div className="header-actions">
          <button type="button" className="btn btn-secondary" onClick={() => download('pdf')} disabled={!!downloading}>
            <Download size={14} aria-hidden="true" /> {downloading === 'pdf' ? 'Preparing…' : 'PDF'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => download('excel')} disabled={!!downloading}>
            <FileText size={14} aria-hidden="true" /> {downloading === 'excel' ? 'Preparing…' : 'Excel'}
          </button>
          {canAssess && (
            <button type="button" className="btn btn-secondary" onClick={runAssessment} title="Creates an unverified AI output that must be reviewed">
              <Brain size={14} aria-hidden="true" /> AI assessment
            </button>
          )}
          {canWrite && (
            <button type="button" className="btn btn-secondary" onClick={() => setDialog({ type: 'status' })}>
              <Activity size={14} aria-hidden="true" /> Change status
            </button>
          )}
          {canAssign && (
            <button type="button" className="btn btn-primary" onClick={() => setDialog({ type: 'assign' })}>
              <UserPlus size={14} aria-hidden="true" /> {isAdmin ? 'Assign officer' : 'Assign to me'}
            </button>
          )}
        </div>
      </div>

      <div className="card">
        <dl className="detail-grid">
          <div><dt>Status</dt><dd><StatusBadge status={caseFile.status} /></dd></div>
          <div><dt>Priority</dt><dd><PriorityBadge priority={caseFile.priority} /></dd></div>
          <div><dt><MapPin size={12} aria-hidden="true" /> Location</dt><dd>{caseFile.location || '—'}</dd></div>
          <div><dt><Calendar size={12} aria-hidden="true" /> Incident</dt><dd>{formatDate(caseFile.incident_date, { withTime: true })}</dd></div>
          <div><dt>Investigating officer</dt><dd>{caseFile.assigned_officer?.full_name || 'Unassigned'}</dd></div>
          <div><dt>Last updated</dt><dd>{formatDate(caseFile.updated_at || caseFile.created_at, { withTime: true })}</dd></div>
        </dl>
        {!canWrite && isOfficer && (
          <p className="td-sub" style={{ marginTop: 10 }}>This case is assigned to another officer; it is read-only for you.</p>
        )}
      </div>

      {(isAdmin || isOfficer) && <NetworkGraph caseId={Number(id)} depth={2} />}

      <div className="tab-nav" role="tablist" aria-label="Case sections">
        {TABS.map((t) => {
          const count = { criminals: caseFile.criminals.length, victims: caseFile.victims.length, evidence: caseFile.evidence.length }[t.id];
          return (
            <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`panel-${t.id}`}
              className={`tab-item ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
              <t.icon size={14} aria-hidden="true" /> {t.label}{count !== undefined ? ` (${count})` : ''}
            </button>
          );
        })}
      </div>

      <section role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'overview' && (
          <div className="card">
            <h2 className="card-title" style={{ marginBottom: 10 }}>FIR summary &amp; description</h2>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
              {caseFile.description || 'No description recorded.'}
            </p>
            <dl className="detail-grid" style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border-subtle)' }}>
              <div><dt>FIR number</dt><dd className="mono">{caseFile.fir_number || '—'}</dd></div>
              <div><dt>FIR date</dt><dd>{formatDate(caseFile.fir_date)}</dd></div>
              <div><dt>Police station</dt><dd>{caseFile.fir_station || '—'}</dd></div>
              <div><dt>Filed by</dt><dd>{caseFile.fir_filed_by || '—'}</dd></div>
              <div><dt>Complainant</dt><dd>{caseFile.complainant_name || '—'}</dd></div>
              <div><dt>Complainant contact</dt><dd>{caseFile.complainant_contact || '—'}</dd></div>
              <div><dt>Opened</dt><dd>{formatDate(caseFile.created_at, { withTime: true })}</dd></div>
              <div><dt>Closed</dt><dd>{formatDate(caseFile.closed_at, { withTime: true })}</dd></div>
            </dl>
          </div>
        )}

        {tab === 'criminals' && (
          <div className="table-container">
            <div className="table-toolbar">
              <h2 className="table-title">Linked persons</h2>
              {canWrite && <button type="button" className="btn btn-primary btn-sm" onClick={() => setDialog({ type: 'link' })}><Plus size={13} aria-hidden="true" /> Link record</button>}
            </div>
            {caseFile.criminals.length === 0 ? <EmptyState icon={Shield} title="No records linked to this case" /> : (
              <div className="table-scroll"><table>
                <thead><tr><th scope="col">CRN</th><th scope="col">Name</th><th scope="col">Role</th><th scope="col">Primary offence</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>{caseFile.criminals.map((cc) => (
                  <tr key={cc.id}>
                    <td className="td-mono">{cc.criminal.crn}</td>
                    <td className="td-primary"><Link to={`/criminals/${cc.criminal_id}`}>{cc.criminal.first_name} {cc.criminal.last_name}</Link></td>
                    <td><span className="badge badge-gray">{labelFor(CASE_ROLES, cc.role)}</span></td>
                    <td>{cc.criminal.crime_type || '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      {canWrite && (
                        <button type="button" className="btn btn-ghost btn-sm" aria-label={`Unlink ${cc.criminal.first_name} ${cc.criminal.last_name}`}
                          onClick={() => setDialog({ type: 'unlink', link: cc })}><Trash2 size={13} aria-hidden="true" /></button>
                      )}
                    </td>
                  </tr>))}
                </tbody></table></div>
            )}
          </div>
        )}

        {tab === 'victims' && (
          <div className="table-container">
            <div className="table-toolbar">
              <h2 className="table-title">Victims</h2>
              {canWrite && <button type="button" className="btn btn-primary btn-sm" onClick={() => setDialog({ type: 'victim' })}><Plus size={13} aria-hidden="true" /> Add victim</button>}
            </div>
            {caseFile.victims.length === 0 ? <EmptyState icon={Users} title="No victims recorded" /> : (
              <div className="table-scroll"><table>
                <thead><tr><th scope="col">Name</th><th scope="col">Age</th><th scope="col">Gender</th><th scope="col">Condition</th><th scope="col">Injuries</th></tr></thead>
                <tbody>{caseFile.victims.map((v) => (
                  <tr key={v.id}>
                    <td className="td-primary">{v.first_name} {v.last_name}</td>
                    <td>{v.age ?? '—'}</td>
                    <td>{v.gender || '—'}</td>
                    <td><span className="badge badge-amber">{labelFor(VICTIM_STATUSES, v.status)}</span></td>
                    <td style={{ maxWidth: 320 }}>{v.injury_description || '—'}</td>
                  </tr>))}
                </tbody></table></div>
            )}
          </div>
        )}

        {tab === 'evidence' && (
          <div className="table-container">
            <div className="table-toolbar">
              <h2 className="table-title">Evidence inventory</h2>
              {canWrite && <button type="button" className="btn btn-primary btn-sm" onClick={() => setDialog({ type: 'evidence' })}><Plus size={13} aria-hidden="true" /> Log evidence</button>}
            </div>
            {caseFile.evidence.length === 0 ? <EmptyState icon={Paperclip} title="No evidence logged" /> : (
              <div className="table-scroll"><table>
                <thead><tr><th scope="col">Number</th><th scope="col">Type</th><th scope="col">Description</th><th scope="col">Found at</th><th scope="col">Status</th><th scope="col">Custody log</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>{caseFile.evidence.map((ev) => (
                  <tr key={ev.id}>
                    <td className="td-mono">{ev.evidence_number}{ev.file_sha256 && <div className="td-sub" title={ev.file_sha256}>SHA-256 {ev.file_sha256.slice(0, 10)}…</div>}</td>
                    <td><span className="badge badge-purple">{labelFor(EVIDENCE_TYPES, ev.type)}</span></td>
                    <td className="td-primary">{ev.description}</td>
                    <td>{ev.location_found || '—'}</td>
                    <td><span className="badge badge-green">{labelFor(EVIDENCE_STATUSES, ev.status)}</span></td>
                    <td>
                      <details>
                        <summary className="td-sub">{(ev.chain_of_custody || '').split('\n').filter(Boolean).length} entries</summary>
                        <pre className="custody-log">{ev.chain_of_custody || 'No entries'}</pre>
                      </details>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {canWrite && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDialog({ type: 'evidence-update', evidence: ev })}>Update</button>}
                    </td>
                  </tr>))}
                </tbody></table></div>
            )}
          </div>
        )}
      </section>

      {dialog?.type === 'link' && <LinkCriminalModal caseId={id} linkedIds={linkedIds} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.type === 'victim' && <VictimModal caseId={id} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.type === 'evidence' && <EvidenceModal caseId={id} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.type === 'evidence-update' && <EvidenceUpdateModal caseId={id} evidence={dialog.evidence} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.type === 'status' && <StatusModal caseFile={caseFile} isAdmin={isAdmin} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.type === 'assign' && <AssignModal caseFile={caseFile} isAdmin={isAdmin} userId={user.id} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.type === 'unlink' && (
        <ConfirmDialog title="Unlink record" danger requireReason confirmLabel="Unlink"
          message={`Remove ${dialog.link.criminal.first_name} ${dialog.link.criminal.last_name} from this case? The change is recorded in the audit log.`}
          onCancel={() => setDialog(null)}
          onConfirm={async (reason) => {
            try {
              await casesAPI.removeCriminal(id, dialog.link.criminal_id, reason);
              toast.success('Record unlinked.');
              done();
            } catch (err) {
              toast.error(getErrorMessage(err));
            }
          }} />
      )}
    </div>
  );
}

import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ChevronRight, FileText, Plus, Search } from 'lucide-react';
import { casesAPI, getErrorMessage, usersAPI } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { getFieldErrors } from '../utils/errors';
import { CASE_CRIME_TYPES, CASE_INCIDENT_DETAILS, CASE_INCIDENT_FACTS, CASE_PRIORITIES, CASE_STATUSES } from '../utils/constants';
import { formatDate, localInputToIso, nowLocalInputValue } from '../utils/format';
import { usePagedList } from '../utils/usePagedList';
import { EmptyState, ErrorState, FieldError, FieldHint, LoadingState, Modal, Pagination } from '../components/ui';
import { PriorityBadge, StatusBadge } from '../components/RiskBadge';

const EMPTY_FORM = {
  title: '', description: '', crime_type: '', location: '', incident_date: '', priority: 'normal',
  fir_number: '', fir_station: '', complainant_name: '', complainant_contact: '', assigned_officer_id: '',
  ...Object.fromEntries(CASE_INCIDENT_FACTS.map((f) => [f.key, ''])),
  ...Object.fromEntries(CASE_INCIDENT_DETAILS.map((d) => [d.key, ''])),
};

// '' = not recorded (omitted from the payload), so "unknown" is never stored as "no".
const TRI_STATE = { yes: true, no: false };

function CreateCaseModal({ onClose, onCreated }) {
  const { isAdmin, isOfficer, user } = useAuth();
  const [form, setForm] = useState({ ...EMPTY_FORM, assigned_officer_id: isOfficer ? String(user.id) : '' });
  const [officers, setOfficers] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});

  useEffect(() => {
    if (isAdmin) usersAPI.officers().then((res) => setOfficers(res.data || [])).catch(() => setOfficers([]));
  }, [isAdmin]);

  const set = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
    setFieldErrors((errs) => ({ ...errs, [key]: undefined }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const payload = Object.fromEntries(Object.entries({
      ...form,
      incident_date: localInputToIso(form.incident_date),
      ...Object.fromEntries(CASE_INCIDENT_FACTS.map((f) => [f.key, TRI_STATE[form[f.key]] ?? null])),
      assigned_officer_id: form.assigned_officer_id ? Number(form.assigned_officer_id) : null,
    }).filter(([, v]) => v !== '' && v !== null));
    try {
      const res = await casesAPI.create(payload);
      toast.success(`Case ${res.data.case_number} created.`);
      onCreated(res.data);
    } catch (err) {
      setFieldErrors(getFieldErrors(err));
      setError(getErrorMessage(err, 'Could not create the case.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Register case file" onClose={onClose} busy={saving} maxWidth={640}>
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <div className="form-group">
            <label className="form-label" htmlFor="case-title">Case title *</label>
            <input id="case-title" className="form-control" required minLength={3} maxLength={200} value={form.title} onChange={set('title')} />
            <FieldError>{fieldErrors.title}</FieldError>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="case-desc">FIR summary / description</label>
            <textarea id="case-desc" className="form-control" rows={3} maxLength={10000} value={form.description} onChange={set('description')} />
          </div>
          <div className="form-grid">
            <div className="form-group">
              <label className="form-label" htmlFor="case-crime">Crime category</label>
              <select id="case-crime" className="form-select" value={form.crime_type} onChange={set('crime_type')}>
                <option value="">Unclassified</option>
                {CASE_CRIME_TYPES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="case-priority">Priority *</label>
              <select id="case-priority" className="form-select" required value={form.priority} onChange={set('priority')}>
                {CASE_PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="case-location">Incident location</label>
              <input id="case-location" className="form-control" maxLength={200} value={form.location} onChange={set('location')} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="case-date">Incident date &amp; time</label>
              <input id="case-date" className="form-control" type="datetime-local" max={nowLocalInputValue()}
                value={form.incident_date} onChange={set('incident_date')} />
              <FieldError>{fieldErrors.incident_date}</FieldError>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="case-fir">FIR number</label>
              <input id="case-fir" className="form-control" maxLength={30} value={form.fir_number} onChange={set('fir_number')} />
              <FieldHint>Leave blank to generate one.</FieldHint>
              <FieldError>{fieldErrors.fir_number}</FieldError>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="case-station">Police station</label>
              <input id="case-station" className="form-control" maxLength={100} value={form.fir_station} onChange={set('fir_station')} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="case-complainant">Complainant name</label>
              <input id="case-complainant" className="form-control" maxLength={100} value={form.complainant_name} onChange={set('complainant_name')} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="case-contact">Complainant phone</label>
              <input id="case-contact" className="form-control" type="tel" maxLength={20} value={form.complainant_contact} onChange={set('complainant_contact')} />
              <FieldError>{fieldErrors.complainant_contact}</FieldError>
            </div>
          </div>
          <fieldset className="form-group" style={{ border: 0, padding: 0, margin: '0 0 16px' }}>
            <legend className="form-label">Incident facts</legend>
            <FieldHint>Record only what the evidence shows; leave &ldquo;Not recorded&rdquo; when unknown. These are inputs to AI triage.</FieldHint>
            <div className="form-grid" style={{ marginTop: 8 }}>
              {CASE_INCIDENT_FACTS.map((f) => (
                <div className="form-group" key={f.key}>
                  <label className="form-label" htmlFor={`case-${f.key}`}>{f.label}</label>
                  <select id={`case-${f.key}`} className="form-select" value={form[f.key]} onChange={set(f.key)}>
                    <option value="">Not recorded</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                  <FieldError>{fieldErrors[f.key]}</FieldError>
                </div>
              ))}
              {CASE_INCIDENT_DETAILS.map((d) => (
                <div className="form-group" key={d.key}>
                  <label className="form-label" htmlFor={`case-${d.key}`}>{d.label}</label>
                  <select id={`case-${d.key}`} className="form-select" value={form[d.key]} onChange={set(d.key)}>
                    <option value="">Not recorded</option>
                    {d.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  <FieldError>{fieldErrors[d.key]}</FieldError>
                </div>
              ))}
            </div>
          </fieldset>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" htmlFor="case-officer">Investigating officer</label>
            {isAdmin ? (
              <select id="case-officer" className="form-select" value={form.assigned_officer_id} onChange={set('assigned_officer_id')}>
                <option value="">Unassigned</option>
                {officers.map((o) => <option key={o.id} value={o.id}>{o.full_name}{o.badge_number ? ` (${o.badge_number})` : ''}</option>)}
              </select>
            ) : (
              <select id="case-officer" className="form-select" value={form.assigned_officer_id} onChange={set('assigned_officer_id')}>
                <option value={String(user.id)}>Assign to me</option>
                <option value="">Leave unassigned</option>
              </select>
            )}
          </div>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? <><span className="spinner" aria-hidden="true" /> Saving…</> : 'Create case'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default function Cases() {
  const navigate = useNavigate();
  const { isAdmin, isOfficer } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [debouncedSearch, setDebouncedSearch] = useState(search.trim());
  const [creating, setCreating] = useState(false);
  const filters = {
    status: searchParams.get('status') || '',
    priority: searchParams.get('priority') || '',
    crime_type: searchParams.get('crime_type') || '',
    assigned_to_me: searchParams.get('mine') === '1' ? 'true' : '',
    sort: searchParams.get('sort') || '',
  };

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 350);
    return () => clearTimeout(timer);
  }, [search]);

  const list = usePagedList(casesAPI.list, { ...filters, search: debouncedSearch }, 25);

  const setFilter = (key) => (e) => {
    const next = new URLSearchParams(searchParams);
    const value = e.target.type === 'checkbox' ? (e.target.checked ? '1' : '') : e.target.value;
    if (value) next.set(key, value); else next.delete(key);
    setSearchParams(next, { replace: true });
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Cases &amp; FIR Workspace</h1>
          <p className="page-subtitle">{list.total.toLocaleString()} case file{list.total === 1 ? '' : 's'} match the current filters</p>
        </div>
        {(isAdmin || isOfficer) && (
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} aria-hidden="true" /> Register case
          </button>
        )}
      </div>

      <div className="table-container">
        <div className="table-toolbar" role="search">
          <div className="search-box">
            <Search size={13} aria-hidden="true" />
            <label htmlFor="case-search" className="sr-only">Search cases</label>
            <input id="case-search" className="form-control" type="search" placeholder="Search title, case #, FIR #, location…"
              value={search} onChange={(e) => setSearch(e.target.value)} maxLength={100} />
          </div>
          <div className="toolbar-filters">
            <label className="sr-only" htmlFor="cf-status">Status</label>
            <select id="cf-status" className="form-select" value={filters.status} onChange={setFilter('status')}>
              <option value="">All statuses</option>
              {CASE_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            <label className="sr-only" htmlFor="cf-priority">Priority</label>
            <select id="cf-priority" className="form-select" value={filters.priority} onChange={setFilter('priority')}>
              <option value="">All priorities</option>
              {CASE_PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            <label className="sr-only" htmlFor="cf-sort">Sort by</label>
            <select id="cf-sort" className="form-select" value={filters.sort} onChange={setFilter('sort')}>
              <option value="">Newest first</option>
              <option value="-incident_date">Most recent incident</option>
              <option value="title">Title A–Z</option>
              <option value="case_number">Case number</option>
            </select>
            {isOfficer && (
              <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: '0.8rem' }}>
                <input type="checkbox" checked={filters.assigned_to_me === 'true'} onChange={setFilter('mine')} /> My cases
              </label>
            )}
          </div>
        </div>

        {list.loading ? <LoadingState label="Loading case files…" />
          : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
          : list.rows.length === 0 ? (
            <EmptyState icon={FileText} title="No matching cases">Adjust the filters or register a new case file.</EmptyState>
          ) : (
            <div className="table-scroll">
              <table>
                <caption className="sr-only">Case files, page {list.page + 1}</caption>
                <thead>
                  <tr>
                    <th scope="col">Case #</th>
                    <th scope="col">Title</th>
                    <th scope="col">Crime category</th>
                    <th scope="col">Incident date</th>
                    <th scope="col">Officer</th>
                    <th scope="col">Priority</th>
                    <th scope="col">Status</th>
                    <th scope="col"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {list.rows.map((c) => (
                    <tr key={c.id} className="row-link" onClick={() => navigate(`/cases/${c.id}`)}>
                      <td className="td-mono">{c.case_number}</td>
                      <td className="td-primary">{c.title}</td>
                      <td>{c.crime_type || 'Unclassified'}</td>
                      <td className="td-date">{formatDate(c.incident_date)}</td>
                      <td>{c.assigned_officer?.full_name || <span className="td-sub">Unassigned</span>}</td>
                      <td><PriorityBadge priority={c.priority} /></td>
                      <td><StatusBadge status={c.status} /></td>
                      <td style={{ textAlign: 'right' }}>
                        <Link className="btn btn-secondary btn-sm" to={`/cases/${c.id}`} onClick={(e) => e.stopPropagation()}
                          aria-label={`Open case ${c.case_number}`}>
                          Open <ChevronRight size={11} aria-hidden="true" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {!list.loading && !list.error && list.total > 0 && (
          <Pagination page={list.page} pageSize={list.pageSize} total={list.total} onPageChange={list.setPage} label="cases" />
        )}
      </div>

      {creating && (
        <CreateCaseModal onClose={() => setCreating(false)} onCreated={(created) => { setCreating(false); navigate(`/cases/${created.id}`); }} />
      )}
    </div>
  );
}

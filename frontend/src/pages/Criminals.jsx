import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { AlertTriangle, Eye, Plus, Search, Shield } from 'lucide-react';
import { criminalPhotoUrl, criminalsAPI, getErrorMessage } from '../services/api';
import { getFieldErrors } from '../utils/errors';
import { CRIME_TYPES, GENDERS, THREAT_LEVELS } from '../utils/constants';
import { formatDate, todayInputValue } from '../utils/format';
import { usePagedList } from '../utils/usePagedList';
import { EmptyState, ErrorState, FieldError, LoadingState, Modal, Pagination } from '../components/ui';
import OffenderQuickView from '../components/OffenderQuickView';

const PAGE_SIZE = 25;
const AVATAR_TONES = ['indigo', 'violet', 'sky', 'emerald', 'amber', 'rose'];
const EMPTY_FORM = {
  first_name: '', last_name: '', alias: '', date_of_birth: '', gender: '', nationality: '',
  crime_type: '', prior_convictions: 0, threat_level: 'low', is_wanted: false, is_incarcerated: false,
};

function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function Avatar({ criminal }) {
  const [failed, setFailed] = useState(false);
  const initials = `${criminal.first_name?.[0] || ''}${criminal.last_name?.[0] || ''}`.toUpperCase();
  if (criminal.photo_sha256 && !failed) {
    return (
      <img className="person-avatar person-avatar-photo" src={criminalPhotoUrl(criminal.id, criminal.photo_sha256)} alt=""
        loading="lazy" onError={() => setFailed(true)} />
    );
  }
  return <span className={`person-avatar tone-${AVATAR_TONES[criminal.id % AVATAR_TONES.length]}`} aria-hidden="true">{initials}</span>;
}

function StatusPill({ criminal }) {
  if (criminal.is_wanted) return <span className="badge badge-red">Wanted</span>;
  if (criminal.is_incarcerated) return <span className="badge badge-gray">Incarcerated</span>;
  return <span className="badge badge-blue">On record</span>;
}

function CreateCriminalModal({ onClose, onCreated }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  // Live duplicate check, tagged with the names it was run for; a 409 on save replaces it.
  const [liveCheck, setLiveCheck] = useState({ key: '', list: [] });
  const [confirmedDuplicates, setDuplicates] = useState(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const first = useDebounced(form.first_name.trim());
  const last = useDebounced(form.last_name.trim());
  const dob = useDebounced(form.date_of_birth);

  const checkKey = first.length < 2 || last.length < 2 ? '' : JSON.stringify([first, last, dob]);
  useEffect(() => {
    if (!checkKey) return undefined;
    let cancelled = false;
    criminalsAPI.checkDuplicate({ first_name: first, last_name: last, date_of_birth: dob || undefined })
      .then((res) => { if (!cancelled) setLiveCheck({ key: checkKey, list: res.data.duplicates || [] }); })
      .catch(() => { if (!cancelled) setLiveCheck({ key: checkKey, list: [] }); });
    return () => { cancelled = true; };
  }, [checkKey, first, last, dob]);
  const duplicates = confirmedDuplicates ?? (checkKey && liveCheck.key === checkKey ? liveCheck.list : []);

  const set = (key) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [key]: value }));
    setFieldErrors((errs) => ({ ...errs, [key]: undefined }));
    if (['first_name', 'last_name', 'date_of_birth'].includes(key)) setDuplicates(null);
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setFieldErrors({});
    const payload = {
      ...form,
      prior_convictions: Number(form.prior_convictions) || 0,
      date_of_birth: form.date_of_birth ? `${form.date_of_birth}T00:00:00Z` : null,
      gender: form.gender || null,
      crime_type: form.crime_type || null,
      acknowledge_possible_duplicate: acknowledged,
    };
    try {
      const res = await criminalsAPI.create(payload);
      toast.success(`Record ${res.data.crn} created.`);
      onCreated(res.data);
    } catch (err) {
      if (err.response?.status === 409 && err.response.data?.detail?.duplicates) {
        setDuplicates(err.response.data.detail.duplicates.map((d) => ({
          id: d.id, crn: d.crn, first_name: d.name, last_name: '', match_score: d.match_score,
        })));
        setError('A very similar record already exists. Check it, then confirm below if this is a different person.');
      } else {
        setFieldErrors(getFieldErrors(err));
        setError(getErrorMessage(err, 'Could not create the record.'));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Register offender record" onClose={onClose} busy={saving} maxWidth={620}>
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          {duplicates.length > 0 && (
            <div className="alert alert-warning" role="status" style={{ alignItems: 'flex-start' }}>
              <AlertTriangle size={14} aria-hidden="true" style={{ marginTop: 2 }} />
              <div>
                <strong>Possible existing record{duplicates.length > 1 ? 's' : ''}:</strong>
                <ul style={{ margin: '4px 0 6px 16px' }}>
                  {duplicates.slice(0, 5).map((d) => (
                    <li key={d.id}>
                      <Link to={`/criminals/${d.id}`} target="_blank" rel="noreferrer">
                        {`${d.first_name} ${d.last_name}`.trim()} ({d.crn})
                      </Link>
                    </li>
                  ))}
                </ul>
                <label style={{ display: 'flex', gap: 6, alignItems: 'center', color: 'var(--text-primary)' }}>
                  <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
                  I have checked these; this is a different person.
                </label>
              </div>
            </div>
          )}

          <div className="form-grid">
            <div className="form-group">
              <label className="form-label" htmlFor="c-first">First name *</label>
              <input id="c-first" className="form-control" required maxLength={50} value={form.first_name} onChange={set('first_name')}
                aria-invalid={!!fieldErrors.first_name} aria-describedby="c-first-err" />
              <FieldError id="c-first-err">{fieldErrors.first_name}</FieldError>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="c-last">Last name *</label>
              <input id="c-last" className="form-control" required maxLength={50} value={form.last_name} onChange={set('last_name')}
                aria-invalid={!!fieldErrors.last_name} aria-describedby="c-last-err" />
              <FieldError id="c-last-err">{fieldErrors.last_name}</FieldError>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="c-dob">Date of birth</label>
              <input id="c-dob" className="form-control" type="date" max={todayInputValue()} min="1900-01-01"
                value={form.date_of_birth} onChange={set('date_of_birth')} />
              <FieldError>{fieldErrors.date_of_birth}</FieldError>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="c-gender">Gender</label>
              <select id="c-gender" className="form-select" value={form.gender} onChange={set('gender')}>
                <option value="">Not recorded</option>
                {GENDERS.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="c-alias">Known aliases</label>
              <input id="c-alias" className="form-control" maxLength={200} value={form.alias} onChange={set('alias')} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="c-nat">Nationality</label>
              <input id="c-nat" className="form-control" maxLength={50} value={form.nationality} onChange={set('nationality')} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="c-crime">Primary offence</label>
              <select id="c-crime" className="form-select" value={form.crime_type} onChange={set('crime_type')}>
                <option value="">Not classified</option>
                {CRIME_TYPES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="c-prior">Prior convictions</label>
              <input id="c-prior" className="form-control" type="number" min={0} max={100} value={form.prior_convictions}
                onChange={set('prior_convictions')} />
              <FieldError>{fieldErrors.prior_convictions}</FieldError>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="c-threat">Threat level (officer assessment)</label>
              <select id="c-threat" className="form-select" value={form.threat_level} onChange={set('threat_level')}>
                {THREAT_LEVELS.map((t) => <option key={t} value={t}>{t[0].toUpperCase() + t.slice(1)}</option>)}
              </select>
            </div>
            <div className="form-group" style={{ display: 'flex', gap: 16, alignItems: 'center', paddingTop: 22 }}>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input type="checkbox" checked={form.is_wanted} onChange={set('is_wanted')} /> Wanted
              </label>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input type="checkbox" checked={form.is_incarcerated} onChange={set('is_incarcerated')} /> Incarcerated
              </label>
            </div>
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>A Criminal Record Number (CRN) is generated automatically.</p>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving || (duplicates.length > 0 && error && !acknowledged)}>
            {saving ? <><span className="spinner" aria-hidden="true" /> Saving…</> : 'Create record'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default function Criminals() {
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({ crime_type: '', threat_level: '', is_wanted: '', sort: '' });
  const [creating, setCreating] = useState(false);
  // Index into `rows` of the offender shown in the pop-up card.
  const [viewing, setViewing] = useState(null);
  const debouncedSearch = useDebounced(search.trim());
  const list = usePagedList(criminalsAPI.list, { search: debouncedSearch, ...filters }, PAGE_SIZE);
  const { rows, total, page, setPage, loading, error, reload: load } = list;

  const setFilter = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Offender Records Directory</h1>
          <p className="page-subtitle">{total.toLocaleString()} record{total === 1 ? '' : 's'} match the current filters</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} aria-hidden="true" /> Register record
        </button>
      </div>

      <div className="table-container">
        <div className="table-toolbar" role="search">
          <div className="search-box">
            <Search size={13} aria-hidden="true" />
            <label htmlFor="criminal-search" className="sr-only">Search records</label>
            <input id="criminal-search" className="form-control" type="search" placeholder="Search name, alias, CRN, offence…"
              value={search} onChange={(e) => setSearch(e.target.value)} maxLength={100} />
          </div>
          <div className="toolbar-filters">
            <label className="sr-only" htmlFor="f-crime">Offence</label>
            <select id="f-crime" className="form-select" value={filters.crime_type} onChange={setFilter('crime_type')}>
              <option value="">All offences</option>
              {CRIME_TYPES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <label className="sr-only" htmlFor="f-threat">Threat level</label>
            <select id="f-threat" className="form-select" value={filters.threat_level} onChange={setFilter('threat_level')}>
              <option value="">All threat levels</option>
              {THREAT_LEVELS.map((t) => <option key={t} value={t}>{t[0].toUpperCase() + t.slice(1)}</option>)}
            </select>
            <label className="sr-only" htmlFor="f-wanted">Wanted status</label>
            <select id="f-wanted" className="form-select" value={filters.is_wanted} onChange={setFilter('is_wanted')}>
              <option value="">Any status</option>
              <option value="true">Wanted only</option>
              <option value="false">Not wanted</option>
            </select>
            <label className="sr-only" htmlFor="f-sort">Sort by</label>
            <select id="f-sort" className="form-select" value={filters.sort} onChange={setFilter('sort')}>
              <option value="">Newest first</option>
              <option value="last_name">Last name A–Z</option>
              <option value="-prior_convictions">Most prior convictions</option>
              <option value="crn">CRN</option>
            </select>
          </div>
        </div>

        {loading ? <LoadingState label="Loading records…" />
          : error ? <ErrorState message={error} onRetry={load} />
          : rows.length === 0 ? (
            <EmptyState icon={Shield} title="No matching records">Adjust the search or filters, or register a new record.</EmptyState>
          ) : (
            <div className="table-scroll">
              <table>
                <caption className="sr-only">Offender records, page {page + 1}</caption>
                <thead>
                  <tr>
                    <th scope="col">CRN</th>
                    <th scope="col">Name</th>
                    <th scope="col">Primary offence</th>
                    <th scope="col">Threat level</th>
                    <th scope="col">Status</th>
                    <th scope="col">Registered</th>
                    <th scope="col"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c, i) => (
                    <tr key={c.id} className="row-clickable" onClick={() => setViewing(i)}>
                      <td className="td-mono">{c.crn}</td>
                      <td>
                        <div className="person-cell">
                          <Avatar criminal={c} />
                          <div>
                            <button type="button" className="person-link td-primary" aria-haspopup="dialog"
                              onClick={(e) => { e.stopPropagation(); setViewing(i); }}>
                              {c.first_name} {c.last_name}
                            </button>
                            {c.alias && <div className="td-sub">aka {c.alias}</div>}
                          </div>
                        </div>
                      </td>
                      <td>{c.crime_type || 'Not classified'}</td>
                      <td><span className={`badge risk-${c.threat_level || 'low'}`}>{c.threat_level || 'low'}</span></td>
                      <td><StatusPill criminal={c} /></td>
                      <td className="td-date">{formatDate(c.created_at)}</td>
                      <td style={{ textAlign: 'right' }}>
                        <Link to={`/criminals/${c.id}`} className="btn btn-secondary btn-sm" onClick={(e) => e.stopPropagation()} aria-label={`Open record for ${c.first_name} ${c.last_name}`}>
                          <Eye size={12} aria-hidden="true" /> Open
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {!loading && !error && total > 0 && (
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
        )}
      </div>

      {viewing !== null && rows[viewing] && (
        <OffenderQuickView rows={rows} index={viewing} onIndexChange={setViewing} onClose={() => setViewing(null)} />
      )}

      {creating && (
        <CreateCriminalModal onClose={() => setCreating(false)} onCreated={() => { setCreating(false); setPage(0); load(); }} />
      )}
    </div>
  );
}

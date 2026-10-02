import { useState } from 'react';
import toast from 'react-hot-toast';
import { Filter, RotateCcw, ShieldCheck } from 'lucide-react';
import { adminAPI, getErrorMessage } from '../services/api';
import { ErrorState, LoadingState, Pagination } from '../components/ui';
import { formatDate } from '../utils/format';
import { usePagedList } from '../utils/usePagedList';

const ACTION_BADGE = (action = '') => {
  if (action.includes('FAILED') || action.includes('BLOCKED')) return 'badge-red';
  if (action.includes('LOGIN')) return 'badge-green';
  if (action.includes('DELETE')) return 'badge-red';
  if (action.includes('CREATE') || action.includes('ADDED')) return 'badge-blue';
  if (action.includes('UPDATE') || action.includes('CHANGED')) return 'badge-amber';
  if (action.includes('AI') || action.includes('MODEL')) return 'badge-purple';
  return 'badge-gray';
};
const EMPTY = { user_id: '', action: '', resource_type: '', status: '', request_id: '', date_from: '', date_to: '' };

export default function AdminAudit() {
  const [filters, setFilters] = useState(EMPTY);
  const [applied, setApplied] = useState({});
  const [verification, setVerification] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const list = usePagedList(adminAPI.auditLogs, applied, 25);

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));
  const apply = (e) => {
    e.preventDefault();
    setApplied({ ...filters, date_to: filters.date_to ? `${filters.date_to}T23:59:59` : '' });
  };

  const verify = async () => {
    setVerifying(true);
    try {
      const res = await adminAPI.verifyAuditLogs();
      setVerification(res.data);
      if (res.data.intact) toast.success(`All ${res.data.checked} audit entries verified.`);
      else toast.error(`${res.data.tampered_count} audit entries failed verification.`);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Verification failed.'));
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit Trail</h1>
          <p className="page-subtitle">Append-only, tamper-evident log of security-relevant activity · {list.total.toLocaleString()} matching entries</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={verify} disabled={verifying}>
          <ShieldCheck size={14} aria-hidden="true" /> {verifying ? 'Verifying…' : 'Verify integrity'}
        </button>
      </div>

      {verification && (
        <div className={`alert ${verification.intact ? 'alert-info' : 'alert-error'}`} role="status">
          {verification.intact
            ? `Integrity verified: ${verification.checked} entries checked, ${verification.unsigned_legacy_entries} legacy entries predate signing.`
            : `Tampering detected in ${verification.tampered_count} entr${verification.tampered_count === 1 ? 'y' : 'ies'} (IDs ${verification.tampered_entry_ids.join(', ')}). Preserve evidence and follow the incident procedure.`}
        </div>
      )}

      <form onSubmit={apply} className="filter-bar" aria-label="Filter audit entries">
        <div><label className="form-label" htmlFor="a-user">User ID</label>
          <input id="a-user" className="form-control" inputMode="numeric" value={filters.user_id} onChange={set('user_id')} /></div>
        <div><label className="form-label" htmlFor="a-action">Action contains</label>
          <input id="a-action" className="form-control" value={filters.action} onChange={set('action')} /></div>
        <div><label className="form-label" htmlFor="a-resource">Resource type</label>
          <input id="a-resource" className="form-control" value={filters.resource_type} onChange={set('resource_type')} /></div>
        <div><label className="form-label" htmlFor="a-status">Outcome</label>
          <select id="a-status" className="form-select" value={filters.status} onChange={set('status')}>
            <option value="">Any</option><option value="success">Success</option><option value="failure">Failure</option>
          </select></div>
        <div><label className="form-label" htmlFor="a-request">Request ID</label>
          <input id="a-request" className="form-control mono" value={filters.request_id} onChange={set('request_id')} /></div>
        <div><label className="form-label" htmlFor="a-from">From</label>
          <input id="a-from" className="form-control" type="date" value={filters.date_from} onChange={set('date_from')} /></div>
        <div><label className="form-label" htmlFor="a-to">To</label>
          <input id="a-to" className="form-control" type="date" value={filters.date_to} onChange={set('date_to')} /></div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <button className="btn btn-primary btn-sm" type="submit"><Filter size={14} aria-hidden="true" /> Apply</button>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => { setFilters(EMPTY); setApplied({}); }}>
            <RotateCcw size={14} aria-hidden="true" /> Reset
          </button>
        </div>
      </form>

      <div className="table-container">
        {list.loading ? <LoadingState label="Loading audit entries…" />
          : list.error ? <ErrorState message={list.error} onRetry={list.reload} /> : (
            <div className="table-scroll">
              <table>
                <caption className="sr-only">Audit entries</caption>
                <thead><tr><th scope="col">Time</th><th scope="col">Actor</th><th scope="col">Action</th><th scope="col">Resource</th><th scope="col">Outcome</th><th scope="col">Reason / details</th><th scope="col">Request</th></tr></thead>
                <tbody>
                  {list.rows.length === 0 ? (
                    <tr><td colSpan={7} style={{ textAlign: 'center', padding: 32 }} className="td-sub">No entries match the filters.</td></tr>
                  ) : list.rows.map((log) => (
                    <tr key={log.id}>
                      <td className="td-mono">{formatDate(log.created_at, { withTime: true })}</td>
                      <td><div className="td-primary">{log.username || 'system'}</div><div className="td-sub">{log.role || '—'}{log.ip_address ? ` · ${log.ip_address}` : ''}</div></td>
                      <td><span className={`badge ${ACTION_BADGE(log.action)}`}>{log.action}</span></td>
                      <td>{log.resource_type || '—'}{log.resource_id != null ? ` #${log.resource_id}` : ''}</td>
                      <td><span className={`badge ${log.status === 'success' ? 'badge-green' : 'badge-red'}`}>{log.status}</span></td>
                      <td style={{ maxWidth: 320 }}>
                        {log.reason && <div>{log.reason}</div>}
                        {log.details && Object.keys(log.details).length > 0 && (
                          <details><summary className="td-sub">Details</summary><pre className="custody-log">{JSON.stringify(log.details, null, 2)}</pre></details>
                        )}
                      </td>
                      <td className="td-mono td-sub" title={log.request_id || ''}>{log.request_id ? `${log.request_id.slice(0, 8)}…` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {!list.loading && !list.error && list.total > 0 && (
          <Pagination page={list.page} pageSize={list.pageSize} total={list.total} onPageChange={list.setPage} label="entries" />
        )}
      </div>
    </div>
  );
}

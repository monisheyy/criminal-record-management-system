import { useState, useEffect, useCallback } from 'react';
import { Activity, Clock, User, FileText, ChevronLeft, ChevronRight, Shield } from 'lucide-react';
import toast from 'react-hot-toast';
import { adminAPI } from '../services/api';

const ACTION_BADGE = (action) => {
  if (action?.includes('LOGIN'))   return 'badge-green';
  if (action?.includes('DELETE'))  return 'badge-red';
  if (action?.includes('CREATE'))  return 'badge-blue';
  if (action?.includes('UPDATE'))  return 'badge-amber';
  if (action?.includes('AI'))      return 'badge-purple';
  return 'badge-gray';
};

const LIMIT = 20;

export default function AdminAudit() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  const fetchLogs = useCallback(() => {
    setLoading(true);
    adminAPI.auditLogs({ skip: page * LIMIT, limit: LIMIT + 1 })
      .then(r => {
        const data = r.data || [];
        setHasMore(data.length > LIMIT);
        setLogs(data.slice(0, LIMIT));
      })
      .catch(() => toast.error('Failed to fetch audit logs.'))
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">System Audit Trail</h1>
          <p className="page-subtitle">Immutable security log of all user activities and system transactions</p>
        </div>
      </div>

      <div className="table-container">
        {loading ? (
          <div className="empty-state" style={{ padding: '40px' }}>
            <div className="spinner" style={{ marginBottom: 12 }} />
            <div className="empty-state-title">Loading audit logs...</div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Timestamp (UTC)</th>
                <th>Actor User</th>
                <th>Action Code</th>
                <th>Resource Type</th>
                <th>Resource ID</th>
                <th>IP Address</th>
                <th>Event Metadata</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>
                    No audit records registered yet.
                  </td>
                </tr>
              ) : logs.map((log) => (
                <tr key={log.id}>
                  <td className="td-mono" style={{ fontSize: '0.78rem' }}>
                    <Clock size={11} style={{ marginRight: 4 }} />
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td>
                    <div className="td-primary">{log.username || 'System'}</div>
                    {log.user_id && <div className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>ID #{log.user_id}</div>}
                  </td>
                  <td>
                    <span className={`badge ${ACTION_BADGE(log.action)}`}>{log.action}</span>
                  </td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{log.resource_type || '—'}</td>
                  <td className="td-mono">{log.resource_id ?? '—'}</td>
                  <td className="td-mono" style={{ fontSize: '0.78rem' }}>{log.ip_address || '127.0.0.1'}</td>
                  <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {log.details ? JSON.stringify(log.details) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination Bar */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 10, marginTop: 12 }}>
        <button className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
          <ChevronLeft size={14} /> Previous
        </button>
        <span className="mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Page {page + 1}</span>
        <button className="btn btn-secondary btn-sm" disabled={!hasMore} onClick={() => setPage(p => p + 1)}>
          Next <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}

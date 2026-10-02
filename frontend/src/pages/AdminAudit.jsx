import { useState, useEffect, useCallback } from 'react';
import { Clock, ChevronLeft, ChevronRight, Filter, RotateCcw } from 'lucide-react';
import toast from 'react-hot-toast';
import { adminAPI } from '../services/api';

const ACTION_BADGE = (action) => {
  if (action?.includes('LOGIN')) return 'badge-green';
  if (action?.includes('DELETE')) return 'badge-red';
  if (action?.includes('CREATE') || action?.includes('ADDED')) return 'badge-blue';
  if (action?.includes('UPDATE') || action?.includes('CHANGED')) return 'badge-amber';
  if (action?.includes('AI')) return 'badge-purple';
  return 'badge-gray';
};
const LIMIT = 20;

export default function AdminAudit() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [filters, setFilters] = useState({ user_id: '', action: '', resource_type: '', status: '', date_from: '', date_to: '' });
  const [applied, setApplied] = useState({});

  const fetchLogs = useCallback(() => {
    setLoading(true);
    const params = { skip: page * LIMIT, limit: LIMIT + 1, ...applied };
    Object.keys(params).forEach(k => { if (params[k] === '' || params[k] == null) delete params[k]; });
    adminAPI.auditLogs(params)
      .then(r => { const data = r.data || []; setHasMore(data.length > LIMIT); setLogs(data.slice(0, LIMIT)); })
      .catch(() => toast.error('Failed to fetch audit logs.'))
      .finally(() => setLoading(false));
  }, [page, applied]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);
  const applyFilters = (e) => { e.preventDefault(); setPage(0); setApplied({ ...filters }); };
  const resetFilters = () => { const empty = { user_id: '', action: '', resource_type: '', status: '', date_from: '', date_to: '' }; setFilters(empty); setApplied({}); setPage(0); };

  return (
    <div>
      <div className="page-header"><div><h1 className="page-title">System Audit Trail</h1><p className="page-subtitle">Administrator-only audit trail of security-sensitive activities and system transactions</p></div></div>

      <form onSubmit={applyFilters} style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))', gap:10, marginBottom:16, padding:14, border:'1px solid var(--border-color)', borderRadius:8 }}>
        <input className="input" placeholder="User ID" value={filters.user_id} onChange={e=>setFilters({...filters,user_id:e.target.value})} inputMode="numeric" />
        <input className="input" placeholder="Action" value={filters.action} onChange={e=>setFilters({...filters,action:e.target.value})} />
        <input className="input" placeholder="Resource" value={filters.resource_type} onChange={e=>setFilters({...filters,resource_type:e.target.value})} />
        <select className="input" value={filters.status} onChange={e=>setFilters({...filters,status:e.target.value})}><option value="">All statuses</option><option value="success">Success</option><option value="failure">Failure</option></select>
        <input className="input" type="date" title="From date" value={filters.date_from} onChange={e=>setFilters({...filters,date_from:e.target.value})} />
        <input className="input" type="date" title="To date" value={filters.date_to} onChange={e=>setFilters({...filters,date_to:e.target.value ? `${e.target.value}T23:59:59` : ''})} />
        <div style={{display:'flex',gap:8,alignItems:'center'}}><button className="btn btn-primary btn-sm" type="submit"><Filter size={14}/> Filter</button><button className="btn btn-secondary btn-sm" type="button" onClick={resetFilters}><RotateCcw size={14}/> Reset</button></div>
      </form>

      <div className="table-container">
        {loading ? <div className="empty-state" style={{padding:'40px'}}><div className="spinner" style={{marginBottom:12}}/><div className="empty-state-title">Loading audit logs...</div></div> : (
          <table><thead><tr><th>Timestamp (UTC)</th><th>Actor</th><th>Role</th><th>Action</th><th>Resource</th><th>Status</th><th>IP</th><th>Metadata</th></tr></thead>
          <tbody>{logs.length===0 ? <tr><td colSpan={8} style={{textAlign:'center',color:'var(--text-muted)',padding:32}}>No audit records match the selected filters.</td></tr> : logs.map(log => <tr key={log.id}>
            <td className="td-mono" style={{fontSize:'.78rem'}}><Clock size={11} style={{marginRight:4}}/>{new Date(log.created_at).toLocaleString()}</td>
            <td><div className="td-primary">{log.username || 'System'}</div>{log.user_id && <div className="mono" style={{fontSize:'.72rem',color:'var(--text-muted)'}}>ID #{log.user_id}</div>}</td>
            <td style={{fontSize:'.75rem'}}>{log.role || 'system'}</td>
            <td><span className={`badge ${ACTION_BADGE(log.action)}`}>{log.action}</span></td>
            <td style={{fontSize:'.8rem',color:'var(--text-secondary)'}}>{log.resource_type || '—'}{log.resource_id != null ? ` #${log.resource_id}` : ''}</td>
            <td><span className={`badge ${log.status === 'success' ? 'badge-green' : 'badge-red'}`}>{log.status}</span></td>
            <td className="td-mono" style={{fontSize:'.75rem'}}>{log.ip_address || '—'}</td>
            <td style={{fontSize:'.72rem',color:'var(--text-muted)',maxWidth:260,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}} title={log.reason || ''}>{log.reason || (log.details ? JSON.stringify(log.details) : '—')}</td>
          </tr>)}</tbody></table>
        )}
      </div>
      <div style={{display:'flex',justifyContent:'flex-end',alignItems:'center',gap:10,marginTop:12}}><button className="btn btn-secondary btn-sm" disabled={page===0} onClick={()=>setPage(p=>p-1)}><ChevronLeft size={14}/> Previous</button><span className="mono" style={{fontSize:'.8rem',color:'var(--text-muted)'}}>Page {page+1}</span><button className="btn btn-secondary btn-sm" disabled={!hasMore} onClick={()=>setPage(p=>p+1)}>Next <ChevronRight size={14}/></button></div>
    </div>
  );
}

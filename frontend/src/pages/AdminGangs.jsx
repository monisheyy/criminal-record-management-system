import { useState } from 'react';
import { Plus, Edit2, Trash2, X, Database } from 'lucide-react';
import toast from 'react-hot-toast';
import { gangsAPI, getErrorMessage } from '../services/api';
import { ConfirmDialog, ErrorState } from '../components/ui';
import { useApiQuery } from '../utils/useApiQuery';

const THREAT_LEVELS = ['low', 'medium', 'high', 'critical'];

const EMPTY_FORM = {
  name: '', alias: '', territory: '', threat_level: 'medium',
  known_activities: '', member_count: '', is_active: true,
};

export default function AdminGangs() {
  const { data, loading, error, reload: fetchGangs } = useApiQuery(gangsAPI.list, { fallbackError: 'Failed to load gangs.' });
  const gangs = data || [];
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);


  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setModalOpen(true);
  };

  const openEdit = (gang) => {
    setEditing(gang);
    setForm({
      name: gang.name,
      alias: gang.alias || '',
      territory: gang.territory || '',
      threat_level: gang.threat_level || 'medium',
      known_activities: gang.known_activities || '',
      member_count: gang.member_count ?? '',
      is_active: gang.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        member_count: form.member_count ? Number(form.member_count) : 0,
      };
      if (editing) {
        await gangsAPI.update(editing.id, payload);
        toast.success('Gang organization updated.');
      } else {
        await gangsAPI.create(payload);
        toast.success('Gang organization registered.');
      }
      setModalOpen(false);
      fetchGangs();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to save gang.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (gang) => setPendingDelete(gang);

  const confirmDelete = async () => {
    try {
      await gangsAPI.delete(pendingDelete.id);
      toast.success('Gang record deleted.');
      fetchGangs();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to delete gang.'));
    }
    setPendingDelete(null);
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Gang Intelligence Management</h1>
          <p className="page-subtitle">{gangs.length} tracked criminal syndicates and organized crime rings</p>
        </div>
        <button className="btn btn-primary" onClick={openCreate}>
          <Plus size={15} /> Add Gang Record
        </button>
      </div>

      <div className="table-container">
        {loading ? (
          <div className="empty-state" style={{ padding: '40px' }}>
            <div className="spinner" style={{ marginBottom: 12 }} />
            <div className="empty-state-title">Loading gang database...</div>
          </div>
        ) : error ? (
          <ErrorState message={error} onRetry={fetchGangs} />
        ) : gangs.length === 0 ? (
          <div className="empty-state">
            <Database size={32} style={{ opacity: 0.3 }} />
            <div className="empty-state-title">No Gangs Registered</div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Register criminal organizations to track intelligence and syndicate members.
            </p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Organization</th>
                <th>Territory / Hub</th>
                <th>Threat Level</th>
                <th>Est. Members</th>
                <th>Known Operations</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {gangs.map(gang => (
                <tr key={gang.id}>
                  <td>
                    <div className="td-primary">{gang.name}</div>
                    {gang.alias && <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>aka "{gang.alias}"</div>}
                  </td>
                  <td>{gang.territory || 'Unmapped'}</td>
                  <td>
                    <span className={`badge ${gang.threat_level === 'critical' || gang.threat_level === 'high' ? 'badge-red' : gang.threat_level === 'medium' ? 'badge-amber' : 'badge-green'}`}>
                      {gang.threat_level?.toUpperCase()}
                    </span>
                  </td>
                  <td className="td-mono">{gang.member_count ?? '—'}</td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {gang.known_activities || 'N/A'}
                  </td>
                  <td>
                    {gang.is_active ? <span className="badge badge-green">● Active</span> : <span className="badge badge-gray">● Inactive</span>}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <button className="btn btn-secondary btn-icon" onClick={() => openEdit(gang)}>
                        <Edit2 size={13} />
                      </button>
                      <button className="btn btn-danger btn-icon" onClick={() => handleDelete(gang)}>
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {modalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <span className="modal-title">{editing ? 'Edit Gang Record' : 'Register Gang Organization'}</span>
              <button className="btn btn-ghost btn-icon" onClick={() => setModalOpen(false)}><X size={16} /></button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Gang / Syndicate Name *</label>
                  <input className="form-control" type="text" required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Street Alias</label>
                    <input className="form-control" type="text" value={form.alias} onChange={e => setForm(f => ({ ...f, alias: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Primary Territory</label>
                    <input className="form-control" type="text" value={form.territory} onChange={e => setForm(f => ({ ...f, territory: e.target.value }))} />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Threat Level *</label>
                    <select className="form-select" value={form.threat_level} onChange={e => setForm(f => ({ ...f, threat_level: e.target.value }))}>
                      {THREAT_LEVELS.map(t => (
                        <option key={t} value={t}>{t.toUpperCase()}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Estimated Members</label>
                    <input className="form-control" type="number" min={0} value={form.member_count} onChange={e => setForm(f => ({ ...f, member_count: e.target.value }))} />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Known Operations & Activities</label>
                  <textarea className="form-control" rows={3} value={form.known_activities} onChange={e => setForm(f => ({ ...f, known_activities: e.target.value }))} placeholder="e.g. Arms trafficking, extortion..." />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? <><span className="spinner" /> Saving...</> : (editing ? 'Update Gang' : 'Create Gang')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {pendingDelete && (
        <ConfirmDialog title={`Delete "${pendingDelete.name}"?`} confirmLabel="Delete" danger
          message="Gangs referenced by criminal records or AI outputs cannot be deleted; mark them inactive instead."
          onCancel={() => setPendingDelete(null)} onConfirm={confirmDelete} />
      )}
    </div>
  );
}

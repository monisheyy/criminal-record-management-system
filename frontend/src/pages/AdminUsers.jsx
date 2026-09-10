import { useState, useEffect, useCallback } from 'react';
import { UserPlus, Edit2, Trash2, X, Shield, User, CheckCircle, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { adminAPI } from '../services/api';

const ROLES = [
  { value: 'admin', label: 'Administrator', badge: 'badge-red' },
  { value: 'investigating_officer', label: 'Investigating Officer', badge: 'badge-blue' },
  { value: 'record_clerk', label: 'Record Clerk', badge: 'badge-gray' },
];

const EMPTY_FORM = {
  username: '', email: '', full_name: '',
  password: '', role: 'record_clerk',
  badge_number: '', department: '',
};

export default function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const fetchUsers = useCallback(() => {
    setLoading(true);
    adminAPI.users()
      .then(r => setUsers(r.data || []))
      .catch(() => toast.error('Failed to load user directory.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setModalOpen(true);
  };

  const openEdit = (u) => {
    setEditing(u);
    setForm({
      username: u.username,
      email: u.email,
      full_name: u.full_name,
      password: '',
      role: u.role,
      badge_number: u.badge_number || '',
      department: u.department || '',
    });
    setModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        const payload = { ...form };
        if (!payload.password) delete payload.password;
        await adminAPI.updateUser(editing.id, payload);
        toast.success('User details updated.');
      } else {
        await adminAPI.createUser(form);
        toast.success('New user account created.');
      }
      setModalOpen(false);
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save user account.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (u) => {
    if (!window.confirm(`Permanently remove user "${u.username}"?`)) return;
    try {
      await adminAPI.deleteUser(u.id);
      toast.success('User account removed.');
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete user.');
    }
  };

  const handleToggleActive = async (u) => {
    try {
      await adminAPI.updateUser(u.id, { is_active: !u.is_active });
      toast.success(`User ${u.is_active ? 'deactivated' : 'activated'}.`);
      fetchUsers();
    } catch {
      toast.error('Failed to change user status.');
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">User Account Directory</h1>
          <p className="page-subtitle">{users.length} system users registered with RBAC permissions</p>
        </div>
        <button className="btn btn-primary" onClick={openCreate}>
          <UserPlus size={15} /> Add User Account
        </button>
      </div>

      <div className="table-container">
        {loading ? (
          <div className="empty-state" style={{ padding: '40px' }}>
            <div className="spinner" style={{ marginBottom: 12 }} />
            <div className="empty-state-title">Loading system accounts...</div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>User Identity</th>
                <th>Assigned Role</th>
                <th>Badge / Dept</th>
                <th>Account Status</th>
                <th>Created Date</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => {
                const roleBadge = ROLES.find(r => r.value === u.role)?.badge || 'badge-gray';
                const roleLabel = ROLES.find(r => r.value === u.role)?.label || u.role;
                return (
                  <tr key={u.id}>
                    <td>
                      <div className="td-primary">{u.full_name}</div>
                      <div className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        @{u.username} · {u.email}
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${roleBadge}`}>{roleLabel}</span>
                    </td>
                    <td>
                      {u.badge_number && <div className="mono" style={{ fontSize: '0.78rem' }}>#{u.badge_number}</div>}
                      {u.department && <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{u.department}</div>}
                      {!u.badge_number && !u.department && '—'}
                    </td>
                    <td>
                      {u.is_active
                        ? <span className="badge badge-green">● Active</span>
                        : <span className="badge badge-red">● Inactive</span>}
                    </td>
                    <td className="mono" style={{ fontSize: '0.78rem' }}>
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        <button className="btn btn-secondary btn-icon" onClick={() => openEdit(u)} title="Edit User">
                          <Edit2 size={13} />
                        </button>
                        <button className="btn btn-secondary btn-icon" onClick={() => handleToggleActive(u)} title={u.is_active ? 'Deactivate' : 'Activate'}>
                          {u.is_active ? <XCircle size={13} style={{ color: 'var(--status-amber)' }} /> : <CheckCircle size={13} style={{ color: 'var(--status-emerald)' }} />}
                        </button>
                        <button className="btn btn-danger btn-icon" onClick={() => handleDelete(u)} title="Delete Account">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {modalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <span className="modal-title">{editing ? 'Edit System Account' : 'Register New System User'}</span>
              <button className="btn btn-ghost btn-icon" onClick={() => setModalOpen(false)}><X size={16} /></button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Username *</label>
                    <input className="form-control" type="text" required value={form.username} disabled={!!editing} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Full Name *</label>
                    <input className="form-control" type="text" required value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Email Address *</label>
                  <input className="form-control" type="email" required value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Password {!editing && '*'}</label>
                    <input className="form-control" type="password" required={!editing} placeholder={editing ? 'Leave blank to keep current' : ''} value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">System Role *</label>
                    <select className="form-select" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
                      {ROLES.map(r => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Badge Number</label>
                    <input className="form-control" type="text" value={form.badge_number} onChange={e => setForm(f => ({ ...f, badge_number: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Department / Unit</label>
                    <input className="form-control" type="text" value={form.department} onChange={e => setForm(f => ({ ...f, department: e.target.value }))} />
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? <><span className="spinner" /> Saving...</> : (editing ? 'Update Account' : 'Create Account')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

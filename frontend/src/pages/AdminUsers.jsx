import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { CheckCircle, Edit2, Lock, Trash2, Unlock, UserPlus, XCircle } from 'lucide-react';
import { adminAPI, getErrorMessage } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { ConfirmDialog, ErrorState, FieldHint, LoadingState, Modal } from '../components/ui';
import { PASSWORD_MIN_LENGTH, ROLE_LABELS } from '../utils/constants';
import { formatDate } from '../utils/format';

const ROLE_BADGE = { admin: 'badge-red', investigating_officer: 'badge-blue', record_clerk: 'badge-gray' };
const EMPTY_FORM = { username: '', email: '', full_name: '', password: '', role: 'record_clerk', badge_number: '', department: '' };

const isLocked = (u) => u.locked_until && new Date(u.locked_until) > new Date();

function UserModal({ editing, onClose, onSaved }) {
  const [form, setForm] = useState(editing ? {
    username: editing.username, email: editing.email, full_name: editing.full_name, password: '', role: editing.role,
    badge_number: editing.badge_number || '', department: editing.department || '',
  } : EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      if (editing) {
        const payload = { email: form.email, full_name: form.full_name, role: form.role,
          badge_number: form.badge_number || null, department: form.department || null };
        if (form.password) payload.password = form.password;
        await adminAPI.updateUser(editing.id, payload);
        toast.success(form.password ? 'Account updated. The user must choose a new password at next sign-in.' : 'Account updated.');
      } else {
        await adminAPI.createUser({ ...form, badge_number: form.badge_number || null, department: form.department || null });
        toast.success('Account created. The user must change the temporary password at first sign-in.');
      }
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the account.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={editing ? `Edit ${editing.username}` : 'Create user account'} onClose={onClose} busy={saving}>
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <div className="form-grid">
            <div className="form-group"><label className="form-label" htmlFor="u-username">Username *</label>
              <input id="u-username" className="form-control" required minLength={3} maxLength={50} pattern="[A-Za-z0-9_.\-]{3,50}"
                value={form.username} disabled={!!editing} onChange={set('username')} autoComplete="off" /></div>
            <div className="form-group"><label className="form-label" htmlFor="u-name">Full name *</label>
              <input id="u-name" className="form-control" required minLength={2} maxLength={100} value={form.full_name} onChange={set('full_name')} /></div>
          </div>
          <div className="form-group"><label className="form-label" htmlFor="u-email">Email *</label>
            <input id="u-email" className="form-control" type="email" required value={form.email} onChange={set('email')} /></div>
          <div className="form-grid">
            <div className="form-group"><label className="form-label" htmlFor="u-password">{editing ? 'Reset password' : 'Temporary password *'}</label>
              <input id="u-password" className="form-control" type="password" required={!editing} minLength={PASSWORD_MIN_LENGTH}
                value={form.password} onChange={set('password')} autoComplete="new-password" />
              <FieldHint>{editing ? 'Leave blank to keep. ' : ''}At least {PASSWORD_MIN_LENGTH} characters; the user must replace it at sign-in.</FieldHint></div>
            <div className="form-group"><label className="form-label" htmlFor="u-role">Role *</label>
              <select id="u-role" className="form-select" value={form.role} onChange={set('role')}>
                {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              {editing && editing.role !== form.role && <FieldHint>Changing the role signs the user out everywhere.</FieldHint>}</div>
            <div className="form-group"><label className="form-label" htmlFor="u-badge">Badge number</label>
              <input id="u-badge" className="form-control" maxLength={20} value={form.badge_number} onChange={set('badge_number')} /></div>
            <div className="form-group"><label className="form-label" htmlFor="u-dept">Department / unit</label>
              <input id="u-dept" className="form-control" maxLength={100} value={form.department} onChange={set('department')} /></div>
          </div>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : editing ? 'Save changes' : 'Create account'}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function AdminUsers() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const fetchUsers = useCallback(() => {
    setLoading(true);
    setError('');
    adminAPI.users()
      .then((r) => setUsers(r.data || []))
      .catch((err) => setError(getErrorMessage(err, 'Failed to load users.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const update = async (u, payload, message) => {
    try {
      await adminAPI.updateUser(u.id, payload);
      toast.success(message);
      fetchUsers();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">User Directory</h1>
          <p className="page-subtitle">{users.length} accounts · role-based access control</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setModal({ editing: null })}>
          <UserPlus size={15} aria-hidden="true" /> Create account
        </button>
      </div>

      <div className="table-container">
        {loading ? <LoadingState label="Loading accounts…" />
          : error ? <ErrorState message={error} onRetry={fetchUsers} /> : (
            <div className="table-scroll">
              <table>
                <caption className="sr-only">User accounts</caption>
                <thead><tr><th scope="col">User</th><th scope="col">Role</th><th scope="col">Badge / unit</th><th scope="col">Status</th><th scope="col">Last sign-in</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>
                  {users.map((u) => {
                    const self = u.id === me?.id;
                    return (
                      <tr key={u.id}>
                        <td><div className="td-primary">{u.full_name}{self && <span className="td-sub"> (you)</span>}</div><div className="td-sub mono">@{u.username} · {u.email}</div></td>
                        <td><span className={`badge ${ROLE_BADGE[u.role] || 'badge-gray'}`}>{ROLE_LABELS[u.role] || u.role}</span></td>
                        <td>{u.badge_number || u.department ? <>{u.badge_number && <div className="mono">#{u.badge_number}</div>}<div className="td-sub">{u.department}</div></> : '—'}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {u.is_active ? <span className="badge badge-green">Active</span> : <span className="badge badge-red">Inactive</span>}
                            {isLocked(u) && <span className="badge badge-amber"><Lock size={10} aria-hidden="true" /> Locked</span>}
                            {u.must_change_password && <span className="badge badge-gray">Must change password</span>}
                          </div>
                        </td>
                        <td className="td-mono">{u.last_login_at ? formatDate(u.last_login_at, { withTime: true }) : 'Never'}</td>
                        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <button type="button" className="btn btn-secondary btn-icon" onClick={() => setModal({ editing: u })} aria-label={`Edit ${u.username}`} title="Edit">
                            <Edit2 size={13} aria-hidden="true" />
                          </button>
                          {isLocked(u) && (
                            <button type="button" className="btn btn-secondary btn-icon" onClick={() => update(u, { unlock: true }, 'Account unlocked.')} aria-label={`Unlock ${u.username}`} title="Unlock">
                              <Unlock size={13} aria-hidden="true" />
                            </button>
                          )}
                          {!self && (
                            <button type="button" className="btn btn-secondary btn-icon" title={u.is_active ? 'Deactivate' : 'Activate'}
                              aria-label={`${u.is_active ? 'Deactivate' : 'Activate'} ${u.username}`}
                              onClick={() => (u.is_active ? setConfirm({ type: 'deactivate', user: u }) : update(u, { is_active: true }, 'Account activated.'))}>
                              {u.is_active ? <XCircle size={13} aria-hidden="true" style={{ color: 'var(--status-amber)' }} /> : <CheckCircle size={13} aria-hidden="true" style={{ color: 'var(--status-emerald)' }} />}
                            </button>
                          )}
                          {!self && (
                            <button type="button" className="btn btn-danger btn-icon" onClick={() => setConfirm({ type: 'delete', user: u })} aria-label={`Delete ${u.username}`} title="Delete">
                              <Trash2 size={13} aria-hidden="true" />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
      </div>

      {modal && <UserModal editing={modal.editing} onClose={() => setModal(null)} onSaved={() => { setModal(null); fetchUsers(); }} />}
      {confirm?.type === 'deactivate' && (
        <ConfirmDialog title={`Deactivate ${confirm.user.username}?`} confirmLabel="Deactivate" danger
          message="The user is signed out everywhere immediately and cannot sign in until reactivated. Their records and audit history are kept."
          onCancel={() => setConfirm(null)}
          onConfirm={async () => { await update(confirm.user, { is_active: false }, 'Account deactivated.'); setConfirm(null); }} />
      )}
      {confirm?.type === 'delete' && (
        <ConfirmDialog title={`Delete ${confirm.user.username}?`} confirmLabel="Delete permanently" danger
          message="Accounts referenced by cases, records or audit history cannot be deleted — deactivate them instead. Only unused accounts can be removed."
          onCancel={() => setConfirm(null)}
          onConfirm={async () => {
            try {
              await adminAPI.deleteUser(confirm.user.id);
              toast.success('Account deleted.');
              fetchUsers();
            } catch (err) {
              toast.error(getErrorMessage(err));
            }
            setConfirm(null);
          }} />
      )}
    </div>
  );
}

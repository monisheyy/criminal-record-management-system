import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage, notificationsAPI } from '../services/api';
import { ErrorState, LoadingState } from '../components/ui';
import { formatDate } from '../utils/format';
import toast from 'react-hot-toast';
import { Bell, AlertTriangle, Info, CheckCircle, Siren, User, FileText, CheckCheck } from 'lucide-react';

const TYPE_CONFIG = {
  alert:   { icon: <Siren size={18} />, color: 'var(--status-red)', badgeClass: 'badge-red' },
  warning: { icon: <AlertTriangle size={18} />, color: 'var(--status-amber)', badgeClass: 'badge-amber' },
  info:    { icon: <Info size={18} />, color: 'var(--accent-blue)', badgeClass: 'badge-blue' },
  success: { icon: <CheckCircle size={18} />, color: 'var(--status-emerald)', badgeClass: 'badge-green' },
};

const cfg = (type) => TYPE_CONFIG[type] || TYPE_CONFIG.info;

export default function Alerts() {
  const navigate = useNavigate();

  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchAlerts = useCallback(() => {
    setLoading(true);
    setError('');
    notificationsAPI.list({ limit: 100 })
      .then(r => setAlerts(r.data || []))
      .catch((err) => setError(getErrorMessage(err, 'Failed to load alerts.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const handleMarkRead = async (id) => {
    try {
      await notificationsAPI.markRead(id);
      setAlerts(prev => prev.map(a => a.id === id ? { ...a, is_read: true } : a));
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to mark the alert as read.'));
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationsAPI.markAllRead();
      setAlerts(prev => prev.map(a => ({ ...a, is_read: true })));
      toast.success('All system alerts marked as read.');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to mark alerts as read.'));
    }
  };

  const unreadCount = alerts.filter(a => !a.is_read).length;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Operational System Alerts</h1>
          <p className="page-subtitle">
            {unreadCount > 0
              ? `${unreadCount} unread system operational flag${unreadCount > 1 ? 's' : ''}`
              : 'All notifications read'}
          </p>
        </div>
        <button
          className="btn btn-secondary"
          onClick={handleMarkAllRead}
          disabled={unreadCount === 0 || loading}
        >
          <CheckCheck size={14} /> Mark All Read
        </button>
      </div>

      {loading ? <LoadingState label="Loading alerts…" />
        : error ? <ErrorState message={error} onRetry={fetchAlerts} />
        : alerts.length === 0 ? (
        <div className="empty-state">
          <Bell size={32} style={{ opacity: 0.3 }} />
          <div className="empty-state-title">No Active Alerts</div>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
            System state normal — no active operational flags.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {alerts.map(alert => {
            const { icon, color, badgeClass } = cfg(alert.notification_type);
            return (
              <div
                key={alert.id}
                className="card"
                style={{
                  margin: 0,
                  padding: '14px 18px',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 14,
                  opacity: alert.is_read ? 0.6 : 1,
                  borderColor: alert.is_read ? 'var(--border)' : 'var(--border-strong)',
                }}
              >
                <div style={{ color, flexShrink: 0, marginTop: 2 }} aria-hidden="true">{icon}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                      {!alert.is_read && <span className="sr-only">Unread: </span>}{alert.title}
                    </span>
                    <span className={`badge ${badgeClass}`}>{alert.notification_type}</span>
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 8 }}>
                    {alert.message}
                  </div>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {formatDate(alert.created_at, { withTime: true })}
                    </span>
                    {alert.related_criminal_id && (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => navigate(`/criminals/${alert.related_criminal_id}`)}
                      >
                        <User size={12} /> Inspect Offender Dossier
                      </button>
                    )}
                    {alert.related_case_id && (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => navigate(`/cases/${alert.related_case_id}`)}
                      >
                        <FileText size={12} /> Inspect Case File
                      </button>
                    )}
                  </div>
                </div>
                {!alert.is_read && (
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => handleMarkRead(alert.id)}
                  >
                    Mark Read
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

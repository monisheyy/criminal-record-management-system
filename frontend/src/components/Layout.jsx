import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  Activity, Bell, BookOpen, Brain, CheckCheck, Database, FileText, KeyRound, LayoutDashboard,
  Lock, LogOut, MapPinned, Shield, Siren, Users,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { notificationsAPI } from '../services/api';
import { formatDate } from '../utils/format';
import { ROLE_LABELS } from '../utils/constants';

const ALL = ['admin', 'investigating_officer', 'record_clerk'];
const NAV = [
  { section: 'Overview', links: [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Command Center', roles: ALL },
  ] },
  { section: 'Records', links: [
    { to: '/criminals', icon: Shield, label: 'Offender Directory', roles: ALL },
    { to: '/cases', icon: FileText, label: 'Cases & FIR Files', roles: ALL },
    { to: '/map', icon: MapPinned, label: 'Incident Map', roles: ALL },
  ] },
  { section: 'Decision Support', links: [
    { to: '/ai-predictions', icon: Brain, label: 'AI Predictions (review)', roles: ['admin', 'investigating_officer'] },
    { to: '/alerts', icon: Siren, label: 'Alerts', roles: ALL },
  ] },
  { section: 'Governance', links: [
    { to: '/admin/users', icon: Users, label: 'User Directory', roles: ['admin'] },
    { to: '/admin/gangs', icon: Database, label: 'Gang Register', roles: ['admin'] },
    { to: '/admin/audit', icon: BookOpen, label: 'Audit Trail', roles: ['admin'] },
    { to: '/admin/ai-models', icon: Activity, label: 'Model Governance', roles: ['admin'] },
  ] },
];

const TYPE_CLASS = { alert: 'alert', warning: 'warning', success: 'success' };

function NotificationPanel({ notifications, onMarkRead, onMarkAllRead, onOpen }) {
  return (
    <div className="notification-dropdown" role="dialog" aria-label="Notifications">
      <div className="notif-header">
        <span className="notif-header-title">Notifications</span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onMarkAllRead}>
          <CheckCheck size={13} aria-hidden="true" /> Mark all read
        </button>
      </div>
      {notifications.length === 0 ? (
        <div className="empty-state">
          <Bell size={18} aria-hidden="true" style={{ opacity: 0.3 }} />
          <div className="empty-state-title">No notifications</div>
        </div>
      ) : (
        <ul style={{ overflowY: 'auto', maxHeight: 340, listStyle: 'none', margin: 0, padding: 0 }}>
          {notifications.map((n) => (
            <li key={n.id}>
              <button type="button" className={`notif-item ${!n.is_read ? 'unread' : ''}`}
                onClick={() => { if (!n.is_read) onMarkRead(n.id); onOpen(n); }}
                style={{ width: '100%', textAlign: 'left', background: 'none', border: 0, font: 'inherit', cursor: 'pointer' }}>
                <span className={`notif-dot ${TYPE_CLASS[n.notification_type] || 'info'}`} aria-hidden="true" />
                <span className="notif-content">
                  <span className="notif-title" style={{ display: 'block' }}>
                    {!n.is_read && <span className="sr-only">Unread: </span>}{n.title}
                  </span>
                  <span className="notif-message" style={{ display: 'block' }}>{n.message}</span>
                  <span className="notif-time" style={{ display: 'block' }}>{formatDate(n.created_at, { withTime: true })}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [showNotifs, setShowNotifs] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [realtimeStatus, setRealtimeStatus] = useState('connecting');
  const notifRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptRef = useRef(0);

  const refreshNotifications = useCallback(() => {
    notificationsAPI.list({ limit: 30 })
      .then((res) => {
        setNotifications(res.data || []);
        const header = Number(res.headers?.['x-unread-count']);
        setUnreadCount(Number.isFinite(header) ? header : (res.data || []).filter((n) => !n.is_read).length);
      })
      .catch(() => { /* the bell simply keeps its last state; pages report their own errors */ });
  }, []);

  useEffect(() => {
    refreshNotifications();
    // Polling is the recovery path if the WebSocket drops.
    const timer = setInterval(refreshNotifications, 60000);
    return () => clearInterval(timer);
  }, [refreshNotifications]);

  useEffect(() => {
    let stopped = false;
    const connect = () => {
      if (stopped) return;
      setRealtimeStatus('connecting');
      const ws = new WebSocket(notificationsAPI.websocketUrl());
      wsRef.current = ws;
      ws.onopen = () => { reconnectAttemptRef.current = 0; setRealtimeStatus('connected'); };
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.event === 'notification.created' && payload.notification) {
            const incoming = payload.notification;
            setNotifications((prev) => [incoming, ...prev.filter((n) => n.id !== incoming.id)].slice(0, 30));
            setUnreadCount((prev) => prev + 1);
          }
        } catch { /* ignore malformed server messages */ }
      };
      ws.onclose = () => {
        if (stopped) return;
        setRealtimeStatus('reconnecting');
        const delay = Math.min(30000, 1000 * (2 ** reconnectAttemptRef.current));
        reconnectAttemptRef.current = Math.min(reconnectAttemptRef.current + 1, 5);
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => {
      stopped = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, []);

  useEffect(() => {
    const onPointer = (e) => { if (notifRef.current && !notifRef.current.contains(e.target)) setShowNotifs(false); };
    const onKey = (e) => { if (e.key === 'Escape') setShowNotifs(false); };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onPointer); document.removeEventListener('keydown', onKey); };
  }, []);

  const markRead = async (id) => {
    try {
      await notificationsAPI.markRead(id);
      setNotifications((list) => list.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch { /* non-critical */ }
  };

  const markAllRead = async () => {
    try {
      await notificationsAPI.markAllRead();
      setNotifications((list) => list.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch { /* non-critical */ }
  };

  const openNotification = (n) => {
    setShowNotifs(false);
    if (n.related_case_id) navigate(`/cases/${n.related_case_id}`);
    else if (n.related_criminal_id) navigate(`/criminals/${n.related_criminal_id}`);
  };

  const initials = user?.full_name?.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase() || 'U';
  const realtimeLabel = { connected: 'Live updates on', reconnecting: 'Reconnecting…', connecting: 'Connecting…' }[realtimeStatus];

  return (
    <div className="app-layout">
      <a className="skip-link" href="#main-content">Skip to main content</a>

      <nav className="sidebar" aria-label="Main navigation">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon" aria-hidden="true"><Shield size={15} /></div>
          <div>
            <div className="sidebar-brand-title">AI-CRMS</div>
            <div className="sidebar-brand-sub">Records Platform</div>
          </div>
        </div>

        <div className="sidebar-classification-banner">
          <Lock size={11} aria-hidden="true" style={{ flexShrink: 0, opacity: 0.7 }} />
          <span>Restricted · activity audited</span>
        </div>

        <div className="sidebar-nav">
          {NAV.map((section) => {
            const visible = section.links.filter((l) => l.roles.includes(user?.role));
            if (!visible.length) return null;
            return (
              <div key={section.section} className="sidebar-group">
                <div className="sidebar-group-title">{section.section}</div>
                {visible.map((link) => (
                  <NavLink key={link.to} to={link.to} title={link.label}
                    className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
                    <link.icon className="sidebar-link-icon" aria-hidden="true" />
                    <span>{link.label}</span>
                    {link.to === '/alerts' && unreadCount > 0 && (
                      <span className="sidebar-badge" aria-label={`${unreadCount} unread`}>{unreadCount}</span>
                    )}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-user-card">
            <div className="sidebar-avatar" aria-hidden="true">{initials}</div>
            <div className="sidebar-user-info" style={{ flex: 1, minWidth: 0 }}>
              <div className="sidebar-user-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.full_name || user?.username}
              </div>
              <div className="sidebar-user-role">{ROLE_LABELS[user?.role] || user?.role}</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
            <button type="button" className="btn btn-ghost btn-sm" style={{ flex: 1 }} onClick={() => navigate('/change-password')}
              title="Change password">
              <KeyRound size={13} aria-hidden="true" /><span className="sidebar-action-label">Password</span>
            </button>
            <button type="button" className="btn btn-ghost btn-sm" style={{ flex: 1 }} onClick={logout} title="Sign out">
              <LogOut size={13} aria-hidden="true" /><span className="sidebar-action-label">Sign out</span>
            </button>
          </div>
        </div>
      </nav>

      <header className="header">
        <div className="header-status" aria-live="polite">
          <div className="header-status-indicator">
            <span className={`status-dot ${realtimeStatus !== 'connected' ? 'status-dot-muted' : ''}`} aria-hidden="true" />
            <span>{realtimeLabel}</span>
          </div>
        </div>

        <div className="header-controls">
          <div style={{ position: 'relative' }} ref={notifRef}>
            <button type="button" className="header-btn" onClick={() => setShowNotifs((s) => !s)}
              aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`} aria-expanded={showNotifs}>
              <Bell size={15} aria-hidden="true" />
              {unreadCount > 0 && <span className="notif-badge-dot" aria-hidden="true" />}
            </button>
            {showNotifs && (
              <NotificationPanel notifications={notifications} onMarkRead={markRead}
                onMarkAllRead={markAllRead} onOpen={openNotification} />
            )}
          </div>
          <div className="user-pill">
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{user?.full_name?.split(' ')[0]}</span>
            <span className="badge badge-blue">{ROLE_LABELS[user?.role] || user?.role}</span>
          </div>
        </div>
      </header>

      <main className="main-content" id="main-content" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}

import { useState, useEffect, useRef, useCallback } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { notificationsAPI } from '../services/api';
import {
  LayoutDashboard, Users, FileText, Shield,
  Brain, Bell, LogOut, Siren, BookOpen, Activity, Database, CheckCheck,
  Lock
} from 'lucide-react';

const NAV = [
  {
    section: 'Overview',
    links: [
      { to: '/dashboard', icon: LayoutDashboard, label: 'Command Center', roles: ['admin', 'investigating_officer', 'record_clerk'] },
    ]
  },
  {
    section: 'Intelligence & Records',
    links: [
      { to: '/criminals', icon: Shield, label: 'Offender Directory', roles: ['admin', 'investigating_officer', 'record_clerk'] },
      { to: '/cases', icon: FileText, label: 'Cases & FIR Files', roles: ['admin', 'investigating_officer', 'record_clerk'] },
    ]
  },
  {
    section: 'Decision Support',
    links: [
      { to: '/ai-predictions', icon: Brain, label: 'AI Risk Predictions', roles: ['admin', 'investigating_officer'] },
      { to: '/alerts', icon: Siren, label: 'Operational Alerts', roles: ['admin', 'investigating_officer'] },
    ]
  },
  {
    section: 'Governance',
    links: [
      { to: '/admin/users', icon: Users, label: 'User Directory', roles: ['admin'] },
      { to: '/admin/gangs', icon: Database, label: 'Gang Tracking', roles: ['admin'] },
      { to: '/admin/audit', icon: BookOpen, label: 'Audit Log Stream', roles: ['admin'] },
      { to: '/admin/ai-models', icon: Activity, label: 'Model Governance', roles: ['admin'] },
    ]
  },
];

function NotificationPanel({ onClose, notifications, setNotifications }) {
  const [loading, setLoading] = useState(true);

  useEffect(() => { setLoading(false); }, []);

  const markAllRead = async () => {
    await notificationsAPI.markAllRead();
    setNotifications(n => n.map(x => ({ ...x, is_read: true })));
  };

  const markRead = async (id) => {
    await notificationsAPI.markRead(id);
    setNotifications(n => n.map(x => x.id === id ? { ...x, is_read: true } : x));
  };

  const typeColor = (t) => {
    if (t === 'alert') return 'alert';
    if (t === 'warning') return 'warning';
    if (t === 'success') return 'success';
    return 'info';
  };

  const cleanText = (str) => {
    if (!str) return '';
    return str.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F900}-\u{1F9FF}\u{1F004}\u{1F0CF}\u{1F170}-\u{1F251}]/gu, '').trim();
  };

  return (
    <div className="notification-dropdown">
      <div className="notif-header">
        <span className="notif-header-title">Notifications</span>
        <button className="btn btn-ghost btn-sm" onClick={markAllRead}>
          <CheckCheck size={13} /> Mark read
        </button>
      </div>
      {loading ? (
        <div className="empty-state" style={{ minHeight: 100 }}>
          <div className="spinner" />
        </div>
      ) : notifications.length === 0 ? (
        <div className="empty-state">
          <Bell size={18} style={{ opacity: 0.3 }} />
          <div className="empty-state-title">No notifications</div>
        </div>
      ) : (
        <div style={{ overflowY: 'auto', maxHeight: 340 }}>
          {notifications.map(n => (
            <div
              key={n.id}
              className={`notif-item ${!n.is_read ? 'unread' : ''}`}
              onClick={() => markRead(n.id)}
            >
              <div className={`notif-dot ${typeColor(n.notification_type)}`} />
              <div className="notif-content">
                <div className="notif-title">{cleanText(n.title)}</div>
                <div className="notif-message">{cleanText(n.message)}</div>
                <div className="notif-time">
                  {new Date(n.created_at).toLocaleString()}
                </div>
              </div>
            </div>
          ))}
        </div>
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
    notificationsAPI.list({ limit: 50 })
      .then(r => {
        const data = r.data || [];
        setNotifications(data);
        setUnreadCount(data.filter(n => !n.is_read).length);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshNotifications();
    // Polling remains an intentional recovery fallback for dropped sockets.
    const t = setInterval(refreshNotifications, 30000);
    return () => clearInterval(t);
  }, [refreshNotifications]);

  useEffect(() => {
    let stopped = false;
    const connect = () => {
      if (stopped || !localStorage.getItem('acrms_token')) return;
      setRealtimeStatus('connecting');
      const ws = new WebSocket(notificationsAPI.websocketUrl());
      wsRef.current = ws;
      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        setRealtimeStatus('connected');
      };
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.event === 'notification.created' && payload.notification) {
            const incoming = payload.notification;
            setNotifications(prev => [incoming, ...prev.filter(n => n.id !== incoming.id)].slice(0, 50));
            setUnreadCount(prev => prev + (incoming.is_read ? 0 : 1));
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
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  useEffect(() => {
    const handler = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setShowNotifs(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const roleLabel = {
    admin: 'Administrator',
    investigating_officer: 'Inv. Officer',
    record_clerk: 'Record Clerk',
  }[user?.role] || user?.role;

  const initials = user?.full_name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'U';
  const visibleLinks = (links) => links.filter(l => l.roles.includes(user?.role));

  return (
    <div className="app-layout">
      {/* Minimalistic Sidebar */}
      <nav className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <Shield size={15} />
          </div>
          <div>
            <div className="sidebar-brand-title">AI-CRMS</div>
            <div className="sidebar-brand-sub">Platform</div>
          </div>
        </div>

        <div className="sidebar-classification-banner">
          <Lock size={11} style={{ flexShrink: 0, opacity: 0.7 }} />
          <span>Restricted environment</span>
        </div>

        <div className="sidebar-nav">
          {NAV.map(section => {
            const visible = visibleLinks(section.links);
            if (visible.length === 0) return null;
            return (
              <div key={section.section} className="sidebar-group">
                <div className="sidebar-group-title">{section.section}</div>
                {visible.map(link => (
                  <NavLink
                    key={link.to}
                    to={link.to}
                    className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
                  >
                    <link.icon className="sidebar-link-icon" />
                    <span>{link.label}</span>
                    {link.to === '/alerts' && unreadCount > 0 && (
                      <span className="sidebar-badge">{unreadCount}</span>
                    )}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-user-card" onClick={logout} title="Click to logout">
            <div className="sidebar-avatar">{initials}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="sidebar-user-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.full_name || user?.username}
              </div>
              <div className="sidebar-user-role">{roleLabel}</div>
            </div>
            <LogOut size={13} style={{ color: 'var(--text-muted)' }} />
          </div>
        </div>
      </nav>

      {/* Header */}
      <header className="header">
        <div className="header-status">
          <div className="header-status-indicator">
            <span className="status-dot" />
            <span>Operational</span>
          </div>
          <span className="header-status-divider">/</span>
          <span style={{ color: 'var(--text-secondary)' }}>{realtimeStatus === 'connected' ? 'Live Connection' : realtimeStatus === 'reconnecting' ? 'Reconnecting' : 'Connecting'}</span>
        </div>

        <div className="header-controls">
          <div style={{ position: 'relative' }} ref={notifRef}>
            <button
              className="header-btn"
              onClick={() => setShowNotifs(s => !s)}
              title="Notifications"
            >
              <Bell size={15} />
              {unreadCount > 0 && <span className="notif-badge-dot" />}
            </button>
            {showNotifs && <NotificationPanel onClose={() => setShowNotifs(false)} notifications={notifications} setNotifications={setNotifications} />}
          </div>

          <div className="user-pill">
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{user?.full_name?.split(' ')[0]}</span>
            <span className="badge badge-blue">{user?.role?.replace('_', ' ')}</span>
          </div>
        </div>
      </header>

      {/* Main Page Area */}
      <main className="main-content">
        {children}
      </main>
    </div>
  );
}

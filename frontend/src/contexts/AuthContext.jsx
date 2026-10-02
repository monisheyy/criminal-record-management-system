import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { authAPI, onSessionEvent } from '../services/api';

const AuthContext = createContext(null);

/**
 * The session lives in an HttpOnly cookie the browser manages; this context
 * only keeps the *user profile* in memory and re-validates it with /me on
 * load. Nothing authentication-related is written to localStorage.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Clean up tokens left behind by older versions of the app.
    try { localStorage.removeItem('acrms_token'); localStorage.removeItem('acrms_user'); } catch { /* storage unavailable */ }
    authAPI.me()
      .then((res) => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => onSessionEvent((type) => {
    if (type === 'expired') {
      setUser((current) => {
        if (current) toast.error('Your session has ended. Please sign in again.', { id: 'session-expired' });
        return null;
      });
    }
    if (type === 'password-change-required') {
      setUser((current) => (current ? { ...current, must_change_password: true } : current));
    }
  }), []);

  const login = useCallback(async (username, password) => {
    const res = await authAPI.login(username, password);
    setUser(res.data.user);
    return res.data.user;
  }, []);

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    const res = await authAPI.changePassword(currentPassword, newPassword);
    setUser(res.data.user);
    return res.data.user;
  }, []);

  const logout = useCallback(async () => {
    try { await authAPI.logout(); } catch { /* the server clears the cookie; nothing else to do */ }
    setUser(null);
  }, []);

  const isAdmin = user?.role === 'admin';
  const isOfficer = user?.role === 'investigating_officer';
  const isClerk = user?.role === 'record_clerk';
  const canEdit = isAdmin || isOfficer || isClerk;

  return (
    <AuthContext.Provider value={{ user, login, logout, changePassword, loading, isAdmin, isOfficer, isClerk, canEdit }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};

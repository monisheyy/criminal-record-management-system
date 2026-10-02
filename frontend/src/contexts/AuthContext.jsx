import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authAPI } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('acrms_token');
    const savedUser = localStorage.getItem('acrms_user');
    if (token && savedUser) {
      try {
        setUser(JSON.parse(savedUser));
      } catch {}
    }
    setLoading(false);
  }, []);

  const login = useCallback(async (username, password) => {
    const res = await authAPI.login(username, password);
    const { access_token, user: userData } = res.data;
    localStorage.setItem('acrms_token', access_token);
    localStorage.setItem('acrms_user', JSON.stringify(userData));
    setUser(userData);
    return userData;
  }, []);

  const logout = useCallback(async () => {
    try { await authAPI.logout(); } catch {}
    localStorage.removeItem('acrms_token');
    localStorage.removeItem('acrms_user');
    setUser(null);
  }, []);

  const isAdmin = user?.role === 'admin';
  const isOfficer = user?.role === 'investigating_officer';
  const isClerk = user?.role === 'record_clerk';
  const canEdit = isAdmin || isOfficer || isClerk;

  return (
    <AuthContext.Provider value={{ user, login, logout, loading, isAdmin, isOfficer, isClerk, canEdit }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};

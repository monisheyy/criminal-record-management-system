import { useMemo } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LoadingState } from './ui';

export default function ProtectedRoute({ children, roles }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  // A stable state object: <Navigate> re-navigates whenever its props change,
  // so a fresh object on every render would redirect over and over.
  const redirectState = useMemo(() => ({ from: location.pathname }), [location.pathname]);

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-base)' }}>
        <LoadingState label="Loading AI-CRMS…" />
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace state={redirectState} />;

  if (user.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }

  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}

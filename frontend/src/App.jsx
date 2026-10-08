import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider } from './contexts/AuthContext';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import ErrorBoundary from './components/ErrorBoundary';
import { LoadingState } from './components/ui';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ChangePassword from './pages/ChangePassword';
// Pages are code-split per route so each screen only downloads what it needs.
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Criminals = lazy(() => import('./pages/Criminals'));
const CriminalProfile = lazy(() => import('./pages/CriminalProfile'));
const Cases = lazy(() => import('./pages/Cases'));
const CaseDetails = lazy(() => import('./pages/CaseDetails'));
const IncidentMap = lazy(() => import('./pages/IncidentMap'));
const AIPredictions = lazy(() => import('./pages/AIPredictions'));
const Alerts = lazy(() => import('./pages/Alerts'));
const AdminUsers = lazy(() => import('./pages/AdminUsers'));
const AdminGangs = lazy(() => import('./pages/AdminGangs'));
const AdminAudit = lazy(() => import('./pages/AdminAudit'));
const AdminAIModels = lazy(() => import('./pages/AdminAIModels'));

const ALL_ROLES = ['admin', 'investigating_officer', 'record_clerk'];
const OFFICERS = ['admin', 'investigating_officer'];
const ADMIN = ['admin'];

const ROUTES = [
  { path: '/dashboard', element: <Dashboard />, roles: ALL_ROLES },
  { path: '/criminals', element: <Criminals />, roles: ALL_ROLES },
  { path: '/criminals/:id', element: <CriminalProfile />, roles: ALL_ROLES },
  { path: '/cases', element: <Cases />, roles: ALL_ROLES },
  { path: '/cases/:id', element: <CaseDetails />, roles: ALL_ROLES },
  { path: '/map', element: <IncidentMap />, roles: ALL_ROLES },
  { path: '/ai-predictions', element: <AIPredictions />, roles: OFFICERS },
  { path: '/alerts', element: <Alerts />, roles: ALL_ROLES },
  { path: '/admin/users', element: <AdminUsers />, roles: ADMIN },
  { path: '/admin/gangs', element: <AdminGangs />, roles: ADMIN },
  { path: '/admin/audit', element: <AdminAudit />, roles: ADMIN },
  { path: '/admin/ai-models', element: <AdminAIModels />, roles: ADMIN },
];

function Page({ element }) {
  const location = useLocation();
  // Keyed by path so a crash on one page resets when the user navigates away.
  return (
    <ErrorBoundary key={location.pathname}>
      <Suspense fallback={<LoadingState label="Loading…" minHeight="40vh" />}>{element}</Suspense>
    </ErrorBoundary>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster position="top-right" toastOptions={{ ariaProps: { role: 'status', 'aria-live': 'polite' } }} />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/change-password" element={<ProtectedRoute><ChangePassword /></ProtectedRoute>} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          {ROUTES.map(({ path, element, roles }) => (
            <Route key={path} path={path} element={
              <ProtectedRoute roles={roles}><Layout><Page element={element} /></Layout></ProtectedRoute>
            } />
          ))}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

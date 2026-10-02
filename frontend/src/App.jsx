import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider } from './contexts/AuthContext';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import Dashboard from './pages/Dashboard';

// Placeholder components for pages we'll create next
import Criminals from './pages/Criminals';
import CriminalProfile from './pages/CriminalProfile';
import Cases from './pages/Cases';
import CaseDetails from './pages/CaseDetails';
import AIPredictions from './pages/AIPredictions';
import Alerts from './pages/Alerts';
import AdminUsers from './pages/AdminUsers';
import AdminGangs from './pages/AdminGangs';
import AdminAudit from './pages/AdminAudit';
import AdminAIModels from './pages/AdminAIModels';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster position="top-right" />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          
          <Route path="/" element={<ProtectedRoute><Layout><Dashboard /></Layout></ProtectedRoute>} />
          <Route path="/dashboard" element={<ProtectedRoute><Layout><Dashboard /></Layout></ProtectedRoute>} />
          
          <Route path="/criminals" element={<ProtectedRoute><Layout><Criminals /></Layout></ProtectedRoute>} />
          <Route path="/criminals/:id" element={<ProtectedRoute><Layout><CriminalProfile /></Layout></ProtectedRoute>} />
          
          <Route path="/cases" element={<ProtectedRoute><Layout><Cases /></Layout></ProtectedRoute>} />
          <Route path="/cases/:id" element={<ProtectedRoute><Layout><CaseDetails /></Layout></ProtectedRoute>} />
          
          <Route path="/ai-predictions" element={<ProtectedRoute roles={['admin', 'investigating_officer']}><Layout><AIPredictions /></Layout></ProtectedRoute>} />
          <Route path="/alerts" element={<ProtectedRoute roles={['admin', 'investigating_officer']}><Layout><Alerts /></Layout></ProtectedRoute>} />
          
          <Route path="/admin/users" element={<ProtectedRoute roles={['admin']}><Layout><AdminUsers /></Layout></ProtectedRoute>} />
          <Route path="/admin/gangs" element={<ProtectedRoute roles={['admin']}><Layout><AdminGangs /></Layout></ProtectedRoute>} />
          <Route path="/admin/audit" element={<ProtectedRoute roles={['admin']}><Layout><AdminAudit /></Layout></ProtectedRoute>} />
          <Route path="/admin/ai-models" element={<ProtectedRoute roles={['admin']}><Layout><AdminAIModels /></Layout></ProtectedRoute>} />
          
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

import axios from 'axios';

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
});

// Attach JWT to every request
API.interceptors.request.use((config) => {
  const token = localStorage.getItem('acrms_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-logout on 401
API.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('acrms_token');
      localStorage.removeItem('acrms_user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// ── Auth ─────────────────────────────────────────────────────────────────────
export const authAPI = {
  login: (username, password) => {
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);
    return API.post('/api/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
  },
  me: () => API.get('/api/auth/me'),
};

// ── Criminals ────────────────────────────────────────────────────────────────
export const criminalsAPI = {
  list: (params) => API.get('/api/criminals', { params }),
  get: (id) => API.get(`/api/criminals/${id}`),
  create: (data) => API.post('/api/criminals', data),
  update: (id, data) => API.put(`/api/criminals/${id}`, data),
  delete: (id) => API.delete(`/api/criminals/${id}`),
  checkDuplicate: (params) => API.get('/api/criminals/check-duplicate', { params }),
  history: (id) => API.get(`/api/criminals/${id}/history`),
  report: (id) => API.get(`/api/criminals/${id}/report`, { responseType: 'blob' }),
};

// ── Cases ────────────────────────────────────────────────────────────────────
export const casesAPI = {
  list: (params) => API.get('/api/cases', { params }),
  get: (id) => API.get(`/api/cases/${id}`),
  create: (data) => API.post('/api/cases', data),
  update: (id, data) => API.put(`/api/cases/${id}`, data),
  delete: (id) => API.delete(`/api/cases/${id}`),
  assign: (caseId, officerId) => API.post(`/api/cases/${caseId}/assign?officer_id=${officerId}`),
  addEvidence: (caseId, data) => API.post(`/api/cases/${caseId}/evidence`, data),
  addVictim: (caseId, data) => API.post(`/api/cases/${caseId}/victims`, data),
  addCriminal: (caseId, criminalId, role) =>
    API.post(`/api/cases/${caseId}/criminals?criminal_id=${criminalId}&role=${role}`),
  report: (id) => API.get(`/api/cases/${id}/report`, { responseType: 'blob' }),
};

// ── AI Predictions ────────────────────────────────────────────────────────────
export const aiAPI = {
  predict: (data) => API.post('/api/ai/predict', data),
  list: (params) => API.get('/api/ai/predictions', { params }),
  get: (id) => API.get(`/api/ai/predictions/${id}`),
  review: (id, data) => API.post(`/api/ai/predictions/${id}/review`, data),
  retrain: () => API.post('/api/ai/retrain'),
  models: () => API.get('/api/ai/models'),
};

// ── Admin ─────────────────────────────────────────────────────────────────────
export const adminAPI = {
  users: () => API.get('/api/admin/users'),
  createUser: (data) => API.post('/api/admin/users', data),
  updateUser: (id, data) => API.put(`/api/admin/users/${id}`, data),
  deleteUser: (id) => API.delete(`/api/admin/users/${id}`),
  auditLogs: (params) => API.get('/api/admin/audit-logs', { params }),
  dashboard: () => API.get('/api/admin/dashboard'),
};

// ── Gangs ─────────────────────────────────────────────────────────────────────
export const gangsAPI = {
  list: () => API.get('/api/gangs'),
  create: (data) => API.post('/api/gangs', data),
  update: (id, data) => API.put(`/api/gangs/${id}`, data),
  delete: (id) => API.delete(`/api/gangs/${id}`),
};

// ── Notifications ─────────────────────────────────────────────────────────────
export const notificationsAPI = {
  list: (params) => API.get('/api/notifications', { params }),
  markRead: (id) => API.post(`/api/notifications/${id}/read`),
  markAllRead: () => API.post('/api/notifications/read-all'),
};

export default API;

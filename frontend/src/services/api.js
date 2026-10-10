import axios from 'axios';

// VITE_API_URL="" means "same origin" (the production nginx proxies /api).
export const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/**
 * Session model: the API sets an HttpOnly, SameSite cookie at login. Page
 * JavaScript never sees or stores the token (no localStorage), so an XSS bug
 * cannot exfiltrate it. `X-Requested-With` satisfies the API's CSRF check
 * for cookie-authenticated writes.
 */
const API = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  withCredentials: true,
  headers: { 'X-Requested-With': 'XMLHttpRequest' },
});

// Listeners notified when the session ends or a password change is required.
const sessionListeners = new Set();
export const onSessionEvent = (fn) => {
  sessionListeners.add(fn);
  return () => sessionListeners.delete(fn);
};
const emit = (type) => sessionListeners.forEach((fn) => fn(type));

API.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status;
    const url = err.config?.url || '';
    if (status === 401 && !url.includes('/api/auth/login') && !url.includes('/api/auth/me')) {
      emit('expired');
    }
    if (status === 403 && err.response?.headers?.['x-password-change-required'] === 'true') {
      emit('password-change-required');
    }
    return Promise.reject(err);
  }
);

export { getErrorMessage } from '../utils/errors.js';

/** Read the total row count the API reports for paginated lists. */
export const totalCount = (res) => {
  const value = Number(res?.headers?.['x-total-count']);
  return Number.isFinite(value) ? value : (res?.data?.length ?? 0);
};

/** Save a blob response as a file (filename from Content-Disposition when present). */
export const saveBlob = (res, fallbackName) => {
  const disposition = res.headers?.['content-disposition'] || '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const url = window.URL.createObjectURL(new Blob([res.data]));
  const link = document.createElement('a');
  link.href = url;
  link.download = match ? match[1] : fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

/** Wrap a File for a multipart upload (the API reads the field named "file"). */
const fileForm = (file) => {
  const form = new FormData();
  form.append('file', file);
  return form;
};

const clean = (params = {}) =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined));

// ── Auth ─────────────────────────────────────────────────────────────────────
export const authAPI = {
  logout: () => API.post('/api/auth/logout'),
  login: (username, password) => {
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);
    return API.post('/api/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
  },
  me: () => API.get('/api/auth/me'),
  changePassword: (current_password, new_password) =>
    API.post('/api/auth/change-password', { current_password, new_password }),
  requestRecovery: (identifier) => API.post('/api/auth/password-recovery/request', { identifier }),
  verifyRecovery: (identifier, otp) => API.post('/api/auth/password-recovery/verify', { identifier, otp }),
  resetPassword: (reset_token, new_password) => API.post('/api/auth/password-recovery/reset', { reset_token, new_password }),
};

// ── Criminals ────────────────────────────────────────────────────────────────
export const criminalsAPI = {
  list: (params) => API.get('/api/criminals', { params: clean(params) }),
  get: (id) => API.get(`/api/criminals/${id}`),
  create: (data) => API.post('/api/criminals', data),
  update: (id, data) => API.put(`/api/criminals/${id}`, data),
  delete: (id, reason) => API.delete(`/api/criminals/${id}`, { params: { reason } }),
  checkDuplicate: (params) => API.get('/api/criminals/check-duplicate', { params: clean(params) }),
  history: (id) => API.get(`/api/criminals/${id}/history`),
  addHistory: (id, data) => API.post(`/api/criminals/${id}/history`, data),
  report: (id) => API.get(`/api/criminals/${id}/report`, { responseType: 'blob' }),
  reportExcel: (id) => API.get(`/api/criminals/${id}/report/excel`, { responseType: 'blob' }),
  uploadPhoto: (id, file) => API.put(`/api/criminals/${id}/photo`, fileForm(file)),
  removePhoto: (id, reason) => API.delete(`/api/criminals/${id}/photo`, { params: { reason } }),
};

/** Same-origin URL of an offender photo; `version` (the photo's SHA-256) busts the browser cache. */
export const criminalPhotoUrl = (id, version) => `${API_BASE}/api/criminals/${id}/photo?v=${version}`;

// ── Cases ────────────────────────────────────────────────────────────────────
export const casesAPI = {
  list: (params) => API.get('/api/cases', { params: clean(params) }),
  get: (id) => API.get(`/api/cases/${id}`),
  create: (data) => API.post('/api/cases', data),
  update: (id, data) => API.put(`/api/cases/${id}`, data),
  delete: (id) => API.delete(`/api/cases/${id}`),
  assign: (caseId, officerId) => API.post(`/api/cases/${caseId}/assign`, { officer_id: Number(officerId) }),
  addEvidence: (caseId, data) => API.post(`/api/cases/${caseId}/evidence`, data),
  updateEvidence: (caseId, evidenceId, data) => API.put(`/api/cases/${caseId}/evidence/${evidenceId}`, data),
  uploadEvidenceFile: (caseId, evidenceId, file) =>
    API.post(`/api/cases/${caseId}/evidence/${evidenceId}/file`, fileForm(file)),
  evidenceFile: (caseId, evidenceId) =>
    API.get(`/api/cases/${caseId}/evidence/${evidenceId}/file`, { responseType: 'blob' }),
  addVictim: (caseId, data) => API.post(`/api/cases/${caseId}/victims`, data),
  addCriminal: (caseId, criminalId, role) =>
    API.post(`/api/cases/${caseId}/criminals`, { criminal_id: Number(criminalId), role }),
  removeCriminal: (caseId, criminalId, reason) =>
    API.delete(`/api/cases/${caseId}/criminals/${criminalId}`, { params: { reason } }),
  report: (id) => API.get(`/api/cases/${id}/report`, { responseType: 'blob' }),
  reportExcel: (id) => API.get(`/api/cases/${id}/report/excel`, { responseType: 'blob' }),
};

// ── Users directory ──────────────────────────────────────────────────────────
export const usersAPI = {
  officers: () => API.get('/api/users/officers'),
};

// ── AI Predictions ────────────────────────────────────────────────────────────
export const aiAPI = {
  status: () => API.get('/api/ai/status'),
  predict: (data) => API.post('/api/ai/predict', data),
  list: (params) => API.get('/api/ai/predictions', { params: clean(params) }),
  get: (id) => API.get(`/api/ai/predictions/${id}`),
  review: (id, data) => API.post(`/api/ai/predictions/${id}/review`, data),
  retrain: () => API.post('/api/ai/retrain', null, { timeout: 180000 }),
  models: () => API.get('/api/ai/models'),
  activate: (id, justification) => API.post(`/api/ai/models/${id}/activate`, { justification }),
  rollback: (id, justification) => API.post(`/api/ai/models/${id}/rollback`, { justification }),
};

// ── Admin ─────────────────────────────────────────────────────────────────────
export const adminAPI = {
  users: () => API.get('/api/admin/users'),
  createUser: (data) => API.post('/api/admin/users', data),
  updateUser: (id, data) => API.put(`/api/admin/users/${id}`, data),
  deleteUser: (id) => API.delete(`/api/admin/users/${id}`),
  auditLogs: (params) => API.get('/api/admin/audit-logs', { params: clean(params) }),
  verifyAuditLogs: () => API.get('/api/admin/audit-logs/verify'),
  metrics: () => API.get('/api/admin/metrics'),
  dashboard: () => API.get('/api/admin/dashboard'),
  dashboardExcel: () => API.get('/api/admin/dashboard/report/excel', { responseType: 'blob' }),
  dashboardPdf: () => API.get('/api/admin/dashboard/report/pdf', { responseType: 'blob' }),
};

// ── Gangs ─────────────────────────────────────────────────────────────────────
export const gangsAPI = {
  list: () => API.get('/api/gangs'),
  create: (data) => API.post('/api/gangs', data),
  update: (id, data) => API.put(`/api/gangs/${id}`, data),
  delete: (id) => API.delete(`/api/gangs/${id}`),
};

// ── Intelligence Network ───────────────────────────────────────────────────
export const intelligenceAPI = {
  network: (params) => API.get('/api/intelligence/network', { params: clean(params) }),
  incidentMap: (params) => API.get('/api/intelligence/incident-map', { params: clean(params) }),
};

// ── Notifications ─────────────────────────────────────────────────────────────
export const notificationsAPI = {
  list: (params) => API.get('/api/notifications', { params: clean(params) }),
  markRead: (id) => API.post(`/api/notifications/${id}/read`),
  markAllRead: () => API.post('/api/notifications/read-all'),
  // The session cookie authenticates the socket; no token in the URL.
  websocketUrl: () => `${(API_BASE || window.location.origin).replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')}/api/notifications/ws`,
};

export default API;

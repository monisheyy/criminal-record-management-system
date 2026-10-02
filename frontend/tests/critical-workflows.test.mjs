import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve(new URL('..', import.meta.url).pathname);
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');

const app = read('src/App.jsx');
const api = read('src/services/api.js');

const pages = {
  login: read('src/pages/Login.jsx'),
  dashboard: read('src/pages/Dashboard.jsx'),
  criminals: read('src/pages/Criminals.jsx'),
  profile: read('src/pages/CriminalProfile.jsx'),
  ai: read('src/pages/AIPredictions.jsx'),
  cases: read('src/pages/Cases.jsx'),
  caseDetails: read('src/pages/CaseDetails.jsx'),
  alerts: read('src/pages/Alerts.jsx'),
  models: read('src/pages/AdminAIModels.jsx'),
};

test('login and password recovery routes exist', () => {
  assert.match(app, /path="\/login"/);
  assert.match(app, /path="\/forgot-password"/);
  assert.match(pages.login, /Forgot password/i);
});

test('dashboard workflow loads dashboard API and exports analytics', () => {
  assert.match(api, /dashboard: \(\) => API\.get\('\/api\/admin\/dashboard'\)/);
  assert.match(api, /dashboardExcel/);
  assert.match(api, /dashboardPdf/);
  assert.match(pages.dashboard, /Export PDF/);
  assert.match(pages.dashboard, /Export Excel/);
});

test('criminal workflow supports search, profile, AI assessment and reports', () => {
  assert.match(api, /list: \(params\) => API\.get\('\/api\/criminals'/);
  assert.match(api, /predict: \(data\) => API\.post\('\/api\/ai\/predict'/);
  assert.match(api, /reportExcel/);
  assert.match(pages.criminals, /fetchCriminals/);
  assert.match(pages.profile, /handlePredict/);
  assert.match(pages.profile, /Export PDF/);
  assert.match(pages.profile, /Export Excel/);
});

test('case navigation and case-detail operations are wired', () => {
  assert.match(app, /path="\/cases"/);
  assert.match(app, /path="\/cases\/:id"/);
  assert.match(api, /addEvidence/);
  assert.match(api, /addVictim/);
  assert.match(api, /addCriminal/);
  assert.match(pages.caseDetails, /handleDownloadReport/);
});

test('alerts and admin model governance workflows are routed and wired', () => {
  assert.match(app, /path="\/alerts"/);
  assert.match(app, /path="\/admin\/ai-models"/);
  assert.match(api, /notificationsAPI/);
  assert.match(api, /retrain: \(\) => API\.post\('\/api\/ai\/retrain'\)/);
  assert.match(pages.alerts, /fetchAlerts/);
  assert.match(pages.models, /handleRetrain/);
});

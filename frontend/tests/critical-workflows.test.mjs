/**
 * Static wiring checks for critical workflows. They pin the API contract each
 * screen depends on (several of these were broken before: wrong field names,
 * capitalised enum values, token storage in localStorage). Behavioural
 * coverage lives in tests/e2e (Playwright) and tests/utils.test.mjs.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const sources = (dir) => fs.readdirSync(path.join(root, dir), { recursive: true })
  .filter((f) => /\.(jsx?|mjs)$/.test(f)).map((f) => read(path.join(dir, f))).join('\n');

const app = read('src/App.jsx');
const api = read('src/services/api.js');
const allSource = sources('src');
const page = (name) => read(`src/pages/${name}.jsx`);

test('routes exist for every screen, including forced password change', () => {
  for (const route of ['/login', '/forgot-password', '/change-password', '/dashboard', '/criminals', '/criminals/:id',
    '/cases', '/cases/:id', '/ai-predictions', '/alerts', '/admin/users', '/admin/gangs', '/admin/audit', '/admin/ai-models']) {
    assert.ok(app.includes(`'${route}'`) || app.includes(`"${route}"`), `missing route ${route}`);
  }
  assert.match(app, /ErrorBoundary/, 'routes are wrapped in an error boundary');
});

test('session uses the HttpOnly cookie, never localStorage tokens', () => {
  assert.match(api, /withCredentials: true/);
  assert.match(api, /'X-Requested-With': 'XMLHttpRequest'/);
  assert.doesNotMatch(allSource, /localStorage\.setItem/, 'no credentials or profiles may be written to localStorage');
  assert.doesNotMatch(api, /\?token=/, 'the WebSocket must not carry the token in its URL');
});

test('demo credentials only appear in development builds', () => {
  assert.match(page('Login'), /import\.meta\.env\.DEV/);
});

test('case creation sends API enum values (lowercase priority)', () => {
  const cases = page('Cases');
  assert.doesNotMatch(cases, /priority: 'Medium'/);
  assert.match(cases, /CASE_PRIORITIES/);
});

test('victim and evidence forms use the API field names', () => {
  const details = page('CaseDetails');
  assert.match(details, /first_name/);
  assert.match(details, /last_name/);
  assert.match(details, /location_found/);
  assert.doesNotMatch(details, /contactInfo|status: 'Collected'/);
  assert.match(api, /assign: \(caseId, officerId\) => API\.post\(`\/api\/cases\/\$\{caseId\}\/assign`, \{ officer_id/);
});

test('duplicate check sends snake_case names and reads has_duplicates-style results', () => {
  const criminals = page('Criminals');
  assert.match(criminals, /checkDuplicate\(\{ first_name: first, last_name: last/);
  assert.doesNotMatch(criminals, /matchFound/);
});

test('lists use server-side pagination', () => {
  assert.match(api, /x-total-count/);
  for (const name of ['Criminals', 'Cases', 'AIPredictions', 'AdminAudit']) {
    assert.match(page(name), /Pagination/, `${name} paginates`);
  }
});

test('AI screens label outputs as unverified decision support and require reasons', () => {
  const ai = page('AIPredictions');
  assert.match(ai, /AIAdvisoryBanner/);
  assert.match(ai, /MIN_REMARKS = 10/);
  assert.match(ai, /Review history/);
  assert.match(page('CriminalProfile'), /AIAdvisoryBanner/);
  assert.doesNotMatch(page('Dashboard'), /Model Precision Rating/, 'agreement rate must not be presented as model precision');
});

test('model governance uses is_active and requires a justification to activate', () => {
  const models = page('AdminAIModels');
  assert.match(models, /m\.is_active/);
  assert.match(models, /handleRetrain/);
  assert.match(api, /activate: \(id, justification\)/);
  assert.match(api, /rollback: \(id, justification\)/);
});

test('scores are formatted from fractions through the shared helper', () => {
  assert.doesNotMatch(allSource, /crime_type_confidence\?\.toFixed/, 'raw fraction must not be printed as a percentage');
  assert.match(page('AIPredictions'), /formatScore\(p\.crime_type_confidence\)/);
});

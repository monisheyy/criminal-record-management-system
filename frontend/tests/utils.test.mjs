import assert from 'node:assert/strict';
import test from 'node:test';

import { getErrorMessage, getFieldErrors, humanize } from '../src/utils/errors.js';
import { displayValue, formatScore, localInputToIso, pageCount, todayInputValue } from '../src/utils/format.js';
import { CASE_PRIORITIES, CASE_STATUS_TRANSITIONS, CRIME_TYPES, EVIDENCE_STATUSES } from '../src/utils/constants.js';

const axiosError = (status, data, headers = {}) => ({ response: { status, data, headers } });

test('formatScore renders stored 0-1 fractions as percentages', () => {
  assert.equal(formatScore(0.157), '15.7%');
  assert.equal(formatScore(1), '100.0%');
  assert.equal(formatScore(0), '0.0%');
});

test('formatScore tolerates legacy 0-100 values and missing data', () => {
  assert.equal(formatScore(64.5), '64.5%');
  assert.equal(formatScore(null), '—');
  assert.equal(formatScore(undefined), '—');
  assert.equal(formatScore('abc'), '—');
});

test('displayValue never returns an object (prevents React child crashes)', () => {
  for (const value of [{ nested: true }, [1, 2], true, false, 3, 2.345, 'text', null, '']) {
    assert.equal(typeof displayValue(value), 'string');
  }
  assert.equal(displayValue(true), 'Yes');
  assert.equal(displayValue({ a: 1 }), 'Details available');
});

test('getErrorMessage handles string, validation-array and object details', () => {
  assert.equal(getErrorMessage(axiosError(400, { detail: 'Case not found' })), 'Case not found');
  const validation = axiosError(422, { detail: [
    { loc: ['body', 'first_name'], msg: 'String should have at least 1 character' },
    { loc: ['body', 'photo_url'], msg: 'Value error, Only http(s) URLs or server-relative paths are allowed' },
  ] });
  assert.equal(getErrorMessage(validation),
    'First Name: String should have at least 1 character; Photo Url: Only http(s) URLs or server-relative paths are allowed');
  assert.equal(getErrorMessage(axiosError(409, { detail: { message: 'Possible duplicate', duplicates: [] } })), 'Possible duplicate');
});

test('getErrorMessage covers network failures, timeouts and status fallbacks', () => {
  assert.match(getErrorMessage({ message: 'Network Error' }), /Cannot reach the server/);
  assert.match(getErrorMessage({ code: 'ECONNABORTED' }), /too long/);
  assert.match(getErrorMessage(axiosError(403, {})), /permission/);
  assert.match(getErrorMessage(axiosError(429, {})), /Too many attempts/);
  assert.equal(getErrorMessage(new Error('Choose an officer.')), 'Choose an officer.');
});

test('server errors include the request ID for support', () => {
  const err = axiosError(500, { detail: 'Internal server error.', request_id: 'abc123' });
  assert.equal(getErrorMessage(err), 'Internal server error. (Reference: abc123)');
});

test('getFieldErrors maps validation errors to field names', () => {
  const err = axiosError(422, { detail: [{ loc: ['body', 'email'], msg: 'value is not a valid email address' }] });
  assert.deepEqual(getFieldErrors(err), { email: 'value is not a valid email address' });
  assert.deepEqual(getFieldErrors(axiosError(400, { detail: 'x' })), {});
});

test('date helpers', () => {
  assert.equal(localInputToIso(''), null);
  assert.equal(localInputToIso('not-a-date'), null);
  // Compare against the same local wall-clock time so the test passes in any timezone.
  assert.equal(localInputToIso('2026-03-01T10:30'), new Date(2026, 2, 1, 10, 30).toISOString());
  assert.equal(todayInputValue(new Date(2026, 0, 5)), '2026-01-05');
  assert.equal(pageCount(0, 25), 1);
  assert.equal(pageCount(51, 25), 3);
  assert.equal(humanize('under_investigation'), 'Under Investigation');
});

test('form vocabularies match the API contract', () => {
  // Case priority values must be the lowercase enum the API accepts (the old UI sent "Medium").
  assert.deepEqual(CASE_PRIORITIES.map((p) => p.value), ['low', 'normal', 'high', 'critical']);
  assert.equal(CRIME_TYPES.length, 15);
  assert.ok(EVIDENCE_STATUSES.every((s) => s.value === s.value.toLowerCase()));
  assert.deepEqual(CASE_STATUS_TRANSITIONS.archived, []);
});

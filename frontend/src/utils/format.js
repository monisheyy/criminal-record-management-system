/**
 * Display formatting shared by every page.
 *
 * Model scores are stored as fractions in [0, 1]. Older records may hold
 * 0-100 values, so values above 1 are treated as already-percentages.
 */
export function formatScore(value, digits = 1) {
  const number = Number(value);
  if (value === null || value === undefined || !Number.isFinite(number)) return '—';
  const percent = number <= 1 ? number * 100 : number;
  return `${percent.toFixed(digits)}%`;
}

export function formatDate(value, { withTime = false } = {}) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return withTime
    ? date.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

/** Render any JSON-ish value as short readable text (never an object child). */
export function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return `${value.length} item(s)`;
  return 'Details available';
}

/** Convert a <input type="datetime-local"> value to an ISO string (or null). */
export function localInputToIso(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** Today's date for `max` attributes on date inputs (local time, YYYY-MM-DD). */
export function todayInputValue(now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function nowLocalInputValue(now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${todayInputValue(now)}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

export function pageCount(total, pageSize) {
  return Math.max(1, Math.ceil((Number(total) || 0) / pageSize));
}

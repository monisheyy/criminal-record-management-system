/**
 * Turn any API/axios error into one readable sentence for the UI.
 *
 * Handles the API's error contracts: `{detail: "text"}`,
 * `{detail: [{loc, msg}]}` (validation), `{detail: {message, duplicates}}`
 * (conflicts), network failures and timeouts. Appends the request ID so users
 * can quote it to support without exposing anything sensitive.
 */
export function getErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  if (!error) return fallback;
  if (typeof error === 'string') return error;

  const response = error.response;
  if (!response) {
    if (error.code === 'ECONNABORTED') return 'The server took too long to respond. Please retry.';
    if (error.message === 'Network Error') return 'Cannot reach the server. Check your connection and retry.';
    return error.message || fallback;
  }

  const data = response.data;
  const detail = data && typeof data === 'object' ? data.detail : undefined;
  let message;
  if (typeof detail === 'string') {
    message = detail;
  } else if (Array.isArray(detail)) {
    message = detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((p) => p !== 'body' && p !== 'query').join('.') : '';
        const text = String(item.msg || '').replace(/^Value error, /, '');
        return field ? `${humanize(field)}: ${text}` : text;
      })
      .join('; ');
  } else if (detail && typeof detail === 'object') {
    message = detail.message || JSON.stringify(detail);
  } else if (response.status === 403) {
    message = 'You do not have permission to perform this action.';
  } else if (response.status === 404) {
    message = 'The requested record was not found.';
  } else if (response.status === 429) {
    message = 'Too many attempts. Please wait a minute and try again.';
  } else if (response.status >= 500) {
    message = 'The server encountered an error.';
  }

  message = message || fallback;
  const requestId = (data && data.request_id) || response.headers?.['x-request-id'];
  return response.status >= 500 && requestId ? `${message} (Reference: ${requestId})` : message;
}

/** Field-level validation errors keyed by field name, for inline form messages. */
export function getFieldErrors(error) {
  const detail = error?.response?.data?.detail;
  if (!Array.isArray(detail)) return {};
  return detail.reduce((acc, item) => {
    const loc = Array.isArray(item.loc) ? item.loc : [];
    const field = loc[loc.length - 1];
    if (typeof field === 'string') acc[field] = String(item.msg || '').replace(/^Value error, /, '');
    return acc;
  }, {});
}

export function humanize(value) {
  return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

import { useCallback, useEffect, useState } from 'react';
import { getErrorMessage } from '../services/api';

/**
 * Load data from the API for a screen.
 *
 * `fetcher` returns an axios promise and must be stable (wrap it in
 * useCallback); a new fetcher identity triggers a new request. State is only
 * updated when a response arrives, and `loading` is derived from whether the
 * latest request has answered, so effects never set state synchronously and
 * a slow, stale response can never overwrite a newer one.
 *
 * Returns { data, response, error, loading, reload, setData }.
 */
export function useApiQuery(fetcher, { fallbackError = 'Failed to load data.', enabled = true } = {}) {
  const [nonce, setNonce] = useState(0);
  const [result, setResult] = useState({ fetcher: null, nonce: -1, data: undefined, response: null, error: '' });

  useEffect(() => {
    if (!enabled) return undefined;
    let current = true;
    fetcher()
      .then((response) => {
        if (current) setResult({ fetcher, nonce, data: response.data, response, error: '' });
      })
      .catch((err) => {
        if (current) setResult({ fetcher, nonce, data: undefined, response: null, error: getErrorMessage(err, fallbackError) });
      });
    return () => { current = false; };
  }, [fetcher, nonce, enabled, fallbackError]);

  const answered = result.fetcher === fetcher && result.nonce === nonce;
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  // Local edits (optimistic updates) apply to the latest answered data.
  const setData = useCallback((update) => setResult((prev) => ({
    ...prev, data: typeof update === 'function' ? update(prev.data) : update,
  })), []);

  return {
    // Keep showing the previous data while a reload is in flight.
    data: result.data,
    response: result.response,
    error: answered ? result.error : '',
    loading: enabled && !answered,
    reload,
    setData,
  };
}

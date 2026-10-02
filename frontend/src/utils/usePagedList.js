import { useCallback, useEffect, useRef, useState } from 'react';
import { getErrorMessage, totalCount } from '../services/api';

/**
 * Server-side paginated list state: rows, total (from X-Total-Count),
 * loading/error, and protection against out-of-order responses.
 * `fetcher(params)` must return an axios promise; `params` changes reset to page 0.
 */
export function usePagedList(fetcher, params, pageSize = 25) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestRef = useRef(0);
  const paramsKey = JSON.stringify(params);
  const lastKey = useRef(paramsKey);

  const load = useCallback(() => {
    let targetPage = page;
    if (lastKey.current !== paramsKey) {
      lastKey.current = paramsKey;
      if (page !== 0) { setPage(0); return; } // the page change re-triggers load
      targetPage = 0;
    }
    const requestId = ++requestRef.current;
    setLoading(true);
    setError('');
    fetcher({ ...JSON.parse(paramsKey), skip: targetPage * pageSize, limit: pageSize })
      .then((res) => {
        if (requestId !== requestRef.current) return;
        setRows(res.data || []);
        setTotal(totalCount(res));
      })
      .catch((err) => { if (requestId === requestRef.current) setError(getErrorMessage(err, 'Failed to load data.')); })
      .finally(() => { if (requestId === requestRef.current) setLoading(false); });
  }, [fetcher, paramsKey, page, pageSize]);

  useEffect(() => { load(); }, [load]);

  return { rows, setRows, total, page, setPage, loading, error, reload: load, pageSize };
}

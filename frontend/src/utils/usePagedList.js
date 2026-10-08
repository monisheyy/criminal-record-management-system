import { useCallback, useState } from 'react';
import { totalCount } from '../services/api';
import { useApiQuery } from './useApiQuery';

/**
 * Server-side paginated list state: rows, total (from X-Total-Count),
 * loading/error, and protection against out-of-order responses.
 * `fetcher(params)` must return an axios promise and be stable (an API
 * method or a useCallback); `params` changes reset to page 0.
 */
export function usePagedList(fetcher, params, pageSize = 25) {
  const paramsKey = JSON.stringify(params);
  // The page belongs to the filters it was chosen under, so new filters start at page 0.
  const [pageState, setPageState] = useState({ key: paramsKey, page: 0 });
  const page = pageState.key === paramsKey ? pageState.page : 0;
  const setPage = useCallback((next) => setPageState({ key: paramsKey, page: next }), [paramsKey]);

  const query = useCallback(
    () => fetcher({ ...JSON.parse(paramsKey), skip: page * pageSize, limit: pageSize }),
    [fetcher, paramsKey, page, pageSize],
  );
  const { data, response, error, loading, reload, setData } = useApiQuery(query);

  return {
    rows: data || [],
    setRows: setData,
    total: response ? totalCount(response) : 0,
    page,
    setPage,
    loading,
    error,
    reload,
    pageSize,
  };
}

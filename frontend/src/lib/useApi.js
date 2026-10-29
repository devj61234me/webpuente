import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api/client";

// Loads GET data and exposes {data, loading, error, reload}. Ignores answers that arrive after a newer request or an unmount.
export function useGet(path, params, { enabled = true } = {}) {
  const [state, setState] = useState({ data: null, loading: enabled, error: "" });
  const counter = useRef(0);
  const key = JSON.stringify(params || {});
  const load = useCallback(async (silent = false) => {
    if (!enabled) return;
    const mine = ++counter.current;
    if (!silent) setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const { data } = await api.get(path, { params: JSON.parse(key) });
      if (mine === counter.current) setState({ data, loading: false, error: "" });
    } catch (err) {
      if (mine === counter.current) setState((s) => ({ data: silent ? s.data : null, loading: false, error: errorMessage(err) }));
    }
  }, [path, key, enabled]);
  useEffect(() => { load(); return () => { counter.current++; }; }, [load]);
  return { ...state, reload: load };
}

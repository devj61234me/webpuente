import axios from "axios";

// Empty in development (the Vite dev server proxies /api). In production it is the backend address.
const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");
const REFRESH_KEY = "wp_refresh";

// The access token lives only in memory (lost on reload, then renewed from the refresh token).
// The refresh token is kept in localStorage so people stay signed in. Tradeoff: script injected into the page could read it,
// which is why the app renders no raw HTML and the backend rotates and blacklists refresh tokens.
let accessToken = null;
let onSignedOut = () => {};

export const tokens = {
  get access() { return accessToken; },
  get refresh() { try { return localStorage.getItem(REFRESH_KEY); } catch { return null; } },
  set(access, refresh) {
    accessToken = access || null;
    if (refresh) { try { localStorage.setItem(REFRESH_KEY, refresh); } catch { /* storage blocked: stay signed in for this tab only */ } }
  },
  clear() { accessToken = null; try { localStorage.removeItem(REFRESH_KEY); } catch { /* ignore */ } },
};
export const setSignedOutHandler = (fn) => { onSignedOut = fn; };

export const api = axios.create({ baseURL: `${BASE}/api`, timeout: 60000 });

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});

// One refresh at a time: parallel 401s all wait for the same request.
let refreshing = null;
export function refreshAccess() {
  if (!refreshing) {
    const refresh = tokens.refresh;
    if (!refresh) return Promise.reject(new Error("no refresh token"));
    refreshing = axios
      .post(`${BASE}/api/auth/refresh/`, { refresh })
      .then(({ data }) => { tokens.set(data.access, data.refresh); return data.access; })
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

const isAuthCall = (url = "") => /\/auth\/(login|register|refresh|password-reset)/.test(url);

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { response, config } = error;
    if (response?.status === 401 && config && !config._retried && !isAuthCall(config.url)) {
      config._retried = true;
      try {
        const access = await refreshAccess();
        config.headers.Authorization = `Bearer ${access}`;
        return api(config);
      } catch {
        tokens.clear();
        onSignedOut();
      }
    }
    return Promise.reject(error);
  },
);

// ---- error helpers -------------------------------------------------------------------------------
export function errorInfo(error) {
  if (error?.response) {
    const { status, data } = error.response;
    const e = data?.error;
    if (e) return { status, code: e.code, message: e.message || "Something went wrong.", details: e.details || {} };
    if (status === 429) return { status, code: "throttled", message: "Too many requests. Please wait a moment and try again.", details: {} };
    if (status >= 500) return { status, code: "server_error", message: "The server had a problem. Please try again.", details: {} };
    return { status, code: "error", message: "The request could not be completed.", details: {} };
  }
  if (error?.code === "ECONNABORTED") return { status: 0, code: "timeout", message: "The server took too long to answer. Try again.", details: {} };
  return { status: 0, code: "network", message: "Cannot reach the server. Check your connection and that the API address is correct.", details: {} };
}
export const errorMessage = (error) => errorInfo(error).message;

// DRF field errors arrive as {field: ["message"]}; turn them into {field: "message"}.
export function fieldErrors(error) {
  const out = {};
  const details = errorInfo(error).details;
  if (details && typeof details === "object") {
    for (const [k, v] of Object.entries(details)) out[k] = Array.isArray(v) ? v.join(" ") : typeof v === "string" ? v : "";
  }
  return out;
}

export const apiBase = BASE;

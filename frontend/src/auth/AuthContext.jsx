import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, refreshAccess, setSignedOutHandler, tokens } from "../api/client";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const signedOut = useCallback(() => { tokens.clear(); setUser(null); }, []);
  useEffect(() => { setSignedOutHandler(signedOut); }, [signedOut]);

  // On page load: if a refresh token exists, trade it for an access token and load the profile.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (tokens.refresh) {
        try {
          await refreshAccess();
          const { data } = await api.get("/auth/me/");
          if (!cancelled) setUser(data);
        } catch { tokens.clear(); }
      }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  const accept = (data) => { tokens.set(data.access, data.refresh); setUser(data.user); };
  const value = useMemo(() => ({
    user, loading, setUser,
    async login(email, password) { accept((await api.post("/auth/login/", { email, password })).data); },
    async register(body) { accept((await api.post("/auth/register/", body)).data); },
    async logout() {
      try { await api.post("/auth/logout/", { refresh: tokens.refresh || "" }); } catch { /* signing out locally anyway */ }
      signedOut();
    },
    async logoutAll() { try { await api.post("/auth/logout-all/"); } finally { signedOut(); } },
    acceptTokens(data) { tokens.set(data.access, data.refresh); },
  }), [user, loading, signedOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

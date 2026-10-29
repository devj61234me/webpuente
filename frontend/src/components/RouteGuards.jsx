import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Spinner } from "./ui";

export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Loading your account…" className="min-h-screen" />;
  return user ? <Outlet /> : <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
}

export function PublicOnly() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner label="Loading…" className="min-h-screen" />;
  return user ? <Navigate to="/dashboard" replace /> : <Outlet />;
}

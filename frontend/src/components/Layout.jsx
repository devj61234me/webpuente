import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { FolderKanban, LayoutDashboard, LogOut, Menu, UserCircle, X } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { classNames } from "../lib/format";

export function Logo({ light = false }) {
  return (
    <span className="flex items-center gap-2">
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden><rect width="32" height="32" rx="7" fill={light ? "#fff" : "#1f7b73"} />
        <path d="M5 21h22M8 21v-5a8 8 0 0 1 16 0v5M16 8v13M11 12v9M21 12v9" stroke={light ? "#1f7b73" : "#fff"} strokeWidth="2" fill="none" strokeLinecap="round" /></svg>
      <span className="text-lg font-semibold tracking-tight">WebPuente</span>
    </span>
  );
}

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/profile", label: "Profile", icon: UserCircle },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const link = ({ isActive }) => classNames("flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium", isActive ? "bg-brand-50 text-brand-700" : "text-ink-700 hover:bg-ink-100");
  const nav = (
    <nav className="space-y-1" aria-label="Main">
      {NAV.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} className={link} onClick={() => setOpen(false)}><Icon className="h-4 w-4" aria-hidden />{label}</NavLink>
      ))}
    </nav>
  );
  const signOut = async () => { await logout(); navigate("/login"); };
  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-60 shrink-0 border-r border-ink-200 bg-white p-4 lg:flex lg:flex-col">
        <Link to="/dashboard" className="mb-6 text-ink-900"><Logo /></Link>
        {nav}
        <div className="mt-auto border-t border-ink-100 pt-3">
          <p className="truncate px-1 text-xs text-ink-500" title={user?.email}>{user?.email}</p>
          <button onClick={signOut} className="btn-ghost mt-1 w-full justify-start"><LogOut className="h-4 w-4" aria-hidden />Sign out</button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-ink-200 bg-white px-4 py-3 lg:hidden">
          <Link to="/dashboard" className="text-ink-900"><Logo /></Link>
          <button className="btn-ghost" onClick={() => setOpen(!open)} aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open}>
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </header>
        {open && (
          <div className="border-b border-ink-200 bg-white p-3 lg:hidden">
            {nav}
            <button onClick={signOut} className="btn-ghost mt-2 w-full justify-start"><LogOut className="h-4 w-4" aria-hidden />Sign out</button>
          </div>
        )}
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-8"><Outlet /></main>
      </div>
    </div>
  );
}

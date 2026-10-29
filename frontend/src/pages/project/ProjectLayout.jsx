import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { api, errorInfo } from "../../api/client";
import { classNames } from "../../lib/format";
import { Notice, Spinner } from "../../components/ui";

const ProjectContext = createContext(null);
export const useProject = () => useContext(ProjectContext);

const TABS = [
  ["", "Overview", true], ["import", "Import URLs"], ["review", "Review"], ["quality", "Quality"], ["export", "Export"], ["activity", "Activity"], ["settings", "Settings"],
];

export default function ProjectLayout() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0); // bump to make child pages re-read their data
  const mine = useRef(0);

  const reload = useCallback(async () => {
    const n = ++mine.current;
    try {
      const { data } = await api.get(`/projects/${projectId}/`);
      if (n === mine.current) { setProject(data); setError(""); }
    } catch (err) {
      if (n !== mine.current) return;
      const info = errorInfo(err);
      if (info.status === 404) navigate("/projects", { replace: true });
      else setError(info.message);
    }
  }, [projectId, navigate]);
  const refresh = useCallback(async () => { await reload(); setVersion((v) => v + 1); }, [reload]);

  useEffect(() => { setProject(null); reload(); return () => { mine.current++; }; }, [reload]);

  if (error && !project) return <Notice tone="error">{error}</Notice>;
  if (!project) return <Spinner />;
  return (
    <ProjectContext.Provider value={{ project, reload, refresh, version, setProject }}>
      <Link to="/projects" className="mb-2 inline-flex items-center gap-1 text-sm text-ink-500 hover:text-ink-900"><ChevronLeft className="h-4 w-4" aria-hidden />All projects</Link>
      <h1 className="text-xl font-semibold text-ink-900">{project.name}</h1>
      <p className="mb-4 truncate text-sm text-ink-500">{project.old_site_url} → {project.new_site_url}</p>
      <nav aria-label="Project sections" className="mb-6 flex gap-1 overflow-x-auto border-b border-ink-200">
        {TABS.map(([to, label, end]) => (
          <NavLink key={to} to={to} end={!!end}
            className={({ isActive }) => classNames("whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium", isActive ? "border-brand-600 text-brand-700" : "border-transparent text-ink-500 hover:text-ink-900")}>
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </ProjectContext.Provider>
  );
}

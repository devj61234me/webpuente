import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useGet } from "../lib/useApi";
import { fmtDate, fmtNumber } from "../lib/format";
import { Card, EmptyState, Notice, PageHeader, ProgressBar, Spinner, Stat } from "../components/ui";

export default function Dashboard() {
  const { data, loading, error, reload } = useGet("/dashboard/");
  if (loading) return <Spinner />;
  if (error) return <Notice tone="error">{error} <button className="underline" onClick={() => reload()}>Try again</button></Notice>;
  const { totals, projects } = data;
  const chart = projects.slice(0, 8).map((p) => ({ name: p.name.length > 18 ? `${p.name.slice(0, 17)}…` : p.name, Approved: p.approved, Pending: p.pending }));

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Everything here is calculated from your own projects."
        actions={<Link to="/projects" className="btn-primary">Open projects</Link>} />
      {projects.length === 0 ? (
        <Card><EmptyState title="No projects yet" action={<Link to="/projects" className="btn-primary">Create your first project</Link>}>
          A project holds the old website's URLs, the new website's URLs and your redirect decisions.</EmptyState></Card>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat label="Projects" value={fmtNumber(totals.projects)} />
            <Stat label="Old URLs" value={fmtNumber(totals.old_urls)} />
            <Stat label="New URLs" value={fmtNumber(totals.new_urls)} />
            <Stat label="Approved" value={fmtNumber(totals.approved)} />
            <Stat label="Waiting for review" value={fmtNumber(totals.pending)} tone={totals.pending ? "warn" : undefined} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Review progress by project">
              <div className="h-64" role="img" aria-label="Bar chart of approved and pending mappings per project">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ left: -10 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip /><Legend />
                    <Bar dataKey="Approved" stackId="a" fill="#1f7b73" />
                    <Bar dataKey="Pending" stackId="a" fill="#b7c1c9" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title="Projects" pad={false}>
              <ul className="divide-y divide-ink-100">
                {projects.map((p) => (
                  <li key={p.id} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <Link to={`/projects/${p.id}`} className="truncate font-medium text-brand-700 hover:underline">{p.name}</Link>
                      <span className="shrink-0 text-xs text-ink-500">{fmtDate(p.updated_at)}</span>
                    </div>
                    <div className="mt-2 flex items-center gap-3">
                      <div className="flex-1"><ProgressBar value={p.review_completion_percent} label={`${p.name} review progress`} /></div>
                      <span className="w-24 text-right text-xs text-ink-500">{p.approved}/{p.old_count} approved</span>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

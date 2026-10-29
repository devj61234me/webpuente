import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Loader2, Play } from "lucide-react";
import { toast } from "react-toastify";
import { api, errorInfo, errorMessage } from "../../api/client";
import { useGet } from "../../lib/useApi";
import { fmtDate, fmtNumber } from "../../lib/format";
import { Card, EmptyState, Notice, ProgressBar, Spinner, Stat } from "../../components/ui";
import { useProject } from "./ProjectLayout";

const BAND_COLORS = { high: "#1f7b73", medium: "#e0a526", low: "#e8772e", unmatched: "#b7c1c9" };

export default function Overview() {
  const { project, reload, version } = useProject();
  const { data: stats, loading, error, reload: reloadStats } = useGet(`/projects/${project.id}/dashboard/`);
  const [busy, setBusy] = useState(false);
  const run = project.latest_run;
  const active = run && ["queued", "running"].includes(run.status);
  const timer = useRef(null);

  // Poll while an analysis is running; stop as soon as it is done.
  useEffect(() => {
    if (!active) return undefined;
    timer.current = setInterval(async () => { await reload(); reloadStats(true); }, 2500);
    return () => clearInterval(timer.current);
  }, [active, reload, reloadStats]);
  useEffect(() => { if (version) reloadStats(true); }, [version, reloadStats]);

  const start = async () => {
    setBusy(true);
    try { await api.post(`/projects/${project.id}/analyze/`); toast.info("Analysis started."); await reload(); reloadStats(true); }
    catch (err) { const i = errorInfo(err); toast.error(i.message); if (i.code === "analysis_in_progress") reload(); } finally { setBusy(false); }
  };

  if (loading && !stats) return <Spinner />;
  if (error) return <Notice tone="error">{error}</Notice>;
  const ready = stats.total_old > 0 && stats.total_new > 0;
  const bandData = ["high", "medium", "low", "unmatched"].map((k) => ({ name: { high: "High", medium: "Medium", low: "Low", unmatched: "No match" }[k], value: stats.bands[k], key: k })).filter((d) => d.value > 0);
  const history = stats.history.map((h, i) => ({ ...h, label: `Run ${i + 1}` }));

  return (
    <div className="space-y-6">
      {!ready && (
        <Card><EmptyState title="Add both URL lists to get started" action={<Link to="import" className="btn-primary">Import URLs</Link>}>
          You need the old site's URLs and the new site's URLs. {fmtNumber(stats.total_old)} old and {fmtNumber(stats.total_new)} new URLs are loaded so far.</EmptyState></Card>
      )}
      {ready && (
        <Card title="Matching" actions={<button className="btn-primary" onClick={start} disabled={busy || active}>
          {(busy || active) ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}{stats.analyzed ? "Run again" : "Find matches"}</button>}>
          {active ? (
            <div className="space-y-2"><p className="text-sm text-ink-700">Analysis {run.status === "queued" ? "is waiting to start…" : "is running…"}</p><ProgressBar value={run.progress} label="Analysis progress" /></div>
          ) : run?.status === "failed" ? (
            <Notice tone="error" title="The last analysis did not finish">{run.error_message || "Please try again."}</Notice>
          ) : run ? (
            <div className="text-sm text-ink-700">
              Last run finished {fmtDate(run.finished_at)}. Your approved and manual decisions are kept when you run again.
              {run.stats?.warnings?.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-amber-800">{run.stats.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
            </div>
          ) : <p className="text-sm text-ink-500">Nothing has been matched yet. Suggestions are never approved automatically.</p>}
        </Card>
      )}

      {stats.analyzed && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Old URLs" value={fmtNumber(stats.total_old)} hint={`${fmtNumber(stats.total_new)} new URLs`} />
            <Stat label="With a destination" value={`${stats.coverage_percent}%`} hint={`${fmtNumber(stats.unmatched)} without`} />
            <Stat label="Reviewed" value={`${stats.review_completion_percent}%`} hint={`${fmtNumber(stats.approved)} approved · ${fmtNumber(stats.rejected)} rejected`} />
            <Stat label="Waiting for review" value={fmtNumber(stats.pending)} tone={stats.pending ? "warn" : undefined} hint={<Link className="text-brand-700 hover:underline" to="review">Open review</Link>} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Match confidence">
              <div className="h-60" role="img" aria-label="Pie chart of high, medium, low and no-match counts">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart><Pie data={bandData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={2}>
                    {bandData.map((d) => <Cell key={d.key} fill={BAND_COLORS[d.key]} />)}</Pie><Tooltip /><Legend /></PieChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-ink-500">Scores are a guide to what to check first, not proof that two pages are equivalent.</p>
            </Card>
            <Card title="Risks found">
              {stats.quality_checked_at ? (
                <>
                  <div className="h-48" role="img" aria-label="Bar chart of risks by severity">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={["high", "medium", "low", "info"].map((k) => ({ name: k, value: stats.risks[k] }))}>
                        <CartesianGrid vertical={false} strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip />
                        <Bar dataKey="value" fill="#1f7b73" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="mt-2 text-xs text-ink-500">Checked {fmtDate(stats.quality_checked_at)}. <Link className="text-brand-700 hover:underline" to="quality">See details</Link></p>
                </>
              ) : <EmptyState title="Not checked yet" action={<Link to="quality" className="btn-secondary">Run quality checks</Link>}>Check for loops, chains, duplicates and missing destinations.</EmptyState>}
            </Card>
          </div>
          {history.length > 1 && (
            <Card title="Confidence over runs">
              <div className="h-56" role="img" aria-label="Line chart of average match score per run">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={history}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" /><YAxis domain={[0, 100]} /><Tooltip />
                    <Line type="monotone" dataKey="average_score" name="Average score" stroke="#1f7b73" strokeWidth={2} /></LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

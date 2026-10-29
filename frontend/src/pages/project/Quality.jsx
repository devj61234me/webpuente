import { useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, ShieldCheck } from "lucide-react";
import { toast } from "react-toastify";
import { api, errorMessage } from "../../api/client";
import { useGet } from "../../lib/useApi";
import { KIND_LABEL, fmtDate } from "../../lib/format";
import { Card, EmptyState, Notice, Pagination, SeverityBadge, Spinner, Stat } from "../../components/ui";
import { useProject } from "./ProjectLayout";

export default function Quality() {
  const { project, refresh } = useProject();
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState("");
  const [kind, setKind] = useState("");
  const [busy, setBusy] = useState(false);
  const { data, loading, error, reload } = useGet(`/projects/${project.id}/quality/`, { page, page_size: 50, severity, kind });

  const run = async () => {
    setBusy(true);
    try { const { data: s } = await api.post(`/projects/${project.id}/quality/run/`); toast.success(`Checked: ${s.total} finding${s.total === 1 ? "" : "s"}.`); setPage(1); await reload(true); await refresh(); }
    catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  };

  if (loading && !data) return <Spinner />;
  if (error && !data) return <Notice tone="error">{error}</Notice>;
  const sev = data.by_severity || {};

  return (
    <div className="space-y-6">
      <Card title="Quality checks" actions={<button className="btn-primary" onClick={run} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ShieldCheck className="h-4 w-4" aria-hidden />}{data.checked_at ? "Check again" : "Run checks"}</button>}>
        <p className="text-sm text-ink-700">
          {data.checked_at ? <>Last checked {fmtDate(data.checked_at)}.</> : "Not checked yet."} Looks at the current proposal (approved, pending, and rejected rows are treated differently) for loops, chains, duplicates, missing destinations and similar problems.
        </p>
        {data.stale && data.checked_at && <div className="mt-3"><Notice tone="warn">You changed decisions after the last check. Run the checks again to refresh these results.</Notice></div>}
      </Card>

      {data.checked_at && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="High" value={sev.high || 0} tone={sev.high ? "bad" : undefined} hint="Fix before using" />
          <Stat label="Medium" value={sev.medium || 0} tone={sev.medium ? "warn" : undefined} hint="Review" />
          <Stat label="Low" value={sev.low || 0} />
          <Stat label="Info" value={sev.info || 0} />
        </div>
      )}

      {data.checked_at && (
        <Card pad={false} title="Findings" actions={
          <div className="flex gap-2">
            <select className="input w-auto py-1 text-xs" aria-label="Severity" value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }}>
              <option value="">All severities</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option><option value="info">Info</option></select>
            <select className="input w-auto py-1 text-xs" aria-label="Kind" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }}>
              <option value="">All kinds</option>{Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          </div>}>
          {data.results.length === 0 ? <EmptyState title={severity || kind ? "No findings match these filters" : "No problems found"}>{severity || kind ? "" : "That is good news, but see the list below of what these checks cannot know."}</EmptyState> : (
            <>
              <div className="overflow-x-auto"><table className="w-full min-w-[640px]"><thead className="border-b border-ink-100 bg-ink-50"><tr><th className="th">Severity</th><th className="th">Problem</th><th className="th">URL</th><th className="th">Details</th></tr></thead>
                <tbody className="divide-y divide-ink-100">{data.results.map((r) => (
                  <tr key={r.id}><td className="td"><SeverityBadge severity={r.severity} /></td><td className="td whitespace-nowrap">{KIND_LABEL[r.kind] || r.kind}{r.source === "supplied_data" && <div className="text-xs text-ink-500">in your data</div>}</td>
                    <td className="td max-w-xs"><span className="block truncate font-mono text-xs" title={r.old_url || r.new_url}>{r.old_url || r.new_url || "—"}</span>{r.old_url && r.new_url && <span className="block truncate font-mono text-xs text-ink-500" title={r.new_url}>→ {r.new_url}</span>}</td>
                    <td className="td text-xs text-ink-700">{r.message}</td></tr>))}</tbody></table></div>
              <Pagination page={page} pageSize={50} count={data.count} onPage={setPage} />
            </>
          )}
        </Card>
      )}

      <Card title="What these checks cannot tell you">
        <ul className="list-disc space-y-1 pl-5 text-sm text-ink-700">{(data.not_checked || []).map((t) => <li key={t}>{t}</li>)}</ul>
        <p className="mt-3 text-xs text-ink-500">Next: <Link className="text-brand-700 hover:underline" to="../export">export your redirects</Link> once the high-severity findings are resolved.</p>
      </Card>
    </div>
  );
}

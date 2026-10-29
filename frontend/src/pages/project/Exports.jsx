import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "react-toastify";
import { api, errorInfo } from "../../api/client";
import { useGet } from "../../lib/useApi";
import { fmtDate, fmtNumber, saveBlob } from "../../lib/format";
import { Badge, Card, ConfirmDialog, Field, Notice, Pagination, Spinner } from "../../components/ui";
import { useProject } from "./ProjectLayout";

const FORMATS = [
  ["csv", "CSV", "Spreadsheet-friendly list of approved redirects."],
  ["xlsx", "Excel (.xlsx)", "Approved redirects plus a summary sheet."],
  ["json", "JSON", "For scripts and other tools."],
  ["htaccess", "Apache (.htaccess)", "mod_rewrite rules for Apache (site's top folder)."],
  ["nginx", "Nginx map", "A map file to include in your nginx configuration."],
  ["report", "Full report (.xlsx)", "Every row (approved, pending, rejected) plus risks."],
];

export default function Exports() {
  const { project } = useProject();
  const [fmt, setFmt] = useState("csv");
  const [includePending, setIncludePending] = useState(false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [last, setLast] = useState(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const list = useGet(`/projects/${project.id}/exports/`, { page, page_size: 10 });
  const isConfig = fmt === "htaccess" || fmt === "nginx";

  const create = async (confirmPending = false) => {
    setBusy(true); setError(""); setLast(null);
    try {
      const { data } = await api.post(`/projects/${project.id}/exports/`, {
        format: fmt, include_pending: includePending, confirm_pending: confirmPending, ...(status ? { redirect_status: Number(status) } : {}),
      });
      setLast(data); setConfirm(false); await list.reload(true);
      await download(data);
    } catch (err) {
      const info = errorInfo(err);
      if (info.code === "pending_confirmation_required") setConfirm(true); else setError(info.message);
    } finally { setBusy(false); }
  };

  const download = async (job) => {
    try {
      const res = await api.get(`/projects/${project.id}/exports/${job.id}/download/`, { responseType: "blob" });
      saveBlob(res.data, job.filename);
    } catch { toast.error("The file could not be downloaded. Use the history list below."); }
  };

  return (
    <div className="space-y-6">
      <Card title="Create an export">
        <div className="space-y-4">
          <fieldset>
            <legend className="label">Format</legend>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {FORMATS.map(([value, label, hint]) => (
                <label key={value} className={`flex cursor-pointer gap-2 rounded-lg border p-3 text-sm ${fmt === value ? "border-brand-500 bg-brand-50" : "border-ink-200 hover:bg-ink-50"}`}>
                  <input type="radio" name="fmt" className="mt-1" checked={fmt === value} onChange={() => setFmt(value)} />
                  <span><span className="block font-medium">{label}</span><span className="text-xs text-ink-500">{hint}</span></span>
                </label>
              ))}
            </div>
          </fieldset>
          {fmt !== "report" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Redirect type" htmlFor="ex-status" hint="Leave as 'each row's own setting' unless you want to force one type for the file.">
                <select id="ex-status" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
                  <option value="">Each row's own setting</option><option value="301">Force 301 – Permanent</option><option value="302">Force 302 – Temporary</option><option value="307">Force 307</option><option value="308">Force 308</option></select>
              </Field>
              <label className="flex items-start gap-2 self-end pb-2 text-sm"><input type="checkbox" className="mt-1" checked={includePending} onChange={(e) => setIncludePending(e.target.checked)} /><span>Also include <strong>pending</strong> (not yet approved) mappings</span></label>
            </div>
          )}
          {isConfig && <Notice tone="warn" title="Test before you go live">Generated server rules are a starting point. Rows with loops, self-redirects or excluded paths are left out and listed as warnings. Always test on a staging copy of your server first.</Notice>}
          {error && <Notice tone="error">{error}</Notice>}
          <button className="btn-primary" onClick={() => create(false)} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Download className="h-4 w-4" aria-hidden />}Create and download</button>
          {last && (
            <Notice tone="ok" title={`${last.filename} — ${fmtNumber(last.row_count)} rows${last.skipped_count ? `, ${last.skipped_count} skipped` : ""}`}>
              {last.warnings.length > 0 && <ul className="mt-1 list-disc space-y-0.5 pl-5">{last.warnings.slice(0, 8).map((w, i) => <li key={i}>{w}</li>)}</ul>}
              <p className="mt-1 break-all text-xs opacity-70">SHA-256: {last.sha256}</p>
            </Notice>
          )}
        </div>
      </Card>

      <Card title="Previous exports" pad={false}>
        {list.loading && !list.data ? <Spinner /> : list.data?.results.length ? (
          <>
            <div className="overflow-x-auto"><table className="w-full"><thead className="border-b border-ink-100 bg-ink-50"><tr><th className="th">Created</th><th className="th">Format</th><th className="th">Rows</th><th className="th">File</th><th className="th" /></tr></thead>
              <tbody className="divide-y divide-ink-100">{list.data.results.map((j) => (
                <tr key={j.id}><td className="td whitespace-nowrap">{fmtDate(j.created_at)}</td><td className="td"><Badge>{j.fmt}</Badge></td><td className="td">{fmtNumber(j.row_count)}{j.skipped_count ? ` (+${j.skipped_count} skipped)` : ""}</td>
                  <td className="td max-w-xs truncate">{j.filename}{j.options?.include_pending && <span className="ml-2 text-xs text-amber-700">includes pending</span>}</td>
                  <td className="td text-right"><button className="btn-secondary btn-sm" onClick={() => download(j)}><Download className="h-3.5 w-3.5" aria-hidden />Download</button></td></tr>))}</tbody></table></div>
            <Pagination page={page} pageSize={10} count={list.data.count} onPage={setPage} />
          </>
        ) : <p className="px-4 py-6 text-sm text-ink-500">No exports yet. Approve some mappings in the review screen first.</p>}
      </Card>

      <ConfirmDialog open={confirm} title="Include mappings that are not approved?" confirmLabel="Include pending" busy={busy} onClose={() => setConfirm(false)} onConfirm={() => create(true)}>
        <p>Pending mappings are only suggestions. Redirects built from them could send visitors to the wrong page. The file will carry a warning.</p>
      </ConfirmDialog>
    </div>
  );
}

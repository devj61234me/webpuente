import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { FileUp, Loader2 } from "lucide-react";
import { toast } from "react-toastify";
import { api, errorInfo, errorMessage } from "../../api/client";
import { useGet } from "../../lib/useApi";
import { fmtDate, fmtNumber } from "../../lib/format";
import { Badge, Card, ConfirmDialog, Field, Notice, Pagination, Spinner } from "../../components/ui";
import { useProject } from "./ProjectLayout";

const FIELD_LABELS = {
  url: "URL (required)", title: "Page title", meta_description: "Meta description", h1: "Main heading (H1)", canonical_url: "Canonical URL", status_code: "Status code",
};

export default function ImportPage() {
  const { project, refresh } = useProject();
  const { data: config } = useGet("/config/");
  const [kind, setKind] = useState("old");
  const [mode, setMode] = useState("append");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [columnMap, setColumnMap] = useState({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const history = useGet(`/projects/${project.id}/imports/`, { page: historyPage, page_size: 10 });
  const fileInput = useRef(null);

  const body = () => {
    if (file) { const f = new FormData(); f.append("kind", kind); f.append("file", file); return f; }
    return { kind, text };
  };
  const reset = () => { setPreview(null); setColumnMap({}); setError(""); };
  const hasInput = !!file || text.trim().length > 0;

  const doPreview = async () => {
    setBusy("preview"); setError(""); setResult(null);
    try {
      const { data } = await api.post(`/projects/${project.id}/imports/preview/`, body());
      setPreview(data); setColumnMap(data.suggested_mapping || {});
    } catch (err) { setError(errorMessage(err)); setPreview(null); } finally { setBusy(""); }
  };

  const doImport = async () => {
    setBusy("import"); setError("");
    try {
      let payload = body();
      if (payload instanceof FormData) { payload.append("mode", mode); payload.append("column_map", JSON.stringify(columnMap)); }
      else payload = { ...payload, mode, column_map: columnMap };
      const { data } = await api.post(`/projects/${project.id}/imports/`, payload);
      setResult(data); reset(); setText(""); setFile(null); if (fileInput.current) fileInput.current.value = "";
      toast.success(`${fmtNumber(data.imported_count + data.updated_count)} URLs saved.`);
      await refresh(); history.reload(true);
    } catch (err) {
      const info = errorInfo(err);
      setError(info.message);
    } finally { setBusy(""); setConfirmReplace(false); }
  };

  const setCol = (field) => (e) => setColumnMap({ ...columnMap, [field]: e.target.value === "" ? null : Number(e.target.value) });
  const startImport = () => (mode === "replace" ? setConfirmReplace(true) : doImport());

  return (
    <div className="space-y-6">
      <Card title="Add URLs">
        <div className="space-y-4">
          <p className="text-sm text-ink-500">
            Your project has <strong>{fmtNumber(project.old_count)}</strong> old and <strong>{fmtNumber(project.new_count)}</strong> new URLs.
            Upload a CSV or Excel export (for example from a site crawler), or paste one URL per line. Limit: {config?.max_upload_mb ?? 5} MB and {fmtNumber(config?.max_import_rows ?? 20000)} rows per import.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Which list is this?" htmlFor="kind">
              <select id="kind" className="input" value={kind} onChange={(e) => { setKind(e.target.value); reset(); }}>
                <option value="old">Old website URLs (pages that need a redirect)</option>
                <option value="new">New website URLs (possible destinations)</option>
              </select>
            </Field>
            <Field label="If URLs already exist" htmlFor="mode" hint={mode === "replace" ? "Replacing removes the current list and any decisions for it." : "New URLs are added; known URLs are updated."}>
              <select id="mode" className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="append">Add to the existing list</option>
                <option value="replace">Replace the existing list</option>
              </select>
            </Field>
          </div>
          <Field label="Upload a file (CSV, XLSX)" htmlFor="file">
            <input id="file" ref={fileInput} type="file" accept=".csv,.xlsx,.txt,text/csv" className="input file:mr-3 file:rounded file:border-0 file:bg-brand-50 file:px-3 file:py-1 file:text-brand-700"
              onChange={(e) => { setFile(e.target.files[0] || null); if (e.target.files[0]) setText(""); reset(); }} />
          </Field>
          <Field label="…or paste URLs (one per line)" htmlFor="paste">
            <textarea id="paste" className="input font-mono text-xs" rows={6} value={text} placeholder={"https://old.example.com/about\nhttps://old.example.com/contact"}
              onChange={(e) => { setText(e.target.value); if (e.target.value) { setFile(null); if (fileInput.current) fileInput.current.value = ""; } reset(); }} />
          </Field>
          {error && <Notice tone="error">{error}</Notice>}
          <button className="btn-secondary" onClick={doPreview} disabled={!hasInput || busy}>{busy === "preview" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <FileUp className="h-4 w-4" aria-hidden />}Preview</button>
        </div>
      </Card>

      {preview && (
        <Card title="Check the columns">
          <p className="mb-3 text-sm text-ink-500">{fmtNumber(preview.total_rows)} rows found{preview.filename ? ` in ${preview.filename}` : ""}. Tell WebPuente which column holds what. Only the URL is required; titles and headings make matching better.</p>
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(FIELD_LABELS).map(([field, label]) => (
              <Field key={field} label={label} htmlFor={`col-${field}`}>
                <select id={`col-${field}`} className="input" value={columnMap[field] ?? ""} onChange={setCol(field)}>
                  <option value="">{field === "url" ? "Choose a column…" : "Not in this file"}</option>
                  {preview.headers.map((h, i) => <option key={i} value={i}>{h || `Column ${i + 1}`}</option>)}
                </select>
              </Field>
            ))}
          </div>
          <div className="mb-4 overflow-x-auto rounded-lg border border-ink-200">
            <table className="w-full text-xs">
              <thead className="bg-ink-50"><tr>{preview.headers.map((h, i) => <th key={i} className="th">{h || `Column ${i + 1}`}</th>)}</tr></thead>
              <tbody className="divide-y divide-ink-100">{preview.sample.map((row, r) => <tr key={r}>{row.map((cell, c) => <td key={c} className="max-w-xs truncate px-3 py-1.5" title={cell}>{cell}</td>)}</tr>)}</tbody>
            </table>
          </div>
          <button className="btn-primary" onClick={startImport} disabled={busy || columnMap.url == null}>{busy === "import" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Import {fmtNumber(preview.total_rows)} rows as {kind === "old" ? "old" : "new"} URLs</button>
        </Card>
      )}

      {result && (
        <Card title="Import finished">
          <div className="flex flex-wrap gap-2 text-sm">
            <Badge tone="approved">{fmtNumber(result.imported_count)} added</Badge>
            {result.updated_count > 0 && <Badge tone="info">{fmtNumber(result.updated_count)} updated</Badge>}
            {result.duplicate_count > 0 && <Badge tone="medium">{fmtNumber(result.duplicate_count)} duplicates skipped</Badge>}
            {result.invalid_count > 0 && <Badge tone="rejected">{fmtNumber(result.invalid_count)} invalid</Badge>}
            {result.removed_count > 0 && <Badge tone="neutral">{fmtNumber(result.removed_count)} replaced</Badge>}
          </div>
          {result.needs_reanalysis && <div className="mt-3"><Notice tone="warn">Your URL lists changed. Run the matching again from the <Link className="underline" to="..">Overview</Link> to update suggestions. Your decisions are kept.</Notice></div>}
          {result.errors?.length > 0 && (
            <details className="mt-3"><summary className="cursor-pointer text-sm font-medium text-ink-700">Rows that were skipped or ignored ({result.errors.length}{result.errors_truncated ? "+" : ""})</summary>
              <div className="mt-2 max-h-64 overflow-auto rounded-lg border border-ink-200"><table className="w-full text-xs"><thead className="bg-ink-50"><tr><th className="th">Row</th><th className="th">Value</th><th className="th">Reason</th></tr></thead>
                <tbody className="divide-y divide-ink-100">{result.errors.map((e, i) => <tr key={i}><td className="td">{e.row}</td><td className="td max-w-xs truncate font-mono">{e.value}</td><td className="td">{e.reason}</td></tr>)}</tbody></table></div>
            </details>
          )}
        </Card>
      )}

      {config?.website_fetch_enabled && <FetchCard project={project} limit={config.fetch_max_urls_per_request} onDone={refresh} />}

      <Card title="Import history" pad={false}>
        {history.loading && !history.data ? <Spinner /> : history.data?.results.length ? (
          <>
            <div className="overflow-x-auto"><table className="w-full"><thead className="border-b border-ink-100 bg-ink-50"><tr><th className="th">When</th><th className="th">List</th><th className="th">Source</th><th className="th">Rows</th><th className="th">Added</th><th className="th">Skipped</th></tr></thead>
              <tbody className="divide-y divide-ink-100">{history.data.results.map((b) => (
                <tr key={b.id}><td className="td whitespace-nowrap">{fmtDate(b.created_at)}</td><td className="td">{b.kind}</td><td className="td">{b.filename || b.source}</td>
                  <td className="td">{fmtNumber(b.total_rows)}</td><td className="td">{fmtNumber(b.imported_count)}</td><td className="td">{fmtNumber(b.errors_total)}</td></tr>))}</tbody></table></div>
            <Pagination page={historyPage} pageSize={10} count={history.data.count} onPage={setHistoryPage} />
          </>
        ) : <p className="px-4 py-6 text-sm text-ink-500">No imports yet.</p>}
      </Card>

      <ConfirmDialog open={confirmReplace} danger title="Replace the existing list?" confirmLabel="Replace" busy={busy === "import"} onClose={() => setConfirmReplace(false)} onConfirm={doImport}>
        <p>This removes the current {kind} URL list. Decisions that point to removed URLs are reset to pending. This cannot be undone.</p>
      </ConfirmDialog>
    </div>
  );
}

function FetchCard({ project, limit, onDone }) {
  const [side, setSide] = useState("old");
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState(null);
  const run = async () => {
    setBusy(true); setOut(null);
    try { const { data } = await api.post(`/projects/${project.id}/fetch-metadata/`, { side }); setOut(data); onDone(); }
    catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  };
  return (
    <Card title="Read page titles from the live website (optional)">
      <p className="mb-3 text-sm text-ink-500">Fetches up to {limit} pages that have no title yet, respecting robots.txt, to improve matching. Only public websites can be read. Run it again for the next batch.</p>
      <div className="flex flex-wrap items-center gap-3">
        <select className="input w-auto" value={side} onChange={(e) => setSide(e.target.value)} aria-label="Which list to read">
          <option value="old">Old site URLs</option><option value="new">New site URLs</option></select>
        <button className="btn-secondary" onClick={run} disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Fetch titles</button>
      </div>
      {out && <p className="mt-3 text-sm">{out.fetched} read, {out.failed} could not be read.</p>}
      {out?.results?.some((r) => r.error) && <ul className="mt-2 max-h-40 list-disc overflow-auto pl-5 text-xs text-ink-500">{out.results.filter((r) => r.error).slice(0, 10).map((r) => <li key={r.id}>{r.url}: {r.error}</li>)}</ul>}
    </Card>
  );
}

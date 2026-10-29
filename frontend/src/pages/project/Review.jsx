import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Check, Loader2, RotateCcw, Search, Undo2, X } from "lucide-react";
import { toast } from "react-toastify";
import { api, errorInfo, errorMessage } from "../../api/client";
import { useGet } from "../../lib/useApi";
import { EVIDENCE_LABEL, MATCH_LABEL, classNames, fmtNumber } from "../../lib/format";
import { BandBadge, Card, ConfirmDialog, EmptyState, Field, Modal, Notice, Pagination, Spinner, StatusBadge } from "../../components/ui";
import { useProject } from "./ProjectLayout";

const PAGE_SIZE = 50;
const FILTER_KEYS = ["search", "band", "status", "match_type", "unmatched", "ambiguous", "has_risk", "origin", "ordering"];

export default function Review() {
  const { project, refresh, version } = useProject();
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(new Set());
  const [openId, setOpenId] = useState(null);
  const [confirm, setConfirm] = useState(null); // {kind:'low'|'many', row, body}
  const [bulk, setBulk] = useState(null);       // 'approve' | 'reject' | 'reset'
  const [busy, setBusy] = useState(false);

  const filters = useMemo(() => Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) || ""]).filter(([, v]) => v)), [params]);
  const query = useMemo(() => ({ ...filters, page, page_size: PAGE_SIZE }), [filters, page]);
  const { data, loading, error, reload } = useGet(`/projects/${project.id}/mappings/`, query);
  const [searchText, setSearchText] = useState(filters.search || "");

  useEffect(() => { setSelected(new Set()); }, [query]);
  useEffect(() => { if (version) reload(true); }, [version, reload]);

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true }); setPage(1);
  };
  useEffect(() => { // debounce search typing
    const t = setTimeout(() => { if (searchText !== (filters.search || "")) setFilter("search", searchText.trim()); }, 350);
    return () => clearTimeout(t);
  }, [searchText]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = data?.results || [];
  const onChanged = useCallback(async () => { await reload(true); await refresh(); }, [reload, refresh]);

  // ---- single-row actions (the server decides when a confirmation is needed; we only ask when it says so)
  const approve = async (row, extra = {}) => {
    setBusy(true);
    try {
      await api.post(`/projects/${project.id}/mappings/${row.id}/approve/`, extra);
      toast.success("Approved."); setConfirm(null); await onChanged();
    } catch (err) {
      const info = errorInfo(err);
      if (info.code === "low_confidence_confirmation_required") setConfirm({ kind: "low", row, body: extra, info });
      else if (info.code === "many_to_one_confirmation_required") setConfirm({ kind: "many", row, body: extra, info });
      else toast.error(info.message);
    } finally { setBusy(false); }
  };
  const act = async (row, action) => {
    setBusy(true);
    try { await api.post(`/projects/${project.id}/mappings/${row.id}/${action}/`); await onChanged(); if (action === "undo") toast.info("Change undone."); }
    catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  };

  const allOnPage = rows.length > 0 && rows.every((r) => selected.has(r.id));
  const toggle = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected(allOnPage ? new Set() : new Set(rows.map((r) => r.id)));
  const hasFilters = Object.keys(filters).some((k) => k !== "ordering");

  if (!data && loading) return <Spinner />;
  if (error && !data) return <Notice tone="error">{error}</Notice>;
  if (!hasFilters && data.count === 0) {
    return <Card><EmptyState title="Nothing to review yet" action={<Link to=".." className="btn-primary">Go to the overview</Link>}>
      Import both URL lists and run the matching first. Suggestions will appear here for you to check.</EmptyState></Card>;
  }

  return (
    <div className="space-y-4">
      <Card pad={false}>
        <div className="grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-6">
          <div className="relative lg:col-span-2">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-400" aria-hidden />
            <input className="input pl-8" placeholder="Search URLs…" aria-label="Search URLs" value={searchText} onChange={(e) => setSearchText(e.target.value)} />
          </div>
          <Select label="Confidence" value={filters.band} onChange={(v) => setFilter("band", v)} options={[["high", "High"], ["medium", "Medium"], ["low", "Low"], ["unmatched", "No match"]]} />
          <Select label="Status" value={filters.status} onChange={(v) => setFilter("status", v)} options={[["pending", "Pending"], ["approved", "Approved"], ["rejected", "Rejected"]]} />
          <Select label="Match type" value={filters.match_type} onChange={(v) => setFilter("match_type", v)} options={Object.entries(MATCH_LABEL).filter(([k]) => !["manual", "none"].includes(k))} />
          <Select label="Sort" value={filters.ordering} onChange={(v) => setFilter("ordering", v)} blank="Default" options={[["-score", "Highest score"], ["score", "Lowest score"], ["old_url", "Old URL A–Z"], ["status", "Status"]]} />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-ink-100 px-3 py-2 text-sm">
          {[["ambiguous", "Ambiguous only"], ["unmatched", "No destination only"], ["has_risk", "With risks only"]].map(([k, label]) => (
            <label key={k} className="flex items-center gap-1.5"><input type="checkbox" checked={filters[k] === "true"} onChange={(e) => setFilter(k, e.target.checked ? "true" : "")} />{label}</label>
          ))}
          <label className="flex items-center gap-1.5"><input type="checkbox" checked={filters.origin === "manual"} onChange={(e) => setFilter("origin", e.target.checked ? "manual" : "")} />Chosen by me</label>
          {hasFilters && <button className="btn-ghost btn-sm ml-auto" onClick={() => { setParams({}); setSearchText(""); setPage(1); }}>Clear filters</button>}
        </div>
      </Card>

      {selected.size > 0 && (
        <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm" role="region" aria-label="Bulk actions">
          <span className="font-medium">{selected.size} selected</span>
          <button className="btn-primary btn-sm" onClick={() => setBulk("approve")}><Check className="h-3.5 w-3.5" aria-hidden />Approve…</button>
          <button className="btn-secondary btn-sm" onClick={() => setBulk("reject")}><X className="h-3.5 w-3.5" aria-hidden />Reject…</button>
          <button className="btn-secondary btn-sm" onClick={() => setBulk("reset")}><RotateCcw className="h-3.5 w-3.5" aria-hidden />Reset to suggestion…</button>
          <button className="btn-ghost btn-sm ml-auto" onClick={() => setSelected(new Set())}>Clear selection</button>
        </div>
      )}

      <Card pad={false}>
        {rows.length === 0 ? <EmptyState title="No mappings match these filters" /> : (
          <div className={classNames("overflow-x-auto", loading && "opacity-60")}>
            <table className="w-full min-w-[860px]">
              <thead className="border-b border-ink-100 bg-ink-50"><tr>
                <th className="th w-8"><input type="checkbox" aria-label="Select all rows on this page" checked={allOnPage} onChange={toggleAll} /></th>
                <th className="th">Old URL</th><th className="th">Redirect to</th><th className="th">Score</th><th className="th">Match</th><th className="th">Status</th><th className="th w-40">Actions</th></tr></thead>
              <tbody className="divide-y divide-ink-100">
                {rows.map((r) => (
                  <tr key={r.id} className={classNames("hover:bg-ink-50", openId === r.id && "bg-brand-50/50")}>
                    <td className="td"><input type="checkbox" aria-label={`Select ${r.old_url.original}`} checked={selected.has(r.id)} onChange={() => toggle(r.id)} /></td>
                    <td className="td max-w-[260px]"><button className="block max-w-full truncate text-left text-brand-700 hover:underline" title={r.old_url.original} onClick={() => setOpenId(r.id)}>{r.old_url.original}</button>
                      {r.old_url.title && <div className="truncate text-xs text-ink-500">{r.old_url.title}</div>}</td>
                    <td className="td max-w-[260px]">{r.final_url ? <span className="block truncate" title={r.final_url}>{r.final_url}</span> : <span className="text-ink-400">No destination</span>}
                      {r.new_suggestion_differs && <div className="text-xs text-amber-700">Suggestion differs from your choice</div>}</td>
                    <td className="td whitespace-nowrap"><div className="flex items-center gap-2"><span className="tabular-nums">{r.score}</span><BandBadge band={r.band} />{r.ambiguous && <span className="text-xs text-amber-700" title="Another page scored almost as well">ambiguous</span>}</div></td>
                    <td className="td whitespace-nowrap text-xs text-ink-700">{MATCH_LABEL[r.match_type] || r.match_type}{r.risk_count > 0 && <span className="ml-1 text-amber-700" title="Quality checks found something">⚠ {r.risk_count}</span>}</td>
                    <td className="td"><StatusBadge status={r.status} /></td>
                    <td className="td"><div className="flex gap-1">
                      <button className="btn-secondary btn-sm" disabled={busy || !r.final_new_url_id || r.status === "approved"} onClick={() => approve(r)} aria-label={`Approve ${r.old_url.original}`}><Check className="h-3.5 w-3.5" aria-hidden /></button>
                      <button className="btn-secondary btn-sm" disabled={busy || r.status === "rejected"} onClick={() => act(r, "reject")} aria-label={`Reject ${r.old_url.original}`}><X className="h-3.5 w-3.5" aria-hidden /></button>
                      <button className="btn-ghost btn-sm" onClick={() => setOpenId(r.id)}>Details</button></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={page} pageSize={PAGE_SIZE} count={data.count} onPage={(p) => { setPage(p); window.scrollTo({ top: 0 }); }} />
      </Card>

      {openId && <DetailPanel key={openId} project={project} reviewId={openId} onClose={() => setOpenId(null)} onChanged={onChanged} onApprove={approve} />}

      <ConfirmDialog open={confirm?.kind === "low"} title="Low-confidence match" confirmLabel="Approve anyway" busy={busy}
        onClose={() => setConfirm(null)} onConfirm={() => approve(confirm.row, { ...confirm.body, confirm_low_confidence: true })}>
        <p>{confirm?.info?.message}</p><p className="break-all"><strong>{confirm?.row.old_url.original}</strong><br />→ {confirm?.row.final_url}</p>
      </ConfirmDialog>
      <ConfirmDialog open={confirm?.kind === "many"} title="Many old URLs to one page" confirmLabel="Yes, this is intended" busy={busy}
        onClose={() => setConfirm(null)} onConfirm={() => approve(confirm.row, { ...confirm.body, confirm_many_to_one: true })}>
        <p>{confirm?.info?.message}</p><p className="break-all">{confirm?.row.final_url}</p>
      </ConfirmDialog>
      <BulkDialog action={bulk} ids={[...selected]} project={project} onClose={() => setBulk(null)} onDone={async () => { setBulk(null); setSelected(new Set()); await onChanged(); }} />
    </div>
  );
}

function Select({ label, value, onChange, options, blank = "All" }) {
  return (
    <select className="input" aria-label={label} value={value || ""} onChange={(e) => onChange(e.target.value)}>
      <option value="">{label}: {blank}</option>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
}

function BulkDialog({ action, ids, project, onClose, onDone }) {
  const [includeLow, setIncludeLow] = useState(false);
  const [manyToOne, setManyToOne] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setIncludeLow(false); setManyToOne(false); }, [action]);
  const run = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/projects/${project.id}/mappings/bulk/`, { action, ids, confirm: true, include_low: includeLow, confirm_many_to_one: manyToOne });
      const skipped = Object.values(data.skipped).reduce((a, b) => a + b, 0);
      toast.success(`${data.updated} updated.${skipped ? ` ${skipped} skipped (see the filters to review them).` : ""}`);
      if (skipped) toast.warn(`Skipped: ${data.skipped.no_destination} without destination, ${data.skipped.low_confidence} low confidence, ${data.skipped.many_to_one} many-to-one.`, { autoClose: 9000 });
      onDone();
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  };
  const verb = { approve: "Approve", reject: "Reject", reset: "Reset" }[action];
  return (
    <ConfirmDialog open={!!action} title={`${verb} ${ids.length} mapping${ids.length === 1 ? "" : "s"}?`} confirmLabel={verb} danger={action === "reject"} busy={busy} onClose={onClose} onConfirm={run}>
      {action === "approve" && (<>
        <p>Approved mappings go into your exports. Rows without a destination are always skipped.</p>
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={includeLow} onChange={(e) => setIncludeLow(e.target.checked)} /><span>Include <strong>low-confidence</strong> matches. I have checked them.</span></label>
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={manyToOne} onChange={(e) => setManyToOne(e.target.checked)} /><span>Allow several old URLs to point to the same destination.</span></label>
      </>)}
      {action === "reject" && <p>These suggestions will be marked as rejected and left out of exports. You can reset them later.</p>}
      {action === "reset" && <p>Each row goes back to pending with the engine's original suggestion. Manual choices on these rows are discarded.</p>}
    </ConfirmDialog>
  );
}

function DetailPanel({ project, reviewId, onClose, onChanged, onApprove }) {
  const { data: row, loading, reload } = useGet(`/projects/${project.id}/mappings/${reviewId}/`);
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [picker, setPicker] = useState(false);
  const [pendingAssign, setPendingAssign] = useState(null);

  const after = async () => { await reload(true); await onChanged(); };
  const call = async (fn) => { setBusy(true); try { await fn(); await after(); } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); } };
  const assign = async (payload, extra = {}) => {
    setBusy(true);
    try { await api.post(`/projects/${project.id}/mappings/${reviewId}/assign/`, { ...payload, ...extra }); setPendingAssign(null); setPicker(false); toast.success("Destination saved and approved."); await after(); }
    catch (err) {
      const info = errorInfo(err);
      if (info.code === "many_to_one_confirmation_required") setPendingAssign({ payload, message: info.message }); else toast.error(info.message);
    } finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title="Mapping details" wide>
      {loading && !row ? <Spinner /> : row && (
        <div className="space-y-5 text-sm">
          <div>
            <p className="text-xs font-medium uppercase text-ink-500">Old URL</p>
            <p className="break-all font-mono text-xs">{row.old_url.original}</p>
            {row.old_url.normalized !== row.old_url.original && <p className="break-all text-xs text-ink-500">Compared as: {row.old_url.normalized}</p>}
            {row.old_url.title && <p className="mt-1 text-ink-700">“{row.old_url.title}”</p>}
          </div>
          <div>
            <p className="text-xs font-medium uppercase text-ink-500">Redirect to</p>
            <p className="break-all font-mono text-xs">{row.final_url || "No destination yet"}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2"><StatusBadge status={row.status} /><BandBadge band={row.band} /><span>Score {row.score}</span>
              <span className="text-ink-500">· {MATCH_LABEL[row.match_type] || row.match_type} · {EVIDENCE_LABEL[row.evidence] || row.evidence}</span></div>
          </div>
          {row.recommended_url && row.recommended_url !== row.final_url && <p className="text-xs text-ink-500">Engine suggestion: <span className="break-all font-mono">{row.recommended_url}</span></p>}

          <div>
            <p className="mb-1 text-xs font-medium uppercase text-ink-500">Why this suggestion</p>
            {row.reasons.length ? <ul className="list-disc space-y-1 pl-5">{row.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="text-ink-500">No evidence was found.</p>}
            {row.evidence === "url_only" && <p className="mt-2 text-xs text-ink-500">Only the URL text was compared. Add page titles to the import for better evidence.</p>}
          </div>

          {Object.keys(row.components).length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-ink-500">Score breakdown</p>
              <div className="space-y-1">{Object.entries(row.components).map(([k, v]) => (
                <div key={k} className="flex items-center gap-2"><span className="w-24 text-xs capitalize text-ink-700">{k}</span>
                  <div className="h-1.5 flex-1 rounded bg-ink-100"><div className="h-1.5 rounded bg-brand-500" style={{ width: `${v}%` }} /></div><span className="w-8 text-right text-xs tabular-nums">{v}</span></div>))}</div>
            </div>
          )}

          {row.alternatives.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-ink-500">Other candidates{row.ambiguous && <span className="ml-2 normal-case text-amber-700">— close call, please check</span>}</p>
              <ul className="divide-y divide-ink-100 rounded-lg border border-ink-200">{row.alternatives.map((a) => (
                <li key={a.new_id} className="flex items-center gap-2 px-3 py-2"><span className="min-w-0 flex-1 truncate font-mono text-xs" title={a.url}>{a.url}</span><span className="tabular-nums text-xs">{a.score}</span>
                  <button className="btn-secondary btn-sm" disabled={busy} onClick={() => assign({ new_url_id: a.new_id })}>Use this</button></li>))}</ul>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Redirect type" htmlFor="rs"><select id="rs" className="input" value={row.redirect_status} onChange={(e) => call(() => api.patch(`/projects/${project.id}/mappings/${reviewId}/`, { redirect_status: Number(e.target.value) }))}>
              <option value={301}>301 – Permanent</option><option value={302}>302 – Temporary</option><option value={307}>307 – Temporary (keeps method)</option><option value={308}>308 – Permanent (keeps method)</option></select></Field>
            <Field label="Note" htmlFor="note"><input id="note" className="input" maxLength={500} value={note ?? row.note} onChange={(e) => setNote(e.target.value)}
              onBlur={() => note !== null && note !== row.note && call(() => api.patch(`/projects/${project.id}/mappings/${reviewId}/`, { note }))} /></Field>
          </div>

          <div className="flex flex-wrap gap-2 border-t border-ink-100 pt-4">
            <button className="btn-primary" disabled={busy || !row.final_new_url_id || row.status === "approved"} onClick={async () => { await onApprove(row); await reload(true); }}><Check className="h-4 w-4" aria-hidden />Approve</button>
            <button className="btn-secondary" disabled={busy || row.status === "rejected"} onClick={() => call(() => api.post(`/projects/${project.id}/mappings/${reviewId}/reject/`))}><X className="h-4 w-4" aria-hidden />Reject</button>
            <button className="btn-secondary" disabled={busy} onClick={() => setPicker(true)}>Choose another destination…</button>
            <button className="btn-ghost" disabled={busy} onClick={() => call(() => api.post(`/projects/${project.id}/mappings/${reviewId}/reset/`))}><RotateCcw className="h-4 w-4" aria-hidden />Reset</button>
            <button className="btn-ghost" disabled={busy || !row.can_undo} onClick={() => call(() => api.post(`/projects/${project.id}/mappings/${reviewId}/undo/`))}><Undo2 className="h-4 w-4" aria-hidden />Undo last change</button>
            {busy && <Loader2 className="h-4 w-4 animate-spin self-center" aria-hidden />}
          </div>
        </div>
      )}
      <DestinationPicker open={picker} project={project} onClose={() => setPicker(false)} onPick={(payload) => assign(payload)} busy={busy} />
      <ConfirmDialog open={!!pendingAssign} title="Many old URLs to one page" confirmLabel="Yes, this is intended" busy={busy} onClose={() => setPendingAssign(null)} onConfirm={() => assign(pendingAssign.payload, { confirm_many_to_one: true })}>
        <p>{pendingAssign?.message}</p>
      </ConfirmDialog>
    </Modal>
  );
}

function DestinationPicker({ open, project, onClose, onPick, busy }) {
  const [search, setSearch] = useState("");
  const [typed, setTyped] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(search), 300); return () => clearTimeout(t); }, [search]);
  const { data, loading } = useGet(`/projects/${project.id}/urls/`, { side: "new", search: debounced, page_size: 15 }, { enabled: open });
  return (
    <Modal open={open} onClose={onClose} title="Choose a destination" wide>
      <div className="space-y-4 text-sm">
        <Field label="Search the new site's URLs" htmlFor="pick-search"><input id="pick-search" className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Part of a URL or title" autoFocus /></Field>
        {loading ? <Spinner /> : data?.results.length ? (
          <ul className="max-h-64 divide-y divide-ink-100 overflow-auto rounded-lg border border-ink-200">{data.results.map((u) => (
            <li key={u.id} className="flex items-center gap-2 px-3 py-2"><div className="min-w-0 flex-1"><p className="truncate font-mono text-xs" title={u.original_url}>{u.original_url}</p>{u.title && <p className="truncate text-xs text-ink-500">{u.title}</p>}</div>
              <button className="btn-secondary btn-sm" disabled={busy} onClick={() => onPick({ new_url_id: u.id })}>Use</button></li>))}</ul>
        ) : <p className="text-ink-500">No imported URL matches.</p>}
        <div className="border-t border-ink-100 pt-4">
          <Field label="…or type any destination URL" htmlFor="typed" hint="For a page that is not in your imported list. It is added to the project's new URLs.">
            <div className="flex gap-2"><input id="typed" className="input" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="https://www.example.com/new-page" inputMode="url" />
              <button className="btn-primary" disabled={busy || !typed.trim()} onClick={() => onPick({ url: typed.trim() })}>Use</button></div></Field>
        </div>
      </div>
    </Modal>
  );
}

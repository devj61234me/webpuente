import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { toast } from "react-toastify";
import { api, errorMessage, fieldErrors } from "../../api/client";
import { useGet } from "../../lib/useApi";
import { Card, ConfirmDialog, Field, Notice, TextInput } from "../../components/ui";
import { useProject } from "./ProjectLayout";

const WEIGHT_LABELS = {
  slug: "Page name (last part of the URL)", path: "Full path", hierarchy: "Folder structure", title: "Page title", h1: "Main heading (H1)", meta: "Meta description", semantic: "Meaning (needs AI embeddings)",
};
const THRESHOLD_LABELS = {
  high: "High confidence from", medium: "Medium confidence from", min_accept: "Lowest score worth suggesting", ambiguity_gap: "Flag as ambiguous when the runner-up is within", fuzzy_cap: "Highest score for an approximate match",
};

const toForm = (p) => ({
  name: p.name, old_site_url: p.old_site_url, new_site_url: p.new_site_url, description: p.description || "",
  s: JSON.parse(JSON.stringify(p.settings)), drop: (p.settings.normalization.drop_params || []).join("\n"), patterns: (p.settings.excluded_patterns || []).join("\n"),
});
const lines = (t) => t.split(/[\n,]+/).map((x) => x.trim()).filter(Boolean);

export default function Settings() {
  const { project, setProject, reload } = useProject();
  const { data: config } = useGet("/config/");
  const [form, setForm] = useState(() => toForm(project));
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [del, setDel] = useState({ open: false, name: "", error: "" });
  const navigate = useNavigate();
  useEffect(() => { setForm(toForm(project)); }, [project.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const setS = (group, key, value) => setForm((f) => ({ ...f, s: { ...f.s, [group]: { ...f.s[group], [key]: value } } }));
  const num = (v) => (v === "" ? "" : Number(v));

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErrors({}); setMessage("");
    const settings = { ...form.s, normalization: { ...form.s.normalization, drop_params: lines(form.drop) }, excluded_patterns: lines(form.patterns) };
    try {
      const { data } = await api.patch(`/projects/${project.id}/`, { name: form.name.trim(), old_site_url: form.old_site_url.trim(), new_site_url: form.new_site_url.trim(), description: form.description, settings });
      setProject(data); setForm(toForm(data)); toast.success("Settings saved. Run the matching again to use new matching settings.");
    } catch (err) { setErrors(fieldErrors(err)); setMessage(errorMessage(err)); } finally { setBusy(false); }
  };

  const remove = async () => {
    setBusy(true);
    try { await api.delete(`/projects/${project.id}/`, { data: { confirm_name: del.name } }); toast.success("Project deleted."); navigate("/projects", { replace: true }); }
    catch (err) { setDel((d) => ({ ...d, error: errorMessage(err) })); } finally { setBusy(false); }
  };

  const s = form.s;
  return (
    <form onSubmit={save} className="space-y-6">
      {message && <Notice tone="error">{message}</Notice>}
      <Card title="Project">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} error={errors.name} maxLength={120} />
          <div />
          <TextInput label="Old website address" value={form.old_site_url} onChange={(e) => setForm({ ...form, old_site_url: e.target.value })} error={errors.old_site_url} />
          <TextInput label="New website address" value={form.new_site_url} onChange={(e) => setForm({ ...form, new_site_url: e.target.value })} error={errors.new_site_url} />
          <div className="sm:col-span-2"><Field label="Notes" htmlFor="desc"><textarea id="desc" className="input" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={1000} /></Field></div>
        </div>
      </Card>

      <Card title="How URLs are compared">
        <p className="mb-4 text-sm text-ink-500">Your original URLs are never changed. These options only decide when two URLs count as the same. Changing them re-normalizes the saved lists.</p>
        {errors.normalization && <div className="mb-3"><Notice tone="error">{errors.normalization}</Notice></div>}
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.normalization.strip_trailing_slash} onChange={(e) => setS("normalization", "strip_trailing_slash", e.target.checked)} />Treat /page and /page/ as the same</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.normalization.ignore_case} onChange={(e) => setS("normalization", "ignore_case", e.target.checked)} />Ignore upper/lower case in paths</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.normalization.ignore_www} onChange={(e) => setS("normalization", "ignore_www", e.target.checked)} />Treat www.example.com and example.com as the same</label>
          <Field label="Query strings (?a=b)" htmlFor="qm">
            <select id="qm" className="input" value={s.normalization.query_mode} onChange={(e) => setS("normalization", "query_mode", e.target.value)}>
              <option value="keep">Keep them</option><option value="drop_listed">Remove only the tracking parameters listed below</option><option value="drop_all">Remove all of them</option></select></Field>
          {s.normalization.query_mode === "drop_listed" && (
            <div className="sm:col-span-2"><Field label="Parameters to remove (one per line)" htmlFor="drop"><textarea id="drop" className="input font-mono text-xs" rows={4} value={form.drop} onChange={(e) => setForm({ ...form, drop: e.target.value })} /></Field></div>
          )}
        </div>
      </Card>

      <Card title="Matching weights and thresholds">
        <p className="mb-4 text-sm text-ink-500">Weights (0 to 1) say how much each kind of evidence counts. Evidence that is missing, such as page titles, is skipped rather than counted as zero. Defaults are a reasonable start.</p>
        {errors.weights && <div className="mb-3"><Notice tone="error">{errors.weights}</Notice></div>}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(WEIGHT_LABELS).map(([k, label]) => (
            <TextInput key={k} label={label} type="number" min="0" max="1" step="0.05" value={s.weights[k]} onChange={(e) => setS("weights", k, num(e.target.value))} disabled={k === "semantic" && !config?.embeddings_enabled} />
          ))}
        </div>
        <h3 className="mb-2 mt-6 text-sm font-semibold">Score thresholds (0–100)</h3>
        {errors.thresholds && <div className="mb-3"><Notice tone="error">{errors.thresholds}</Notice></div>}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(THRESHOLD_LABELS).map(([k, label]) => (
            <TextInput key={k} label={label} type="number" min="0" max="100" value={s.thresholds[k]} onChange={(e) => setS("thresholds", k, num(e.target.value))} />
          ))}
        </div>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <Field label="Default redirect type" htmlFor="rs" error={errors.redirect_status}>
            <select id="rs" className="input" value={s.redirect_status} onChange={(e) => setForm({ ...form, s: { ...s, redirect_status: Number(e.target.value) } })}>
              <option value={301}>301 – Permanent</option><option value={302}>302 – Temporary</option><option value={307}>307 – Temporary (keeps method)</option><option value={308}>308 – Permanent (keeps method)</option></select></Field>
          <div className="self-end pb-2 text-sm">
            <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" disabled={!config?.embeddings_enabled} checked={!!s.use_embeddings} onChange={(e) => setForm({ ...form, s: { ...s, use_embeddings: e.target.checked } })} />
              <span>Use AI embeddings to compare meaning{!config?.embeddings_enabled && <span className="block text-xs text-ink-500">Not configured on this server. An administrator must set an embeddings provider.</span>}
                {config?.embeddings_enabled && <span className="block text-xs text-ink-500">Sends URL paths and titles to the configured provider. May cost money.</span>}</span></label>
          </div>
        </div>
      </Card>

      <Card title="Paths that must never be redirected">
        <Field label="One pattern per line (must start with /)" htmlFor="pat" error={errors.excluded_patterns} hint="Example: /wp-admin/*  or  /api/*">
          <textarea id="pat" className="input font-mono text-xs" rows={4} value={form.patterns} onChange={(e) => setForm({ ...form, patterns: e.target.value })} /></Field>
      </Card>

      <div className="flex justify-end"><button className="btn-primary" disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Save settings</button></div>

      <Card title="Danger zone">
        <p className="mb-3 text-sm text-ink-500">Deleting a project removes its URLs, suggestions, decisions, quality findings and exports for good.</p>
        <button type="button" className="btn-danger" onClick={() => setDel({ open: true, name: "", error: "" })}>Delete this project…</button>
      </Card>

      <ConfirmDialog open={del.open} danger title="Delete this project?" confirmLabel="Delete project" busy={busy} disabled={del.name !== project.name} onClose={() => setDel({ open: false, name: "", error: "" })} onConfirm={remove}>
        <p>This cannot be undone. Type <strong>{project.name}</strong> to confirm.</p>
        {del.error && <Notice tone="error">{del.error}</Notice>}
        <TextInput label="Project name" value={del.name} onChange={(e) => setDel({ ...del, name: e.target.value })} autoComplete="off" />
      </ConfirmDialog>
    </form>
  );
}

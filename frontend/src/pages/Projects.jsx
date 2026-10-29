import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2, Plus } from "lucide-react";
import { toast } from "react-toastify";
import { api, errorMessage, fieldErrors } from "../api/client";
import { useGet } from "../lib/useApi";
import { fmtDate, fmtNumber } from "../lib/format";
import { Card, EmptyState, Modal, Notice, PageHeader, Pagination, Spinner, TextInput, Field } from "../components/ui";

const EMPTY = { name: "", old_site_url: "", new_site_url: "", description: "" };

export default function Projects() {
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useGet("/projects/", { page, page_size: 20 });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const create = async (e) => {
    e.preventDefault();
    setBusy(true); setErrors({}); setFormError("");
    try {
      const { data: project } = await api.post("/projects/", { ...form, name: form.name.trim() });
      toast.success("Project created.");
      navigate(`/projects/${project.id}/import`);
    } catch (err) { setErrors(fieldErrors(err)); setFormError(errorMessage(err)); } finally { setBusy(false); }
  };
  const close = () => { setOpen(false); setForm(EMPTY); setErrors({}); setFormError(""); };

  return (
    <>
      <PageHeader title="Projects" subtitle="One project per website move."
        actions={<button className="btn-primary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" aria-hidden />New project</button>} />
      {loading ? <Spinner /> : error ? <Notice tone="error">{error} <button className="underline" onClick={() => reload()}>Try again</button></Notice> : (
        <Card pad={false}>
          {data.results.length === 0 ? (
            <EmptyState title="No projects yet" action={<button className="btn-primary" onClick={() => setOpen(true)}>Create your first project</button>}>
              Give the project a name and the addresses of the old and new websites. You will add URLs next.</EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-ink-100 bg-ink-50"><tr>
                  <th className="th">Project</th><th className="th">Old URLs</th><th className="th">New URLs</th><th className="th">Approved</th><th className="th">Pending</th><th className="th">Updated</th></tr></thead>
                <tbody className="divide-y divide-ink-100">
                  {data.results.map((p) => (
                    <tr key={p.id} className="hover:bg-ink-50">
                      <td className="td"><Link to={`/projects/${p.id}`} className="font-medium text-brand-700 hover:underline">{p.name}</Link>
                        <div className="max-w-xs truncate text-xs text-ink-500">{p.old_site_url} → {p.new_site_url}</div></td>
                      <td className="td">{fmtNumber(p.old_count)}</td><td className="td">{fmtNumber(p.new_count)}</td>
                      <td className="td">{fmtNumber(p.approved_count)}</td><td className="td">{fmtNumber(p.pending_count)}</td>
                      <td className="td whitespace-nowrap text-ink-500">{fmtDate(p.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pagination page={page} pageSize={20} count={data.count} onPage={setPage} />
        </Card>
      )}
      <Modal open={open} onClose={close} title="New project"
        footer={<><button className="btn-secondary" onClick={close} disabled={busy}>Cancel</button>
          <button className="btn-primary" form="new-project" disabled={busy || !form.name || !form.old_site_url || !form.new_site_url}>{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Create project</button></>}>
        <form id="new-project" onSubmit={create} className="space-y-4" noValidate>
          {formError && !Object.keys(errors).length && <Notice tone="error">{formError}</Notice>}
          <TextInput label="Project name" value={form.name} onChange={set("name")} error={errors.name} maxLength={120} placeholder="e.g. Company website 2026 move" autoFocus />
          <TextInput label="Old website address" value={form.old_site_url} onChange={set("old_site_url")} error={errors.old_site_url} placeholder="https://old.example.com" inputMode="url" />
          <TextInput label="New website address" value={form.new_site_url} onChange={set("new_site_url")} error={errors.new_site_url} placeholder="https://www.example.com" inputMode="url" />
          <Field label="Notes (optional)" htmlFor="desc" error={errors.description}>
            <textarea id="desc" className="input" rows={3} value={form.description} onChange={set("description")} maxLength={1000} />
          </Field>
        </form>
      </Modal>
    </>
  );
}

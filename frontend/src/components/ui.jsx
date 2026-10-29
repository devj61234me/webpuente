import { useEffect, useId, useRef } from "react";
import { AlertTriangle, CheckCircle2, Loader2, X } from "lucide-react";
import { BAND_LABEL, STATUS_LABEL, classNames } from "../lib/format";

export function Spinner({ label = "Loading…", className = "" }) {
  return (
    <div role="status" className={classNames("flex items-center justify-center gap-2 py-10 text-sm text-ink-500", className)}>
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function Card({ title, actions, children, className = "", pad = true }) {
  return (
    <section className={classNames("card", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-ink-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
          {actions}
        </header>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-ink-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Field({ label, error, hint, children, htmlFor }) {
  return (
    <div>
      {label && <label htmlFor={htmlFor} className="label">{label}</label>}
      {children}
      {hint && !error && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
      {error && <p role="alert" className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

export function TextInput({ label, error, hint, id, ...props }) {
  const auto = useId();
  const inputId = id || auto;
  return (
    <Field label={label} error={error} hint={hint} htmlFor={inputId}>
      <input id={inputId} className={classNames("input", error && "border-red-400")} aria-invalid={!!error} {...props} />
    </Field>
  );
}

const BADGE = {
  high: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  medium: "bg-amber-50 text-amber-800 ring-amber-200",
  low: "bg-orange-50 text-orange-800 ring-orange-200",
  unmatched: "bg-ink-100 text-ink-700 ring-ink-200",
  approved: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  rejected: "bg-red-50 text-red-700 ring-red-200",
  pending: "bg-sky-50 text-sky-700 ring-sky-200",
  info: "bg-ink-100 text-ink-700 ring-ink-200",
  neutral: "bg-ink-100 text-ink-700 ring-ink-200",
};
export function Badge({ tone = "neutral", children }) {
  return <span className={classNames("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", BADGE[tone] || BADGE.neutral)}>{children}</span>;
}
export const BandBadge = ({ band }) => <Badge tone={band}>{BAND_LABEL[band] || band}</Badge>;
export const StatusBadge = ({ status }) => <Badge tone={status}>{STATUS_LABEL[status] || status}</Badge>;
export const SeverityBadge = ({ severity }) => (
  <Badge tone={{ high: "rejected", medium: "medium", low: "low", info: "info" }[severity] || "neutral"}>{severity}</Badge>
);

export function Notice({ tone = "info", title, children }) {
  const styles = {
    info: "border-sky-200 bg-sky-50 text-sky-900", warn: "border-amber-200 bg-amber-50 text-amber-900",
    error: "border-red-200 bg-red-50 text-red-800", ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
  };
  const Icon = tone === "ok" ? CheckCircle2 : AlertTriangle;
  return (
    <div role={tone === "error" ? "alert" : "note"} className={classNames("flex gap-2 rounded-lg border p-3 text-sm", styles[tone])}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>{title && <p className="font-medium">{title}</p>}<div>{children}</div></div>
    </div>
  );
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="px-6 py-12 text-center">
      <p className="text-sm font-medium text-ink-900">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-md text-sm text-ink-500">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Modal({ open, onClose, title, children, footer, wide = false }) {
  const ref = useRef(null);
  // Keep the newest onClose in a ref. Parents pass a new function on every render, and if the effect below depended on it,
  // the dialog would grab focus again after every keystroke and the cursor would leave the text box.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    // Only move focus into the dialog if nothing inside it (for example an autoFocus field) already has it
    if (ref.current && !ref.current.contains(document.activeElement)) ref.current.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink-900/40 p-4 sm:items-center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={classNames("max-h-[90vh] w-full overflow-y-auto rounded-xl bg-white shadow-xl", wide ? "max-w-2xl" : "max-w-md")}>
        <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        <div className="p-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-ink-100 px-4 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, title, children, confirmLabel = "Confirm", danger = false, busy = false, onConfirm, onClose, disabled = false }) {
  return (
    <Modal open={open} onClose={onClose} title={title}
      footer={<>
        <button className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
        <button className={danger ? "btn-danger" : "btn-primary"} onClick={onConfirm} disabled={busy || disabled}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}{confirmLabel}
        </button>
      </>}>
      <div className="space-y-3 text-sm text-ink-700">{children}</div>
    </Modal>
  );
}

export function Pagination({ page, pageSize, count, onPage }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (count <= pageSize) return <p className="px-3 py-2 text-xs text-ink-500">{count} item{count === 1 ? "" : "s"}</p>;
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2 text-sm text-ink-700">
      <span className="text-xs text-ink-500">{(page - 1) * pageSize + 1}–{Math.min(page * pageSize, count)} of {count}</span>
      <div className="flex items-center gap-2">
        <button className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <span className="text-xs">Page {page} of {pages}</span>
        <button className="btn-secondary btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </div>
  );
}

export function Stat({ label, value, hint, tone }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className={classNames("mt-1 text-2xl font-semibold", tone === "warn" ? "text-amber-700" : tone === "bad" ? "text-red-700" : "text-ink-900")}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

export function ProgressBar({ value, label }) {
  const pct = Math.max(0, Math.min(100, value || 0));
  return (
    <div role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}
      className="h-2 w-full overflow-hidden rounded-full bg-ink-100">
      <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}

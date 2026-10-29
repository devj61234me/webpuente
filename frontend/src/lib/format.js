export const fmtNumber = (n) => (n ?? 0).toLocaleString();
export function fmtDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
export const BAND_LABEL = { high: "High", medium: "Medium", low: "Low", unmatched: "No match" };
export const STATUS_LABEL = { pending: "Pending", approved: "Approved", rejected: "Rejected" };
export const MATCH_LABEL = {
  exact_url: "Exact URL", exact_path: "Same path", slug: "Page name", fuzzy: "Approximate", semantic: "Meaning", manual: "Chosen by you", none: "None",
};
export const KIND_LABEL = {
  no_destination: "No destination", orphan_new_url: "New page nobody points to", duplicate_source: "Duplicate source", many_to_one: "Many old URLs → one page",
  self_redirect: "Redirects to itself", redirect_loop: "Redirect loop", redirect_chain: "Redirect chain", invalid_destination: "Invalid destination",
  weak_match: "Weak match", homepage_redirect: "Sent to the home page", homepage_mass_redirect: "Many pages sent to the home page", excluded_pattern: "Excluded path",
};
export const EVIDENCE_LABEL = { url_only: "URL only", metadata: "URL + page titles", semantic: "URL + titles + meaning" };
// Download a Blob with a file name chosen by the server.
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const classNames = (...parts) => parts.filter(Boolean).join(" ");

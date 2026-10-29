import { useState } from "react";
import { useGet } from "../../lib/useApi";
import { fmtDate } from "../../lib/format";
import { Card, Notice, Pagination, Spinner } from "../../components/ui";
import { useProject } from "./ProjectLayout";

const detailText = (d) => Object.entries(d || {}).filter(([, v]) => v !== "" && v !== null && typeof v !== "object").map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ");

export default function Activity() {
  const { project } = useProject();
  const [page, setPage] = useState(1);
  const { data, loading, error } = useGet(`/projects/${project.id}/audit/`, { page, page_size: 50 });
  if (loading && !data) return <Spinner />;
  if (error && !data) return <Notice tone="error">{error}</Notice>;
  return (
    <Card title="Activity log" pad={false}>
      {data.results.length === 0 ? <p className="px-4 py-6 text-sm text-ink-500">Nothing has happened yet.</p> : (
        <>
          <div className="overflow-x-auto"><table className="w-full min-w-[600px]"><thead className="border-b border-ink-100 bg-ink-50"><tr><th className="th">When</th><th className="th">Who</th><th className="th">What</th><th className="th">Details</th></tr></thead>
            <tbody className="divide-y divide-ink-100">{data.results.map((e) => (
              <tr key={e.id}><td className="td whitespace-nowrap text-ink-500">{fmtDate(e.created_at)}</td><td className="td">{e.user || "system"}</td><td className="td font-mono text-xs">{e.action}</td>
                <td className="td max-w-md truncate text-xs text-ink-700" title={detailText(e.detail)}>{detailText(e.detail)}</td></tr>))}</tbody></table></div>
          <Pagination page={page} pageSize={50} count={data.count} onPage={setPage} />
        </>
      )}
    </Card>
  );
}

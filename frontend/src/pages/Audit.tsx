import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Badge, Button, Card, Empty, ErrorBox, Json, PageHeader, Spinner, Table, Td, when } from "../components/ui";
import { useResource } from "../hooks";

export default function Audit() {
  const [sp, setSp] = useSearchParams();
  const run = sp.get("run") ?? "";
  const action = sp.get("action") ?? "";
  const qs = new URLSearchParams({ limit: "300", ...(run && { run_id: run }), ...(action && { action }) }).toString();
  const { data, loading, error } = useResource<any>(`/api/audit?${qs}`);
  const [verify, setVerify] = useState<any>(null);
  const [open, setOpen] = useState<number | null>(null);
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); v ? n.set(k, v) : n.delete(k); setSp(n); };

  return (
    <>
      <PageHeader title="Audit trail" subtitle="Append-only log of uploads, extractions, tool calls, quotes and approvals. Each entry is hash-chained to the previous one."
        actions={<Button onClick={async () => setVerify(await api.get("/api/audit/verify"))}>Verify hash chain</Button>} />
      {verify && (
        <div className={`mb-4 rounded-md border p-3 text-sm ${verify.ok ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "border-red-300 bg-red-50 text-red-800"}`}>
          {verify.ok ? `Chain intact: ${verify.checked} entries verified.` : `Chain BROKEN at entry #${verify.first_bad_id} (checked ${verify.checked}). The log was modified outside the application.`}
        </div>
      )}
      <Card>
        <div className="mb-3 flex flex-wrap gap-3">
          <input value={run} onChange={(e) => set("run", e.target.value.trim())} placeholder="Filter by run id (e.g. rfq-1a2b3c4d)" className="w-64 rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
          <input value={action} onChange={(e) => set("action", e.target.value.trim())} placeholder="Filter by action (e.g. quote_approved)" className="w-64 rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
          {data && <span className="self-center text-xs text-slate-500">{data.items.length} of {data.total} entries shown (newest first)</span>}
        </div>
        {loading ? <Spinner /> : error ? <ErrorBox>{error}</ErrorBox> : !data?.items.length ? <Empty>No audit entries match.</Empty> : (
          <Table head={["#", "Time", "Run", "Actor", "Action", "Hash", ""]}>
            {data.items.map((a: any) => (
              <Fragment key={a.id}>
                <tr className="hover:bg-slate-50">
                  <Td className="num text-xs">{a.id}</Td><Td className="whitespace-nowrap text-xs text-slate-500">{when(a.ts)}</Td><Td className="font-mono text-xs">{a.run_id ?? "-"}</Td>
                  <Td className="text-xs">{a.actor === "ai" ? <Badge tone="violet">ai</Badge> : a.actor === "system" ? <Badge>system</Badge> : a.actor}</Td>
                  <Td className="font-mono text-xs">{a.action}</Td><Td className="font-mono text-xs text-slate-400" title={a.hash}>{a.hash.slice(0, 10)}…</Td>
                  <Td><button className="text-xs text-sky-700 hover:underline" onClick={() => setOpen(open === a.id ? null : a.id)}>{open === a.id ? "hide" : "payload"}</button></Td>
                </tr>
                {open === a.id && <tr><td colSpan={7} className="bg-slate-50 px-3 py-2"><Json value={a.payload} /><div className="mt-1 font-mono text-xs text-slate-400">prev {a.prev_hash}<br />hash {a.hash}</div></td></tr>}
              </Fragment>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}

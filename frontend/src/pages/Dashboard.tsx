import { Link } from "react-router-dom";
import { useResource } from "../hooks";
import { Badge, Card, Empty, ErrorBox, Kpi, PageHeader, Spinner, StatusBadge, Table, Td, ms, when } from "../components/ui";

export default function Dashboard() {
  const { data, error, loading } = useResource<any>("/api/dashboard", { poll: () => true, intervalMs: 5000 });
  if (loading) return <Spinner />;
  if (error || !data) return <ErrorBox>{error ?? "No data"}</ErrorBox>;
  const m = data.metrics;
  const t = m.by_type ?? {};
  const count = (type: string) => Object.values<number>(t[type] ?? {}).reduce((a, b) => a + b, 0);
  return (
    <>
      <PageHeader title="Operations dashboard" subtitle="Live view of workflow runs, the approval queue and system health." />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Kpi label="Awaiting approval" value={data.pending_approvals.length} tone={data.pending_approvals.length ? "text-amber-600" : undefined} />
        <Kpi label="RFQs processed" value={count("rfq")} />
        <Kpi label="COA checks" value={count("coa")} />
        <Kpi label="Export doc sets" value={count("export_docs")} />
        <Kpi label="Latency p50 / p95" value={`${ms(m.latency_ms.p50)}`} hint={`p95 ${ms(m.latency_ms.p95)} · ${m.latency_ms.n} runs`} />
        <Kpi label="Failed runs" value={m.failed_runs} tone={m.failed_runs ? "text-red-600" : undefined} hint={`${m.tool_calls_total} tool calls`} />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card title="Approval queue" actions={<Link className="text-xs text-sky-700 hover:underline" to="/rfq">New RFQ</Link>}>
          {data.pending_approvals.length === 0 ? <Empty>Nothing waiting. Submit an RFQ to create a suggested quote.</Empty> : (
            <Table head={["Run", "Total (USD)", "Warnings", "Created"]}>
              {data.pending_approvals.map((r: any) => (
                <tr key={r.id}>
                  <Td><Link className="font-mono text-xs text-sky-700 hover:underline" to={`/rfq/${r.id}`}>{r.id}</Link></Td>
                  <Td className="num">{r.total ? Number(r.total).toLocaleString() : "-"}</Td>
                  <Td><div className="flex flex-wrap gap-1">{r.warnings.filter((w: string) => w !== "UNIT_CONVERTED").map((w: string) => <Badge key={w} tone="amber">{w}</Badge>)}</div></Td>
                  <Td className="text-xs text-slate-500">{when(r.created_at)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card title="Recent activity">
          <Table head={["Run", "Type", "Status", "Latency"]}>
            {data.recent.map((r: any) => (
              <tr key={r.id}>
                <Td><Link className="font-mono text-xs text-sky-700 hover:underline" to={`/${r.type === "rfq" ? "rfq" : r.type === "coa" ? "quality" : "documents"}/${r.id}`}>{r.id}</Link></Td>
                <Td className="text-xs">{r.type}</Td><Td><StatusBadge status={r.status === "completed" && r.type === "coa" ? "completed" : r.status} /></Td>
                <Td className="num text-xs">{ms(r.latency_ms)}</Td>
              </tr>
            ))}
          </Table>
          {data.recent.length === 0 && <Empty>No runs yet.</Empty>}
        </Card>

        <Card title="Observability: tools">
          <Table head={["Tool", "Calls", "Avg ms", "Failed"]}>
            {m.tools.map((x: any) => (
              <tr key={x.tool}><Td className="font-mono text-xs">{x.tool}</Td><Td className="num">{x.calls}</Td><Td className="num">{x.avg_ms}</Td><Td className="num">{x.failed ? <Badge tone="red">{x.failed}</Badge> : 0}</Td></tr>
            ))}
          </Table>
          {m.tools.length === 0 && <Empty>No tool calls recorded yet.</Empty>}
        </Card>

        <Card title="System">
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-slate-500">AI mode</dt><dd><Badge tone={data.mode === "llm" ? "violet" : "slate"}>{data.mode}{data.model ? ` · ${data.model}` : ""}</Badge></dd>
            <dt className="text-slate-500">LLM time (total)</dt><dd className="num">{ms(m.llm_ms_total)}</dd>
            <dt className="text-slate-500">Tool time (total)</dt><dd className="num">{ms(m.tool_ms_total)}</dd>
            <dt className="text-slate-500">Tokens (prompt / output)</dt><dd className="num">{m.prompt_tokens.toLocaleString()} / {m.output_tokens.toLocaleString()}</dd>
          </dl>
          {data.mode === "rules" && <p className="mt-3 rounded bg-slate-50 p-2 text-xs text-slate-600">Rules mode: no language model is configured, so extraction uses regex rules and the tool plan is fixed. Pricing is deterministic in both modes.</p>}
        </Card>
      </div>
    </>
  );
}

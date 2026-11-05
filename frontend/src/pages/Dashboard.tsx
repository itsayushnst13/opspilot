import { Link } from "react-router-dom";
import { useResource } from "../hooks";
import { Badge, Card, Empty, ErrorBox, Kpi, PageHeader, Spinner, StatusBadge, Table, Td, ms, when } from "../components/ui";

export default function Dashboard() {
  const { data, error, loading } = useResource<any>("/api/dashboard", { poll: () => true, intervalMs: 5000 });
  if (loading) return <Spinner label="Loading operations overview…" />;
  if (error || !data) return <ErrorBox>{error ?? "No dashboard data available"}</ErrorBox>;
  const m = data.metrics ?? {};
  const t = m.by_type ?? {};
  const count = (type: string) => Object.values<number>(t[type] ?? {}).reduce((a, b) => a + b, 0);
  const totalRuns = Number(m.runs_total ?? 0);
  const successRuns = Object.values<Record<string, number>>(t).reduce((sum, statuses) => sum + (statuses.completed ?? 0) + (statuses.approved ?? 0), 0);
  const successRate = totalRuns ? Math.round((successRuns / totalRuns) * 100) : 0;
  const workflowTypes = [
    { key: "rfq", label: "RFQ quotations", icon: "↗", hint: "Customer quote workflows" },
    { key: "coa", label: "Quality checks", icon: "◈", hint: "Certificate validation" },
    { key: "export_docs", label: "Export document sets", icon: "▤", hint: "Cross-document checks" },
  ];
  return (
    <>
      <PageHeader title="Operations overview" subtitle="A live view of approvals, workflow activity and AI runtime health." actions={<Link to="/rfq" className="inline-flex min-h-9 items-center gap-2 rounded-xl bg-[#10243a] px-4 text-xs font-semibold text-white shadow-sm transition hover:bg-[#1b3854]">＋ Create RFQ</Link>} />
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/80 bg-white px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-50 text-emerald-700">✦</span><div><p className="text-xs font-semibold text-slate-800">Workspace status</p><p className="text-[11px] text-slate-500">Workflow telemetry refreshed every 5 seconds</p></div></div>
        <div className="flex flex-wrap items-center gap-2"><Badge tone={data.mode === "llm" ? "violet" : "slate"}>{data.mode === "llm" ? "LLM mode" : "Rules mode"}</Badge><Badge tone={data.llm?.verified ? "green" : data.mode === "llm" ? "amber" : "slate"}>{data.mode === "llm" ? (data.llm?.verified ? "Model verified" : "Model unverified") : "Deterministic engine"}</Badge></div>
      </div>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Kpi label="Awaiting approval" value={data.pending_approvals?.length ?? 0} hint="Quotes requiring an approver" tone={data.pending_approvals?.length ? "text-amber-600" : undefined} />
        <Kpi label="Total workflow runs" value={totalRuns} hint="Across all operation types" />
        <Kpi label="Completed / approved" value={successRuns} hint={`${successRate}% of all recorded runs`} tone="text-emerald-700" />
        <Kpi label="Failed runs" value={m.failed_runs ?? 0} hint={`${m.tool_calls_total ?? 0} recorded tool calls`} tone={m.failed_runs ? "text-rose-600" : undefined} />
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.35fr_.85fr]">
        <Card title="Approval queue" actions={<Link className="text-xs font-semibold text-cyan-700 hover:text-cyan-900" to="/rfq">View RFQs →</Link>}>
          {data.pending_approvals?.length === 0 ? <Empty><span className="text-2xl text-emerald-600">✓</span><span className="font-semibold text-slate-700">You're all caught up</span><span>No quotes are waiting for approval.</span></Empty> : (
            <Table head={["Workflow", "Quote total", "Warnings", "Submitted"]}>
              {data.pending_approvals.map((r: any) => (
                <tr key={r.id}>
                  <Td><Link className="font-mono text-xs font-semibold text-cyan-800 hover:underline" to={`/rfq/${r.id}`}>{r.id}</Link></Td>
                  <Td className="num font-semibold">{r.total ? Number(r.total).toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—"} <span className="text-[10px] font-normal text-slate-400">USD</span></Td>
                  <Td><div className="flex flex-wrap gap-1">{(r.warnings ?? []).filter((w: string) => w !== "UNIT_CONVERTED").map((w: string) => <Badge key={w} tone="amber">{w}</Badge>)}</div></Td>
                  <Td className="whitespace-nowrap text-[11px] text-slate-500">{when(r.created_at)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <Card title="Workflow activity" actions={<span className="text-[10px] font-medium text-slate-400">ALL TIME</span>}>
          <div className="space-y-5">
            {workflowTypes.map((w) => {
              const n = count(w.key);
              const pct = totalRuns ? Math.min(100, Math.round(n / totalRuns * 100)) : 0;
              return <div key={w.key}>
                <div className="mb-2 flex items-center justify-between gap-3"><div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-lg bg-slate-50 text-slate-600">{w.icon}</span><div><p className="text-xs font-semibold text-slate-800">{w.label}</p><p className="text-[10px] text-slate-400">{w.hint}</p></div></div><span className="num text-sm font-semibold text-slate-800">{n}</span></div>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-cyan-600 to-blue-500 transition-all" style={{width: `${pct}%`}} /></div>
              </div>;
            })}
          </div>
          <div className="mt-6 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4">
            <div><p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Latency p50</p><p className="num mt-1 text-lg font-semibold text-slate-900">{ms(m.latency_ms?.p50)}</p></div>
            <div><p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Latency p95</p><p className="num mt-1 text-lg font-semibold text-slate-900">{ms(m.latency_ms?.p95)}</p></div>
          </div>
        </Card>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Card title="Recent activity" actions={<span className="text-[10px] text-slate-400">LATEST 10 RUNS</span>}>
          {!data.recent?.length ? <Empty>No workflow runs recorded yet.</Empty> : <Table head={["Workflow", "Type", "Status", "Duration"]}>
            {data.recent.map((r: any) => (
              <tr key={r.id}>
                <Td><Link className="font-mono text-[11px] font-semibold text-cyan-800 hover:underline" to={`/${r.type === "rfq" ? "rfq" : r.type === "coa" ? "quality" : "documents"}/${r.id}`}>{r.id}</Link></Td>
                <Td><span className="text-xs capitalize">{r.type === "export_docs" ? "Export docs" : r.type}</span></Td>
                <Td><StatusBadge status={r.status} /></Td><Td className="num text-xs text-slate-500">{ms(r.latency_ms)}</Td>
              </tr>
            ))}
          </Table>}
        </Card>
        <Card title="Tool observability" actions={<span className="text-[10px] text-slate-400">RECORDED CALLS</span>}>
          {!m.tools?.length ? <Empty>No tool calls recorded yet.</Empty> : <Table head={["Tool", "Calls", "Avg. duration", "Failed"]}>
            {m.tools.map((x: any) => <tr key={x.tool}><Td className="font-mono text-[11px]">{x.tool}</Td><Td className="num">{x.calls}</Td><Td className="num text-xs">{ms(x.avg_ms)}</Td><Td>{x.failed ? <Badge tone="red">{x.failed}</Badge> : <span className="text-xs text-slate-400">0</span>}</Td></tr>)}
          </Table>}
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-[11px] text-slate-500"><span>AI mode</span><Badge tone={data.mode === "llm" ? "violet" : "slate"}>{data.mode}</Badge><span className="ml-auto">LLM time: <b className="num text-slate-700">{ms(m.llm_ms_total)}</b></span><span>Tool time: <b className="num text-slate-700">{ms(m.tool_ms_total)}</b></span></div>
        </Card>
      </div>
    </>
  );
}

import { Badge, Card, ErrorBox, Kpi, PageHeader, Spinner, Table, Td } from "../components/ui";
import { useResource } from "../hooks";

const pct = (x: any) => (x && typeof x === "object" && "rate" in x ? `${(x.rate * 100).toFixed(1)}%` : String(x));
const frac = (x: any) => (x && typeof x === "object" && "passed" in x ? `${x.passed}/${x.total}` : "");

function Metrics({ title, data, skip = [] }: { title: string; data: Record<string, any>; skip?: string[] }) {
  const rows = Object.entries(data).filter(([k, v]) => !["failures", "not_top1", "scenarios", "cases", "per_field", "confusion (expected -> got)", "hit@3_by_kind", ...skip].includes(k) && !Array.isArray(v) && !(v && typeof v === "object" && !("rate" in v)));
  return (
    <Card title={title}>
      <Table head={["Metric", "Result", ""]}>{rows.map(([k, v]) => <tr key={k}><Td className="text-sm">{k.replaceAll("_", " ")}</Td><Td className="num font-medium">{typeof v === "object" ? pct(v) : String(v)}</Td><Td className="num text-xs text-slate-400">{frac(v)}</Td></tr>)}</Table>
    </Card>
  );
}

export default function Evaluations() {
  const { data, loading, error } = useResource<any>("/api/evals/latest");
  if (loading) return <Spinner />;
  if (error || !data) return <ErrorBox>{error ?? "No results"}</ErrorBox>;
  const { meta, suites: s } = data;
  const failures = [...s.pricing.failures, ...s.rfq_extraction.failures, ...s.coa.failures, ...s.consistency.failures, ...s.grounding.failures];
  return (
    <>
      <PageHeader title="Evaluations" subtitle={<>Measured by <code className="text-xs">python evals/run_all.py</code> on {new Date(meta.generated_at).toLocaleString()} · mode <b>{meta.mode}</b> · embedder {meta.embedder}</>} />
      <div className="mb-5 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
        <b>Read these numbers carefully.</b> Datasets are synthetic and template-generated ({Object.entries(meta.datasets).map(([k, v]) => `${v} ${k}`).join(", ")}); the rules extractor was tuned on the same RFQ set, so
        the extraction accuracy is optimistic and says little about real-world RFQs. Pricing is checked against an independent reference implementation written for this project. Results in <b>llm</b> mode have to be produced separately with an API key.
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Pricing exact" value={pct(s.pricing.price_per_kg_exact)} hint={frac(s.pricing.price_per_kg_exact)} />
        <Kpi label="COA verdict" value={pct(s.coa.verdict_accuracy)} hint={`${s.coa["unsafe_passes (non-PASS COA judged PASS)"]} unsafe passes`} />
        <Kpi label="Consistency detection" value={pct(s.consistency["detection_rate (inconsistent sets flagged)"])} hint={`${s.consistency["false_positive_rate (clean sets flagged)"].passed} false positives`} />
        <Kpi label="Retrieval hit@3" value={pct(s.retrieval["hit@3"])} hint={`MRR ${s.retrieval.mrr}`} />
        <Kpi label="RFQ latency p50 / p95" value={`${s.latency.rfq_end_to_end_ms.p50} ms`} hint={`p95 ${s.latency.rfq_end_to_end_ms.p95} ms`} />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Metrics title="RFQ extraction" data={{ all_fields_exact: s.rfq_extraction.all_fields_exact, ...Object.fromEntries(Object.entries(s.rfq_extraction.per_field)) }} />
        <Metrics title="Pricing vs reference engine" data={s.pricing} />
        <Metrics title="Tool-call correctness" data={s.tool_calls} />
        <Metrics title="COA checker" data={s.coa} />
        <Metrics title="Export-document consistency" data={s.consistency} />
        <Metrics title="Retrieval (RAG)" data={s.retrieval} />
        <Metrics title="Grounding / hallucination" data={s.grounding} />
        <Card title="Latency">
          <Table head={["Measure", "p50", "p95", "max"]}>
            <tr><Td>RFQ end-to-end ({s.latency.rfq_end_to_end_ms.n} runs)</Td><Td className="num">{s.latency.rfq_end_to_end_ms.p50} ms</Td><Td className="num">{s.latency.rfq_end_to_end_ms.p95} ms</Td><Td className="num">{s.latency.rfq_end_to_end_ms.max} ms</Td></tr>
            <tr><Td>COA end-to-end ({s.latency.coa_end_to_end_ms.n} runs)</Td><Td className="num">{s.latency.coa_end_to_end_ms.p50} ms</Td><Td className="num">{s.latency.coa_end_to_end_ms.p95} ms</Td><Td className="num">{s.latency.coa_end_to_end_ms.max} ms</Td></tr>
          </Table>
          <p className="mt-2 text-xs text-slate-500">{s.latency.note}</p>
        </Card>
      </div>
      {s.guardrails_scripted_agent.scenarios && (
        <Card title={`Agent guardrails: scripted misbehaving model (${frac(s.guardrails_scripted_agent)})`} className="mt-5">
          <Table head={["Scenario", "Result", "Detail"]}>{s.guardrails_scripted_agent.scenarios.map((x: any) => <tr key={x.scenario}><Td>{x.scenario}</Td><Td><Badge tone={x.passed ? "green" : "red"}>{x.passed ? "PASS" : "FAIL"}</Badge></Td><Td className="text-xs text-slate-500">{x.note}</Td></tr>)}</Table>
        </Card>
      )}
      <Card title="Known failures and misses" className="mt-5">
        {failures.length === 0 && s.retrieval.not_top1.length === 0 ? <p className="text-sm text-slate-500">None in this run.</p> : (
          <ul className="space-y-1.5 text-xs">
            {failures.map((f: any, i: number) => <li key={i} className="font-mono">{JSON.stringify(f)}</li>)}
            {s.retrieval.not_top1.map((f: any) => <li key={f.id}><b>{f.id}</b> rank {String(f.rank)}: “{f.query}” → {f.top3.join(", ")}</li>)}
          </ul>
        )}
      </Card>
    </>
  );
}

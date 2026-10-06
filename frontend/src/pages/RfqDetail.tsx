import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Badge, Button, Card, ErrorBox, Json, Kpi, PageHeader, SeverityBadge, Spinner, StatusBadge, Table, Td, ms, when } from "../components/ui";
import { useResource } from "../hooks";

const STAGES = ["queued", "parsing", "extracting", "agent", "done"];

export default function RfqDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const { data: d, error, reload } = useResource<any>(`/api/rfq/${id}`, { poll: (x) => x.run.status === "processing", intervalMs: 800 });
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actErr, setActErr] = useState<string | null>(null);

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!d) return <Spinner />;
  const { run, quote, extraction } = d;
  const m = run.metrics ?? {};
  const critical = (quote?.warnings ?? []).filter((w: any) => w.severity === "critical");
  const recommend = d.tool_calls.find((t: any) => t.tool === "recommend_source" && t.ok)?.result;
  const selectedId = d.tool_calls.filter((t: any) => t.tool === "calculate_quote" && t.ok).at(-1)?.result?.selected_option?.option_id;
  const isCreator = user?.email === run.created_by;
  const canDecide = (user?.role === "approver" || user?.role === "admin") && quote?.status === "pending_approval";

  const decide = async (decision: "approved" | "rejected") => {
    setBusy(true); setActErr(null);
    try { await api.post(`/api/rfq/${id}/decision`, { decision, reason }); await reload(); } catch (e: any) { setActErr(e.message); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader
        title={run.id}
        subtitle={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={run.status} /> <Badge>{run.mode} mode</Badge> {extraction && <Badge>extraction: {extraction.method}</Badge>} <span className="text-xs">by {run.created_by} · {when(run.created_at)}</span></span>}
        actions={<Link to="/rfq" className="text-sm text-sky-700 hover:underline">← All RFQs</Link>}
      />

      {run.status === "processing" && (
        <Card><div className="flex items-center gap-4"><Spinner label={`Stage: ${m.stage ?? "queued"}`} />
          <div className="flex gap-1">{STAGES.map((s) => <span key={s} className={`h-1.5 w-10 rounded ${STAGES.indexOf(s) <= STAGES.indexOf(m.stage ?? "queued") ? "bg-slate-700" : "bg-slate-200"}`} />)}</div></div></Card>
      )}
      {run.status === "failed" && <ErrorBox>Processing failed: {run.error}. The failure is recorded in the audit trail; no quote was produced.</ErrorBox>}

      {run.status !== "processing" && (
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            {quote ? (
              <Card title="Suggested quote" actions={quote.status === "approved" && <Button onClick={() => api.download(`/api/rfq/${id}/quote.pdf`, `${id}-quote.pdf`).catch((e) => setActErr(e.message))}>Download quote PDF</Button>}>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <Kpi label="Price per kg" value={Number(quote.price_per_kg).toFixed(4)} hint={quote.currency} />
                  <Kpi label="Total" value={Number(quote.total).toLocaleString()} hint={quote.currency} />
                  <Kpi label="Margin" value={`${(Number(quote.breakdown.margin_pct) * 100).toFixed(1)}%`} hint="of selling price" />
                  <Kpi label="Valid until" value={<span className="text-lg">{quote.breakdown.quote_valid_until}</span>} hint={`${quote.breakdown.qty_kg.toLocaleString()} kg · ${quote.breakdown.incoterm}${quote.breakdown.incoterm === "CIF" ? " " + quote.breakdown.destination_port : ""}`} />
                </div>
                <div className="mt-4"><Table head={["Cost line", "Calculation", "Amount (USD)"]}>
                  {quote.breakdown.lines.map((l: any) => <tr key={l.label}><Td>{l.label}</Td><Td className="font-mono text-xs text-slate-500">{l.formula}</Td><Td className="num text-right">{Number(l.amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}</Td></tr>)}
                  <tr className="bg-slate-50 font-medium"><Td>Landed cost</Td><Td /><Td className="num text-right">{Number(quote.breakdown.landed_cost).toLocaleString("en-US", { minimumFractionDigits: 2 })}</Td></tr>
                  <tr className="font-semibold"><Td>Selling price</Td><Td className="font-mono text-xs font-normal text-slate-500">landed / (1 − margin {quote.breakdown.margin_pct})</Td><Td className="num text-right">{Number(quote.total).toLocaleString("en-US", { minimumFractionDigits: 2 })}</Td></tr>
                </Table></div>
                <p className="mt-3 text-xs text-slate-500">Every number above comes from deterministic Python tools reading the reference data, never from the language model.</p>
              </Card>
            ) : run.status !== "failed" && (
              <Card title="No quote could be prepared">
                <p className="text-sm text-slate-700">{m.needs_info?.summary}</p>
                {m.needs_info?.missing?.length > 0 && <p className="mt-2 text-sm"><b>Missing:</b> {m.needs_info.missing.join(", ")}</p>}
                <div className="mt-3 space-y-1">{(m.needs_info?.warnings ?? []).map((w: any) => <div key={w.code}><SeverityBadge severity={w.severity}>{w.code}</SeverityBadge> <span className="text-sm text-slate-600">{w.message}</span></div>)}</div>
                <p className="mt-3 text-xs text-slate-500">The system does not guess a price when required information is missing. Ask the customer and resubmit.</p>
              </Card>
            )}

            {quote && (
              <Card title="Reasoning summary">
                <p className="text-sm leading-relaxed text-slate-700">{quote.reasoning_summary}</p>
              </Card>
            )}

            {recommend?.options?.length > 0 && (
              <Card title={`Sources compared (${recommend.options.length})`}>
                <Table head={["", "Option", "Type", "Origin", "Grade", "Price/kg", "Lead + transit", "Valid until"]}>
                  {recommend.options.map((o: any) => (
                    <tr key={o.option_id} className={o.option_id === selectedId ? "bg-emerald-50" : ""}>
                      <Td>{o.option_id === selectedId && <Badge tone="green">selected</Badge>}</Td>
                      <Td className="text-xs">{o.source_name}<div className="font-mono text-slate-400">{o.option_id}</div></Td><Td className="text-xs">{o.source_type}</Td><Td className="text-xs">{o.country}</Td>
                      <Td className="num">{o.purity_grade}%</Td><Td className="num">{o.price_per_kg}</Td>
                      <Td className="num text-xs">{o.lead_time_days}d + {o.transit_days ?? 0}d = {o.days_needed ?? o.lead_time_days}d</Td><Td className="text-xs">{o.valid_until ?? "n/a (plant)"}</Td>
                    </tr>
                  ))}
                </Table>
                {recommend.available_days != null && <p className="mt-2 text-xs text-slate-500">Days available before the required date: {recommend.available_days}. Rule: the cheapest option that meets the deadline is selected.</p>}
              </Card>
            )}

            <Card title="Extracted RFQ fields" actions={<Badge>{extraction?.method}</Badge>}>
              {extraction ? <>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
                  {Object.entries(extraction.fields).filter(([k]) => k !== "destination_supported").map(([k, v]) => (
                    <div key={k}><dt className="text-xs text-slate-500">{k.replaceAll("_", " ")}</dt><dd className="font-medium">{v === null ? <span className="text-red-600">missing</span> : String(v)}</dd></div>
                  ))}
                </dl>
                {extraction.issues.length > 0 && <ul className="mt-3 list-disc pl-5 text-xs text-slate-600">{extraction.issues.map((i: any, n: number) => <li key={n}><b>{i.code}</b>: {i.message}</li>)}</ul>}
              </> : <span className="text-sm text-slate-500">No extraction recorded.</span>}
            </Card>

            <Card title={`Tool calls (${d.tool_calls.length})`}>
              <Table head={["#", "Tool", "OK", "ms", "Arguments", "Result"]}>
                {d.tool_calls.map((t: any) => <ToolRow key={t.seq} t={t} />)}
              </Table>
            </Card>
          </div>

          <div className="space-y-5">
            {quote && (
              <Card title="Human approval">
                <div className="mb-3"><StatusBadge status={quote.status} /></div>
                {quote.status === "pending_approval" ? (
                  canDecide ? (
                    <>
                      {isCreator && <div className="mb-3 rounded bg-amber-50 p-2 text-xs text-amber-800">You created this RFQ. The four-eyes rule blocks you from deciding on it. Sign in as another approver (use the sign-out button).</div>}
                      {critical.length > 0 && <div className="mb-3 rounded bg-red-50 p-2 text-xs text-red-700">Critical warnings need a written reason (min. 10 characters): {critical.map((w: any) => w.code).join(", ")}</div>}
                      <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="Reason / notes (required for critical warnings and rejections)" className="w-full rounded-md border border-slate-300 p-2 text-sm" />
                      {actErr && <div className="mt-2"><ErrorBox>{actErr}</ErrorBox></div>}
                      <div className="mt-3 flex gap-2">
                        <Button variant="primary" disabled={busy || isCreator || (critical.length > 0 && reason.trim().length < 10)} onClick={() => decide("approved")}>Approve quote</Button>
                        <Button variant="danger" disabled={busy || reason.trim().length < 5} onClick={() => decide("rejected")}>Reject</Button>
                      </div>
                      <p className="mt-2 text-xs text-slate-500">Approving generates the quote PDF. Sending to the customer is simulated in this prototype.</p>
                    </>
                  ) : <p className="text-sm text-slate-600">Waiting for an approver. Your role ({user?.role}) cannot approve quotes.</p>
                ) : d.approvals.map((a: any, i: number) => (
                  <div key={i} className="text-sm"><b>{a.decision}</b> by {a.approver}<div className="text-xs text-slate-500">{when(a.decided_at)}</div>{a.reason && <p className="mt-1 rounded bg-slate-50 p-2 text-xs">{a.reason}</p>}</div>
                ))}
                {quote.status === "approved" && <Button className="mt-3" onClick={() => api.post("/api/documents/generate", { quote_run_id: id }).then((r: any) => nav(`/documents/${r.run_id}`)).catch((e) => setActErr(e.message))}>Generate export documents</Button>}
                {quote.status !== "pending_approval" && actErr && <div className="mt-2"><ErrorBox>{actErr}</ErrorBox></div>}
              </Card>
            )}

            {quote && (
              <Card title={`Warnings (${quote.warnings.length})`}>
                {quote.warnings.length === 0 ? <p className="text-sm text-slate-500">None.</p> : <ul className="space-y-2">{quote.warnings.map((w: any) => <li key={w.code} className="text-sm"><SeverityBadge severity={w.severity}>{w.code}</SeverityBadge><div className="mt-0.5 text-xs text-slate-600">{w.message}</div></li>)}</ul>}
              </Card>
            )}

            {quote && (
              <Card title="Sources & citations">
                <ul className="space-y-2 text-xs">
                  {quote.sources.map((s: any, i: number) => <li key={i}><Badge tone={s.kind === "kb" ? "violet" : "slate"}>{s.kind === "kb" ? "document" : "data"}</Badge> <span className="font-mono">{s.ref}</span><div className="text-slate-500">{String(s.what).slice(0, 110)}</div></li>)}
                </ul>
              </Card>
            )}

            <Card title="Run metrics">
              <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
                <dt className="text-slate-500">Total latency</dt><dd className="num">{ms(run.latency_ms)}</dd>
                <dt className="text-slate-500">Extraction</dt><dd className="num">{ms(m.extraction_ms)}</dd>
                <dt className="text-slate-500">Agent + tools</dt><dd className="num">{ms(m.agent_ms)}</dd>
                <dt className="text-slate-500">Tool time</dt><dd className="num">{ms(m.tool_ms)}</dd>
                <dt className="text-slate-500">LLM calls / time</dt><dd className="num">{m.llm_calls ?? 0} / {ms(m.llm_ms)}</dd>
                <dt className="text-slate-500">Tokens in / out</dt><dd className="num">{m.prompt_tokens ?? 0} / {m.output_tokens ?? 0}</dd>
              </dl>
            </Card>

            <Card title="Audit trail (this run)" actions={<Link to={`/audit?run=${run.id}`} className="text-xs text-sky-700 hover:underline">Open</Link>}>
              <ol className="space-y-2 border-l border-slate-200 pl-3 text-xs">
                {d.audit.map((a: any) => <li key={a.id}><b>{a.action}</b> <span className="text-slate-500">· {a.actor}</span><div className="text-slate-400">{when(a.ts)}</div></li>)}
              </ol>
            </Card>
          </div>
        </div>
      )}
      {actErr && run.status === "processing" && <ErrorBox>{actErr}</ErrorBox>}
    </>
  );
}

function ToolRow({ t }: { t: any }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(!open)}>
        <Td className="num text-xs">{t.seq}</Td><Td className="font-mono text-xs">{t.tool}</Td>
        <Td>{t.ok ? <Badge tone="green">ok</Badge> : <Badge tone="red">error</Badge>}</Td><Td className="num text-xs">{t.duration_ms}</Td>
        <Td className="max-w-xs truncate font-mono text-xs text-slate-500">{JSON.stringify(t.args)}</Td>
        <Td className="text-xs text-sky-700">{open ? "hide" : "show"}</Td>
      </tr>
      {open && <tr><td colSpan={6} className="bg-slate-50 px-3 py-2"><div className="grid gap-2 md:grid-cols-2"><Json value={t.args} /><Json value={t.result} /></div></td></tr>}
    </>
  );
}

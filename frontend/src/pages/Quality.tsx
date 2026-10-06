import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Dropzone } from "../components/Dropzone";
import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner, StatusBadge, Table, Td, VerdictBadge, ms, when } from "../components/ui";
import { useResource } from "../hooks";

export default function Quality() {
  const { id } = useParams();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const list = useResource<any[]>(id ? null : "/api/quality", { poll: (d) => d.some((r) => r.status === "processing"), intervalMs: 1500 });

  const upload = async (f: File) => {
    setBusy(true); setErr(null);
    try { const r = await api.upload("/api/quality/coa", f); nav(`/quality/${r.run_id}`); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  if (id) return <CoaDetail id={id} />;
  return (
    <>
      <PageHeader title="Quality: certificate of analysis checker" subtitle="Extracts COA values and compares them with the product specification using exact arithmetic. Verdict: PASS, FAIL or REVIEW REQUIRED." />
      <Card title="Upload a COA (PDF or TXT)"><Dropzone accept=".pdf,.txt" label="Drop a certificate of analysis" busy={busy} onFile={upload} />{err && <div className="mt-3"><ErrorBox>{err}</ErrorBox></div>}</Card>
      <Card title="COA checks" className="mt-5">
        {list.loading ? <Spinner /> : !list.data?.length ? <Empty>No COA checks yet.</Empty> : (
          <Table head={["Run", "Verdict", "Product", "Batch", "Status", "Latency", "Created"]}>
            {list.data.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
                <Td><Link className="font-mono text-xs text-sky-700 hover:underline" to={`/quality/${r.id}`}>{r.id}</Link></Td>
                <Td><VerdictBadge verdict={r.coa?.verdict} /></Td><Td className="text-xs">{r.coa?.product_code ?? "-"}</Td><Td className="font-mono text-xs">{r.coa?.batch_no ?? "-"}</Td>
                <Td><StatusBadge status={r.status} /></Td><Td className="num text-xs">{ms(r.latency_ms)}</Td><Td className="text-xs text-slate-500">{when(r.created_at)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}

function CoaDetail({ id }: { id: string }) {
  const { data: d, error } = useResource<any>(`/api/quality/${id}`, { poll: (x) => x.run.status === "processing", intervalMs: 800 });
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!d) return <Spinner />;
  const c = d.coa;
  const tone = c?.verdict === "PASS" ? "border-emerald-300 bg-emerald-50" : c?.verdict === "FAIL" ? "border-red-300 bg-red-50" : "border-amber-300 bg-amber-50";
  return (
    <>
      <PageHeader title={d.run.id} subtitle={<span className="flex items-center gap-2"><StatusBadge status={d.run.status} /> <Badge>extraction: {d.run.metrics.extraction_method ?? "-"}</Badge> <span className="text-xs">{ms(d.run.latency_ms)}</span></span>}
        actions={<Link to="/quality" className="text-sm text-sky-700 hover:underline">← All COA checks</Link>} />
      {d.run.status === "failed" && <ErrorBox>Processing failed: {d.run.error}</ErrorBox>}
      {d.run.status === "processing" && <Spinner label="Checking certificate…" />}
      {c && (
        <div className="space-y-5">
          <div className={`rounded-lg border p-4 ${tone}`}>
            <div className="flex items-center gap-3"><VerdictBadge verdict={c.verdict} /><span className="text-sm font-semibold">{c.product_code ?? "Unidentified product"} · batch {c.batch_no ?? "missing"}</span></div>
            <p className="mt-2 text-sm text-slate-700">{c.explanation}</p>
            {c.verdict !== "PASS" && <p className="mt-2 text-xs text-slate-500">This is decision support: a quality professional must confirm before material is released or rejected.</p>}
          </div>
          <Card title="Parameter comparison">
            <Table head={["Parameter", "Specification", "COA value", "Status", "Reason", "Source"]}>
              {c.results.map((r: any) => (
                <tr key={r.parameter}>
                  <Td className="font-medium">{r.parameter}{r.critical && <span className="ml-1 text-xs text-red-600">critical</span>}</Td><Td className="num text-xs">{r.spec}</Td><Td className="num">{r.actual ?? <span className="text-red-600">not reported</span>}</Td>
                  <Td><VerdictBadge verdict={r.status} /></Td><Td className="text-xs text-slate-600">{r.reason}</Td><Td className="font-mono text-xs text-slate-400">{r.source_ref}</Td>
                </tr>
              ))}
            </Table>
          </Card>
          <Card title="Audit trail"><ol className="space-y-1 text-xs">{d.audit.map((a: any) => <li key={a.id}><b>{a.action}</b> · {a.actor} · <span className="text-slate-400">{when(a.ts)}</span></li>)}</ol></Card>
        </div>
      )}
    </>
  );
}

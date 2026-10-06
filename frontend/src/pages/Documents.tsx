import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, SeverityBadge, Spinner, StatusBadge, Table, Td, when } from "../components/ui";
import { useResource } from "../hooks";

const TITLES: Record<string, string> = { commercial_invoice: "Commercial invoice", packing_list: "Packing list", certificate_of_origin: "Certificate of origin", shipping_instruction: "Shipping instruction" };

export default function Documents() {
  const { id } = useParams();
  return id ? <Detail id={id} /> : <List />;
}

function List() {
  const nav = useNavigate();
  const runs = useResource<any[]>("/api/documents");
  const quotes = useResource<any[]>("/api/rfq?status=approved");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const go = async (body: unknown) => {
    setBusy(true); setErr(null);
    try { const r = await api.post("/api/documents/generate", body); nav(`/documents/${r.run_id}`); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const sample = async () => { const order = await api.get("/api/documents/sample-order"); await go({ order }); };
  return (
    <>
      <PageHeader title="Export documents" subtitle="Generate the invoice, packing list, certificate of origin and shipping instruction from one structured order. Cross-document mismatches block PDF generation." />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="From an approved quote">
          {!quotes.data?.length ? <Empty>No approved quotes yet. Approve one in RFQ → quote.</Empty> : (
            <ul className="divide-y divide-slate-100">{quotes.data.map((q) => (
              <li key={q.id} className="flex items-center justify-between py-2 text-sm"><span><span className="font-mono text-xs">{q.id}</span> <span className="num text-slate-500">· {q.quote ? Number(q.quote.total).toLocaleString() : ""} USD</span></span>
                <Button disabled={busy} onClick={() => go({ quote_run_id: q.id })}>Generate documents</Button></li>
            ))}</ul>
          )}
        </Card>
        <Card title="Try it with a sample order"><p className="text-sm text-slate-600">5 MT CHEM-X01 to Houston, CIF. Then edit a quantity on one document to see the consistency checker block the set.</p>
          <Button className="mt-3" variant="primary" disabled={busy} onClick={sample}>Generate sample document set</Button></Card>
      </div>
      {err && <div className="mt-4"><ErrorBox>{err}</ErrorBox></div>}
      <Card title="Document runs" className="mt-5">
        {runs.loading ? <Spinner /> : !runs.data?.length ? <Empty>No document sets yet.</Empty> : (
          <Table head={["Run", "Status", "Findings", "Created by", "Created"]}>
            {runs.data.map((r) => <tr key={r.id}><Td><Link className="font-mono text-xs text-sky-700 hover:underline" to={`/documents/${r.id}`}>{r.id}</Link></Td><Td><StatusBadge status={r.status} /></Td>
              <Td className="num">{r.metrics?.findings ?? 0}</Td><Td className="text-xs">{r.created_by}</Td><Td className="text-xs text-slate-500">{when(r.created_at)}</Td></tr>)}
          </Table>
        )}
      </Card>
    </>
  );
}

function Detail({ id }: { id: string }) {
  const { data: d, error, reload } = useResource<any>(`/api/documents/${id}`);
  const [doc, setDoc] = useState("packing_list");
  const [field, setField] = useState("net_quantity_kg");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!d) return <Spinner />;
  const blocked = d.run.status === "blocked";
  const edit = async () => {
    setBusy(true); setErr(null);
    try { await api.patch(`/api/documents/${id}`, { doc_type: doc, field, value }); setValue(""); await reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <>
      <PageHeader title={d.run.id} subtitle={<span className="flex items-center gap-2"><StatusBadge status={d.run.status} /> <span className="text-xs">{d.findings.length} finding(s)</span></span>}
        actions={<Link to="/documents" className="text-sm text-sky-700 hover:underline">← All document sets</Link>} />
      {blocked ? (
        <div className="mb-5 rounded-lg border border-red-300 bg-red-50 p-4">
          <div className="font-semibold text-red-800">Document set blocked: inconsistencies found</div>
          <p className="mt-1 text-sm text-red-700">PDFs are not generated while documents disagree. Fix the values below (edit panel) and the set is re-checked automatically.</p>
          <ul className="mt-3 space-y-1.5">{d.findings.map((f: any, i: number) => <li key={i} className="text-sm"><SeverityBadge severity={f.severity}>{f.field}</SeverityBadge> {f.message}</li>)}</ul>
        </div>
      ) : <div className="mb-5 rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-800">All {d.documents.length} documents are consistent. PDFs can be downloaded.</div>}
      <div className="grid gap-5 lg:grid-cols-2">
        {d.documents.map((x: any) => (
          <Card key={x.doc_type} title={TITLES[x.doc_type]} actions={<Button disabled={blocked} onClick={() => api.download(`/api/documents/${id}/${x.doc_type}.pdf`, x.file_name ?? `${x.doc_type}.pdf`).catch((e) => setErr(e.message))}>{blocked ? "PDF blocked" : "Download PDF"}</Button>}>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
              {flatten(x.payload).filter(([k]) => k !== "doc_type").map(([k, v]) => (
                <div key={k} className="contents"><dt className="text-xs text-slate-500">{k}</dt><dd className={`num truncate font-medium ${d.findings.some((f: any) => f.field === k && (f.doc_a === x.doc_type || f.doc_b === x.doc_type)) ? "text-red-600" : ""}`}>{v === null ? "none" : String(v)}</dd></div>
              ))}
            </dl>
          </Card>
        ))}
      </div>
      <Card title="Edit a value (simulate a manual change)" className="mt-5">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm"><span className="block text-xs text-slate-500">Document</span>
            <select className="rounded-md border border-slate-300 px-2 py-1.5 text-sm" value={doc} onChange={(e) => setDoc(e.target.value)}>{Object.entries(TITLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="text-sm"><span className="block text-xs text-slate-500">Field</span>
            <select className="rounded-md border border-slate-300 px-2 py-1.5 text-sm" value={field} onChange={(e) => setField(e.target.value)}>{d.editable_fields.map((f: string) => <option key={f}>{f}</option>)}</select></label>
          <label className="text-sm"><span className="block text-xs text-slate-500">New value</span>
            <input className="rounded-md border border-slate-300 px-2 py-1.5 text-sm" value={value} onChange={(e) => setValue(e.target.value)} placeholder="e.g. 5200" /></label>
          <Button variant="primary" disabled={busy || !value.trim()} onClick={edit}>Apply edit</Button>
        </div>
        <p className="mt-2 text-xs text-slate-500">Try net_quantity_kg = 5200 on the packing list: the invoice says 5000, so the set is blocked until they match again. Every edit is written to the audit trail.</p>
        {err && <div className="mt-3"><ErrorBox>{err}</ErrorBox></div>}
      </Card>
      <Card title="Audit trail" className="mt-5"><ol className="space-y-1 text-xs">{d.audit.map((a: any) => <li key={a.id}><b>{a.action}</b> · {a.actor} · <span className="text-slate-400">{when(a.ts)}</span>{a.action === "document_edited" && <Badge tone="amber">{a.payload.doc_type}.{a.payload.field}: {String(a.payload.from)} → {String(a.payload.to)}</Badge>}</li>)}</ol></Card>
    </>
  );
}

function flatten(o: any, prefix = ""): [string, any][] {
  return Object.entries(o).flatMap(([k, v]) => (v && typeof v === "object" ? flatten(v, `${prefix}${k}.`) : [[`${prefix}${k}`, v] as [string, any]]));
}

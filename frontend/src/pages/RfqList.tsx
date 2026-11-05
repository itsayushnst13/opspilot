import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Dropzone } from "../components/Dropzone";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, Spinner, StatusBadge, Table, Td, ms, when } from "../components/ui";
import { useResource } from "../hooks";

const DEMO_TEXT = `RFQ - Request for Quotation
Customer: Brightwater Coatings LLC
Please quote 5 MT of CHEM-X01, minimum purity 99%, delivered to Houston.
Required by 2026-12-15.`;

export default function RfqList() {
  const nav = useNavigate();
  const { data, loading, error, reload } = useResource<any[]>("/api/rfq", { poll: (d) => d.some((r) => r.status === "processing"), intervalMs: 1500 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [text, setText] = useState("");

  const submit = async (fn: () => Promise<{ run_id: string }>) => {
    setBusy(true); setErr(null);
    try { const r = await fn(); nav(`/rfq/${r.run_id}`); } catch (e: any) { setErr(e.message); reload(); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="RFQ → suggested quote" subtitle="Turn customer requests into traceable, human-approved quotations. Upload a PDF or TXT file, or paste the RFQ message below." />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Upload RFQ (PDF or TXT)">
          <Dropzone accept=".pdf,.txt" label="Drop an RFQ document" busy={busy} onFile={(f) => submit(() => api.upload("/api/rfq", f))} />
        </Card>
        <Card title="Or paste RFQ text" actions={<Button variant="ghost" onClick={() => setText(DEMO_TEXT)}>Load demo RFQ</Button>}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={20000} placeholder="Paste an RFQ email or message…"
            className="min-h-36 w-full rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 text-sm leading-relaxed shadow-sm transition focus:border-cyan-600 focus:bg-white focus:outline-none focus:ring-4 focus:ring-cyan-600/10" />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><span className="text-[10px] text-slate-400">{text.length.toLocaleString()} / 20,000 characters</span><Button variant="primary" disabled={busy || !text.trim()} onClick={() => submit(() => api.post("/api/rfq/text", { text }))}>{busy ? "Processing…" : "Process RFQ →"}</Button></div>
        </Card>
      </div>
      {err && <div className="mt-4"><ErrorBox>{err}</ErrorBox></div>}
      <Card title="All RFQ runs" className="mt-5">
        {loading ? <Spinner /> : error ? <ErrorBox>{error}</ErrorBox> : !data?.length ? <Empty>No RFQs yet. Upload one above.</Empty> : (
          <Table head={["Run", "Status", "Price / kg", "Total", "Flags", "Mode", "Latency", "Created by", "Created"]}>
            {data.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
                <Td><Link className="font-mono text-xs text-sky-700 hover:underline" to={`/rfq/${r.id}`}>{r.id}</Link></Td>
                <Td><StatusBadge status={r.status} /></Td>
                <Td className="num">{r.quote ? Number(r.quote.price_per_kg).toFixed(4) : "-"}</Td>
                <Td className="num">{r.quote ? Number(r.quote.total).toLocaleString() : "-"}</Td>
                <Td><div className="flex flex-wrap gap-1">{(r.quote?.warnings ?? []).filter((w: string) => !["UNIT_CONVERTED", "HAZMAT"].includes(w)).slice(0, 3).map((w: string) => <Badge key={w} tone="amber">{w}</Badge>)}</div></Td>
                <Td className="text-xs">{r.mode}</Td><Td className="num text-xs">{ms(r.latency_ms)}</Td>
                <Td className="text-xs">{r.created_by}</Td><Td className="text-xs text-slate-500">{when(r.created_at)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}

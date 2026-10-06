import { useMemo, useState } from "react";
import { api } from "../api";
import { Dropzone } from "../components/Dropzone";
import { Badge, Button, Card, ErrorBox, PageHeader, Spinner, Table, Td, when } from "../components/ui";
import { useResource } from "../hooks";

const EXAMPLES = ["What are the storage conditions for CHEM-X01?", "Which suppliers have ISO 9001 certification?", "What is the quote approval policy?"];

export default function KnowledgeBase() {
  const docs = useResource<any[]>("/api/kb/documents");
  const [q, setQ] = useState("");
  const [ans, setAns] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");

  const ask = async (question: string) => {
    setQ(question); setBusy(true); setErr(null);
    try { setAns(await api.post("/api/kb/ask", { question })); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const upload = async (f: File) => {
    setErr(null);
    try { await api.upload("/api/kb/upload", f); docs.reload(); } catch (e: any) { setErr(e.message); }
  };
  const types = useMemo(() => ["all", ...Array.from(new Set((docs.data ?? []).map((d) => d.doc_type)))], [docs.data]);
  const shown = (docs.data ?? []).filter((d) => filter === "all" || d.doc_type === filter);

  return (
    <>
      <PageHeader title="Knowledge base" subtitle="Specification sheets, supplier profiles, pricing and shipping tables and regulatory notes. Answers always show their sources." />
      <Card title="Ask the knowledge base">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim().length > 2) ask(q); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about a product, supplier, shipping lane or policy…" className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm" maxLength={500} />
          <Button variant="primary" type="submit" disabled={busy || q.trim().length < 3}>Search</Button>
        </form>
        <div className="mt-2 flex flex-wrap gap-2">{EXAMPLES.map((e) => <button key={e} onClick={() => ask(e)} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-200">{e}</button>)}</div>
        {err && <div className="mt-3"><ErrorBox>{err}</ErrorBox></div>}
        {busy && <div className="mt-4"><Spinner label="Retrieving" /></div>}
        {ans && !busy && (
          <div className="mt-4 space-y-3">
            <div className="rounded-md bg-slate-50 p-3 text-sm"><Badge tone={ans.mode === "llm" ? "violet" : "slate"}>{ans.mode}</Badge> <span className="ml-1 whitespace-pre-wrap">{ans.answer}</span></div>
            {ans.passages.map((p: any) => (
              <div key={p.n} className="rounded-md border border-slate-200 p-3">
                <div className="flex items-center justify-between text-xs"><span className="font-mono text-sky-700">[{p.n}] {p.citation}</span><span className="num text-slate-400">score {p.score}</span></div>
                <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600">{p.content.slice(0, 600)}</p>
              </div>
            ))}
          </div>
        )}
      </Card>
      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Card title="Add a document" className="lg:col-span-1"><Dropzone accept=".pdf,.txt,.csv,.xlsx" label="Upload to the knowledge base" onFile={upload} />
          <p className="mt-2 text-xs text-slate-500">Uploaded documents are chunked, embedded and become searchable immediately. Treated as untrusted text.</p></Card>
        <Card title={`Indexed documents (${shown.length})`} className="lg:col-span-2" actions={<select value={filter} onChange={(e) => setFilter(e.target.value)} className="rounded border border-slate-300 px-2 py-1 text-xs">{types.map((t) => <option key={t}>{t}</option>)}</select>}>
          {docs.loading ? <Spinner /> : <div className="max-h-96 overflow-y-auto"><Table head={["Document", "Type", "Chunks", "Products", "Ingested"]}>
            {shown.map((d) => <tr key={d.id}><Td className="font-mono text-xs">{d.path}</Td><Td className="text-xs">{d.doc_type}</Td><Td className="num">{d.chunks}</Td><Td className="text-xs">{(d.product_codes ?? []).slice(0, 3).join(", ")}</Td><Td className="text-xs text-slate-400">{when(d.ingested_at)}</Td></tr>)}
          </Table></div>}
        </Card>
      </div>
    </>
  );
}

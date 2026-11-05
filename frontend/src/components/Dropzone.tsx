import { useRef, useState } from "react";
import { Spinner, cx } from "./ui";

export function Dropzone({ accept, label, onFile, busy }: { accept: string; label: string; onFile: (f: File) => void; busy?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const choose = () => { if (!busy) ref.current?.click(); };
  return (
    <div
      onClick={choose}
      onDragOver={(e) => { e.preventDefault(); if (!busy) setOver(true); }}
      onDragLeave={(e) => { e.preventDefault(); setOver(false); }}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f && !busy) onFile(f); }}
      role="button" tabIndex={busy ? -1 : 0} aria-disabled={busy}
      onKeyDown={(e) => { if (!busy && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); choose(); } }}
      className={cx("group flex min-h-48 flex-col items-center justify-center rounded-2xl border-2 border-dashed px-5 py-8 text-center transition-all",
        busy ? "cursor-wait border-slate-200 bg-slate-50/70" :
        over ? "cursor-copy border-cyan-500 bg-cyan-50 shadow-inner" :
        "cursor-pointer border-slate-200 bg-slate-50/70 hover:border-cyan-400 hover:bg-cyan-50/50")}
    >
      <input ref={ref} type="file" accept={accept} disabled={busy} className="sr-only" aria-label={label} onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
      {busy ? <Spinner label="Uploading and processing…" /> : (
        <>
          <div className={cx("mb-3 grid h-12 w-12 place-items-center rounded-2xl transition-colors", over ? "bg-cyan-100 text-cyan-800" : "bg-white text-cyan-700 shadow-sm ring-1 ring-slate-200 group-hover:bg-cyan-100")}>
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 16.5v2A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5v-2"/></svg>
          </div>
          <p className="text-sm font-semibold text-slate-800">{label}</p>
          <p className="mt-1.5 text-xs text-slate-500">Drag and drop or <span className="font-semibold text-cyan-700">browse files</span></p>
          <div className="mt-4 flex flex-wrap justify-center gap-1.5">{accept.split(",").map((ext) => <span key={ext} className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[10px] text-slate-500">{ext.replace(".","").toUpperCase()}</span>)}</div>
          <p className="mt-3 text-[10px] text-slate-400">Maximum file size: 5 MB</p>
        </>
      )}
    </div>
  );
}

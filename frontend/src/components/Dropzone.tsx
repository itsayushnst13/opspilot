import { useRef, useState } from "react";
import { Spinner, cx } from "./ui";

export function Dropzone({ accept, label, onFile, busy }: { accept: string; label: string; onFile: (f: File) => void; busy?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      onClick={() => !busy && ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f && !busy) onFile(f); }}
      role="button" tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && ref.current?.click()}
      className={cx("flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center text-sm",
        over ? "border-slate-500 bg-slate-100" : "border-slate-300 bg-slate-50 hover:bg-slate-100")}
    >
      <input ref={ref} type="file" accept={accept} className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
      {busy ? <Spinner label="Uploading" /> : <><div className="font-medium text-slate-700">{label}</div><div className="mt-1 text-xs text-slate-500">Drop a file here or click to browse · {accept.replaceAll(",", " ")} · max 5 MB</div></>}
    </div>
  );
}

import type { ReactNode } from "react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

const TONES: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", red: "bg-rose-50 text-rose-700 ring-rose-600/20",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/20", blue: "bg-sky-50 text-sky-700 ring-sky-600/20",
  slate: "bg-slate-100 text-slate-600 ring-slate-500/20", violet: "bg-violet-50 text-violet-700 ring-violet-600/20",
};
export function Badge({ tone = "slate", children, title }: { tone?: keyof typeof TONES | string; children: ReactNode; title?: string }) {
  return <span title={title} className={cx("inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset whitespace-nowrap", TONES[tone] ?? TONES.slate)}>{children}</span>;
}

const STATUS: Record<string, [string, string]> = {
  processing: ["blue", "Processing"], pending_approval: ["amber", "Pending approval"], needs_info: ["violet", "Needs info"],
  approved: ["green", "Approved"], rejected: ["red", "Rejected"], failed: ["red", "Failed"], completed: ["green", "Completed"],
  blocked: ["red", "Blocked"],
};
export function StatusBadge({ status }: { status: string }) {
  const [tone, label] = STATUS[status] ?? ["slate", status];
  return <Badge tone={tone}>{label}</Badge>;
}
export function VerdictBadge({ verdict }: { verdict?: string | null }) {
  const tone = verdict === "PASS" ? "green" : verdict === "FAIL" ? "red" : "amber";
  return <Badge tone={tone}>{verdict ?? "-"}</Badge>;
}
export function SeverityBadge({ severity, children }: { severity: string; children: ReactNode }) {
  return <Badge tone={severity === "critical" ? "red" : severity === "warning" ? "amber" : "blue"}>{children}</Badge>;
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_2px_12px_rgba(15,23,42,0.035)] transition-shadow hover:shadow-[0_8px_28px_rgba(15,23,42,0.055)]", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <h2 className="text-[13px] font-semibold tracking-tight text-slate-900">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: string }) {
  return (
    <div className="group rounded-2xl border border-slate-200/80 bg-white px-4 py-4 shadow-[0_2px_10px_rgba(15,23,42,0.025)] transition-all hover:-translate-y-0.5 hover:border-cyan-200 hover:shadow-md">
      <div className="text-[10px] font-bold uppercase tracking-[0.13em] text-slate-400">{label}</div>
      <div className={cx("num mt-2 text-[26px] font-semibold tracking-tight", tone ?? "text-slate-900")}>{value}</div>
      {hint && <div className="mt-1 text-[11px] leading-relaxed text-slate-500">{hint}</div>}
    </div>
  );
}

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" };
export function Button({ variant = "secondary", className, ...p }: BtnProps) {
  const v = {
    primary: "bg-[#10243a] text-white shadow-sm shadow-slate-900/10 hover:bg-[#1b3854]",
    secondary: "border border-slate-200 bg-white text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50",
    danger: "bg-rose-600 text-white shadow-sm hover:bg-rose-500",
    ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
  }[variant];
  return <button {...p} className={cx("inline-flex min-h-9 items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-50", v, className)} />;
}

export function Table({ head, children, empty }: { head: ReactNode[]; children: ReactNode; empty?: ReactNode }) {
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <table className="min-w-full text-left text-[13px]">
        <thead className="border-y border-slate-100 text-[10px] uppercase tracking-[0.12em] text-slate-400">
          <tr>{head.map((h, i) => <th key={i} scope="col" className="whitespace-nowrap bg-slate-50/80 px-3.5 py-3 font-bold first:rounded-l-lg last:rounded-r-lg">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100/90">{children}</tbody>
      </table>
      {empty}
    </div>
  );
}
export const Td = ({ children, className, title }: { children?: ReactNode; className?: string; title?: string }) => <td title={title} className={cx("px-3.5 py-3 align-middle text-slate-700", className)}>{children}</td>;

export function Empty({ children }: { children: ReactNode }) {
  return <div className="flex min-h-28 flex-col items-center justify-center gap-2 py-8 text-center text-[13px] text-slate-500">{children}</div>;
}
export function ErrorBox({ children }: { children: ReactNode }) {
  return <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-[13px] leading-relaxed text-rose-700">{children}</div>;
}
export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-24 items-center justify-center gap-2 text-[13px] text-slate-500" role="status" aria-live="polite">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-cyan-700" />{label}
    </div>
  );
}
export function Json({ value }: { value: unknown }) {
  return <pre className="max-h-72 overflow-auto rounded-xl border border-slate-700 bg-[#101c2e] p-4 text-xs leading-relaxed text-slate-100">{JSON.stringify(value, null, 2)}</pre>;
}
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0"><div className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-700">Operations workspace</div><h1 className="text-[25px] font-semibold tracking-tight text-slate-950">{title}</h1>{subtitle && <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-slate-500">{subtitle}</p>}</div>
      <div className="flex items-center gap-2">{actions}</div>
    </div>
  );
}

export const money = (v: string | number | null | undefined, cur = "USD") =>
  v === null || v === undefined ? "-" : `${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} ${cur}`;
export const ms = (v?: number | null) => (v === null || v === undefined ? "-" : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`);
export const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : "-");

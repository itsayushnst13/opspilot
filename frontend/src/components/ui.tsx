import type { ReactNode } from "react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

const TONES: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", red: "bg-red-50 text-red-700 ring-red-600/20",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/20", blue: "bg-sky-50 text-sky-700 ring-sky-600/20",
  slate: "bg-slate-100 text-slate-600 ring-slate-500/20", violet: "bg-violet-50 text-violet-700 ring-violet-600/20",
};
export function Badge({ tone = "slate", children, title }: { tone?: keyof typeof TONES | string; children: ReactNode; title?: string }) {
  return <span title={title} className={cx("inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap", TONES[tone] ?? TONES.slate)}>{children}</span>;
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
    <section className={cx("rounded-lg border border-slate-200 bg-white shadow-sm", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={cx("num mt-1 text-2xl font-semibold", tone ?? "text-slate-900")}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" };
export function Button({ variant = "secondary", className, ...p }: BtnProps) {
  const v = {
    primary: "bg-slate-900 text-white hover:bg-slate-700", secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50",
    danger: "bg-red-600 text-white hover:bg-red-500", ghost: "text-slate-600 hover:bg-slate-100",
  }[variant];
  return <button {...p} className={cx("inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50", v, className)} />;
}

export function Table({ head, children, empty }: { head: ReactNode[]; children: ReactNode; empty?: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
          <tr>{head.map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
      {empty}
    </div>
  );
}
export const Td = ({ children, className, title }: { children?: ReactNode; className?: string; title?: string }) => <td title={title} className={cx("px-3 py-2 align-top", className)}>{children}</td>;

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-8 text-center text-sm text-slate-500">{children}</div>;
}
export function ErrorBox({ children }: { children: ReactNode }) {
  return <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{children}</div>;
}
export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700" />{label}
    </div>
  );
}
export function Json({ value }: { value: unknown }) {
  return <pre className="max-h-72 overflow-auto rounded bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">{JSON.stringify(value, null, 2)}</pre>;
}
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-xl font-semibold text-slate-900">{title}</h1>{subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}</div>
      <div className="flex items-center gap-2">{actions}</div>
    </div>
  );
}

export const money = (v: string | number | null | undefined, cur = "USD") =>
  v === null || v === undefined ? "-" : `${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} ${cur}`;
export const ms = (v?: number | null) => (v === null || v === undefined ? "-" : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`);
export const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : "-");

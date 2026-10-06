import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import { Badge, Button, cx } from "./ui";

const NAV = [
  ["/dashboard", "Dashboard"], ["/rfq", "RFQ → Quote"], ["/quality", "Quality (COA)"], ["/documents", "Export documents"],
  ["/knowledge-base", "Knowledge base"], ["/audit", "Audit trail"], ["/evaluations", "Evaluations"],
] as const;

export default function Layout() {
  const { user, logout } = useAuth();
  const { data: health } = useResource<{ mode: string }>("/api/health");
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 flex-col bg-slate-900 text-slate-300 md:flex">
        <div className="px-4 py-4">
          <div className="text-base font-semibold tracking-tight text-white">OpsPilot</div>
          <div className="text-xs text-slate-400">Chemical operations assistant</div>
        </div>
        <nav className="flex-1 space-y-0.5 px-2">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => cx("block rounded px-3 py-2 text-sm", isActive ? "bg-slate-700 text-white" : "hover:bg-slate-800")}>{label}</NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-800 px-4 py-3 text-xs leading-snug text-slate-400">
          Independent prototype with synthetic data. Not affiliated with any company.
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-2">
          <nav className="flex gap-1 overflow-x-auto md:hidden">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => cx("whitespace-nowrap rounded px-2 py-1 text-xs", isActive ? "bg-slate-900 text-white" : "text-slate-600")}>{label}</NavLink>
            ))}
          </nav>
          <div className="hidden items-center gap-2 text-xs text-slate-500 md:flex">
            AI mode:
            <Badge tone={health?.mode === "llm" ? "violet" : "slate"} title="rules = deterministic regex extractor + fixed tool plan; llm = Gemini tool-calling agent">{health?.mode ?? "…"}</Badge>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right text-xs"><div className="font-medium text-slate-800">{user?.name}</div><div className="text-slate-500">{user?.role}</div></div>
            <Button variant="ghost" onClick={logout}>Sign out</Button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6"><Outlet /></main>
      </div>
    </div>
  );
}

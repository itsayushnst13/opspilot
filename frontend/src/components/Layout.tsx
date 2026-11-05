import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import { Badge, Button, cx } from "./ui";

const NAV = [
  { to: "/dashboard", label: "Overview", icon: "◫", group: "Workspace" },
  { to: "/rfq", label: "RFQ & quotations", icon: "↗", group: "Workspace" },
  { to: "/quality", label: "Quality checks", icon: "◈", group: "Workspace" },
  { to: "/documents", label: "Export documents", icon: "▤", group: "Workspace" },
  { to: "/knowledge-base", label: "Knowledge base", icon: "⌕", group: "Intelligence" },
  { to: "/audit", label: "Audit trail", icon: "⌁", group: "Intelligence" },
  { to: "/evaluations", label: "Evaluations", icon: "◎", group: "Intelligence" },
] as const;

const TITLES: Record<string, string> = {
  "/dashboard": "Overview",
  "/rfq": "RFQ & quotations",
  "/quality": "Quality checks",
  "/documents": "Export documents",
  "/knowledge-base": "Knowledge base",
  "/audit": "Audit trail",
  "/evaluations": "Evaluations",
};

export default function Layout() {
  const { user, logout } = useAuth();
  const { data: health } = useResource<{ mode: string; llm?: { configured?: boolean; verified?: boolean } }>("/api/health");
  const location = useLocation();
  const title = Object.entries(TITLES).find(([path]) => location.pathname === path || location.pathname.startsWith(path + "/"))?.[1] ?? "Workspace";
  const groups = ["Workspace", "Intelligence"];

  const navItems = (mobile = false) => groups.map((group) => (
    <div key={group} className={mobile ? "contents" : "mb-6"}>
      {!mobile && <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{group}</p>}
      {NAV.filter((item) => item.group === group).map((item) => (
        <NavLink key={item.to} to={item.to} end={item.to === "/dashboard"}
          className={({ isActive }) => cx(
            mobile
              ? "flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium transition-colors"
              : "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition-all",
            isActive
              ? "bg-cyan-400/10 text-cyan-200 ring-1 ring-inset ring-cyan-300/15"
              : mobile ? "text-slate-500 hover:bg-slate-100 hover:text-slate-900" : "text-slate-400 hover:bg-white/5 hover:text-white"
          )}>
          <span className={cx("grid h-7 w-7 shrink-0 place-items-center rounded-lg text-base", mobile ? "h-5 w-5" : "bg-white/[0.04] text-slate-300 group-hover:bg-white/10")}>{item.icon}</span>
          <span>{item.label}</span>
          {!mobile && item.to === "/rfq" && <span className="ml-auto rounded-md bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-400">P0</span>}
        </NavLink>
      ))}
    </div>
  ));

  return (
    <div className="min-h-screen bg-[#f5f7fb] text-slate-800 md:flex">
      <aside className="relative hidden w-[248px] shrink-0 flex-col overflow-hidden bg-[#101c2e] text-slate-300 md:flex">
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="relative flex items-center gap-3 px-5 py-6">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-cyan-300 to-blue-500 text-sm font-black tracking-tight text-[#102033] shadow-lg shadow-cyan-950/30">OP</div>
          <div><div className="text-[17px] font-bold tracking-tight text-white">OpsPilot</div><div className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-500">Operations intelligence</div></div>
        </div>
        <div className="relative mx-4 mb-6 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-3">
          <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.7)]" /><span className="text-xs font-medium text-slate-200">Workspace ready</span></div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">Chemical operations · Synthetic demo environment</p>
        </div>
        <nav className="relative flex-1 space-y-1 px-3">{navItems()}</nav>
        <div className="relative m-3 rounded-xl border border-white/[0.08] bg-white/[0.035] p-3">
          <div className="flex items-center justify-between"><span className="text-[11px] font-medium text-slate-300">Runtime mode</span><Badge tone={health?.mode === "llm" ? "violet" : "slate"}>{health?.mode ?? "checking"}</Badge></div>
          <p className="mt-2 text-[10px] leading-relaxed text-slate-500">{health?.mode === "llm" ? (health.llm?.verified ? "Model verified in this process." : "Key configured; live model not yet verified.") : "Deterministic rules engine is active."}</p>
        </div>
        <div className="border-t border-white/[0.07] px-5 py-4 text-[10px] leading-relaxed text-slate-500">Independent prototype using synthetic data.<br />Not affiliated with any company.</div>
      </aside>

      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
          <div className="flex h-[68px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#101c2e] text-[11px] font-black text-cyan-300 md:hidden">OP</div>
              <div className="min-w-0"><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">OpsPilot / Workspace</p><h1 className="truncate text-[15px] font-semibold tracking-tight text-slate-900">{title}</h1></div>
            </div>
            <div className="flex items-center gap-3">
              <div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 sm:flex">
                <span className={cx("h-1.5 w-1.5 rounded-full", health?.mode === "llm" && health.llm?.verified ? "bg-emerald-500" : "bg-amber-400")} />
                <span className="text-[11px] font-medium text-slate-600">{health?.mode === "llm" ? (health.llm?.verified ? "AI connected" : "AI unverified") : "Rules engine"}</span>
              </div>
              <div className="hidden h-8 w-px bg-slate-200 sm:block" />
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-indigo-100 to-cyan-100 text-xs font-bold text-indigo-700">{user?.name?.split(" ").map((part) => part[0]).slice(0, 2).join("") ?? "U"}</div>
              <div className="hidden min-w-0 sm:block"><p className="max-w-36 truncate text-xs font-semibold text-slate-800">{user?.name}</p><p className="text-[10px] capitalize text-slate-500">{user?.role}</p></div>
              <Button variant="ghost" onClick={logout} className="text-xs">Sign out</Button>
            </div>
          </div>
          <nav aria-label="Primary navigation" className="flex gap-1 overflow-x-auto border-t border-slate-100 px-3 py-2 md:hidden">{navItems(true)}</nav>
        </header>
        <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><Outlet /></main>
        <footer className="px-6 pb-5 text-center text-[10px] text-slate-400">OpsPilot · Human-approved workflows · All demo reference data is synthetic</footer>
      </div>
    </div>
  );
}

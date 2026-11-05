import { useState } from "react";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import { Button, ErrorBox } from "../components/ui";

type Demo = { enabled: boolean; password?: string; users: { email: string; name: string; role: string }[] };

export default function Login() {
  const { login } = useAuth();
  const { data: demo } = useResource<Demo>("/api/auth/demo-users");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const go = async (e: string, p: string) => {
    setBusy(true); setErr(null);
    try { await login(e, p); } catch (x: any) { setErr(x.message ?? "Sign in failed"); } finally { setBusy(false); }
  };

  return (
    <main className="relative flex min-h-screen overflow-hidden bg-[#f4f7fb]">
      <div className="pointer-events-none absolute -left-40 -top-40 h-[520px] w-[520px] rounded-full bg-cyan-200/40 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-52 right-0 h-[600px] w-[600px] rounded-full bg-indigo-200/35 blur-3xl" />
      <section className="relative mx-auto grid min-h-screen w-full max-w-[1440px] items-center gap-12 px-5 py-10 lg:grid-cols-[1.05fr_.95fr] lg:px-16">
        <div className="hidden lg:block">
          <div className="mb-12 flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#10243a] text-sm font-black text-cyan-300 shadow-xl shadow-slate-900/15">OP</div>
            <div><p className="text-lg font-bold tracking-tight text-slate-950">OpsPilot</p><p className="text-[10px] font-semibold uppercase tracking-[.18em] text-slate-400">Operations intelligence</p></div>
          </div>
          <p className="mb-4 text-xs font-bold uppercase tracking-[.2em] text-cyan-700">AI-assisted chemical operations</p>
          <h1 className="max-w-xl text-5xl font-semibold leading-[1.08] tracking-[-.045em] text-[#10243a] xl:text-6xl">Complex workflows.<br/><span className="text-cyan-700">Clear decisions.</span></h1>
          <p className="mt-6 max-w-lg text-base leading-8 text-slate-500">One workspace to process customer RFQs, review quality certificates, prepare export documents and keep every decision accountable.</p>
          <div className="mt-12 grid max-w-xl grid-cols-3 gap-3">
            {[["01","Quote with control","RFQ → approval"],["02","Check quality","COA validation"],["03","Ship with clarity","Export documents"]].map(([n,t,s]) => (
              <div key={n} className="rounded-2xl border border-white/80 bg-white/65 p-4 shadow-sm backdrop-blur">
                <span className="text-[10px] font-bold tracking-widest text-cyan-700">{n}</span>
                <p className="mt-3 text-xs font-semibold text-slate-800">{t}</p>
                <p className="mt-1 text-[10px] text-slate-400">{s}</p>
              </div>
            ))}
          </div>
          <p className="mt-12 text-[11px] text-slate-400">Independent prototype · Synthetic demonstration data</p>
        </div>

        <div className="mx-auto w-full max-w-[440px]">
          <div className="mb-7 flex items-center gap-3 lg:hidden">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#10243a] text-xs font-black text-cyan-300">OP</div>
            <div><p className="font-bold tracking-tight text-slate-950">OpsPilot</p><p className="text-[10px] uppercase tracking-widest text-slate-400">Operations intelligence</p></div>
          </div>
          <div className="rounded-[28px] border border-white bg-white/90 p-7 shadow-[0_24px_80px_rgba(15,23,42,.10)] backdrop-blur-xl sm:p-9">
            <div className="mb-8">
              <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-lg text-cyan-700">↗</div>
              <p className="text-[10px] font-bold uppercase tracking-[.18em] text-cyan-700">Secure workspace</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Welcome back</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">Sign in to continue to your operations dashboard.</p>
            </div>
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); go(email, password); }}>
              <label className="block text-xs font-semibold text-slate-700">Work email
                <input type="email" className="mt-2 min-h-11 w-full rounded-xl border border-slate-200 bg-slate-50/70 px-3.5 text-sm outline-none transition focus:border-cyan-600 focus:bg-white focus:ring-4 focus:ring-cyan-600/10" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" placeholder="you@company.com" required />
              </label>
              <label className="block text-xs font-semibold text-slate-700">Password
                <input type="password" className="mt-2 min-h-11 w-full rounded-xl border border-slate-200 bg-slate-50/70 px-3.5 text-sm outline-none transition focus:border-cyan-600 focus:bg-white focus:ring-4 focus:ring-cyan-600/10" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" placeholder="Enter your password" required />
              </label>
              {err && <ErrorBox>{err}</ErrorBox>}
              <Button type="submit" variant="primary" className="mt-2 min-h-11 w-full rounded-xl text-sm" disabled={busy}>{busy ? "Signing in…" : "Sign in to OpsPilot"} <span aria-hidden="true">→</span></Button>
            </form>
            {demo?.enabled && (
              <div className="mt-7 border-t border-slate-100 pt-6">
                <div className="flex items-center justify-between"><p className="text-[10px] font-bold uppercase tracking-[.16em] text-slate-400">Demo access</p><span className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-semibold text-amber-700">Synthetic data</span></div>
                <p className="mt-2 text-xs leading-relaxed text-slate-500">Try the analyst and approver roles to explore the four-eyes approval workflow.</p>
                <div className="mt-3 grid gap-2">
                  {demo.users.map((u) => (
                    <button type="button" key={u.email} disabled={busy} onClick={() => go(u.email, demo.password ?? "")}
                      className="flex items-center justify-between rounded-xl border border-slate-200 px-3.5 py-3 text-left transition hover:border-cyan-200 hover:bg-cyan-50/50 disabled:opacity-50">
                      <span><span className="block text-xs font-semibold text-slate-800">{u.name}</span><span className="mt-0.5 block text-[10px] text-slate-400">{u.email}</span></span>
                      <span className="rounded-lg bg-slate-100 px-2.5 py-1 text-[10px] font-semibold capitalize text-slate-600">{u.role}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <p className="mt-5 text-center text-[10px] leading-relaxed text-slate-400">Access is monitored. Actions are recorded in the audit trail.<br/>OpsPilot is an independent prototype and is not affiliated with any company.</p>
        </div>
      </section>
    </main>
  );
}

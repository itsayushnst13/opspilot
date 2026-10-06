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
    try { await login(e, p); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold text-slate-900">OpsPilot</h1>
        <p className="mt-1 text-sm text-slate-500">AI-assisted RFQ quoting, COA checks and export documents. Independent prototype on synthetic data.</p>
        <form className="mt-5 space-y-3" onSubmit={(e) => { e.preventDefault(); go(email, password); }}>
          <label className="block text-sm"><span className="text-slate-600">Email</span>
            <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></label>
          <label className="block text-sm"><span className="text-slate-600">Password</span>
            <input type="password" className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
          {err && <ErrorBox>{err}</ErrorBox>}
          <Button type="submit" variant="primary" className="w-full justify-center" disabled={busy}>Sign in</Button>
        </form>
        {demo?.enabled && (
          <div className="mt-6 border-t border-slate-100 pt-4">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Demo accounts (one click)</div>
            <p className="mt-1 text-xs text-slate-500">Quotes need a second person: submit as the analyst, approve as the approver (four-eyes rule).</p>
            <div className="mt-2 grid gap-2">
              {demo.users.map((u) => (
                <button key={u.email} disabled={busy} onClick={() => go(u.email, demo.password ?? "")}
                  className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50 disabled:opacity-50">
                  <span><span className="font-medium text-slate-800">{u.name}</span><span className="block text-xs text-slate-500">{u.email}</span></span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{u.role}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

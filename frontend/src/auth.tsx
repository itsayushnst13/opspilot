import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, hasToken, setToken } from "./api";

export type User = { email: string; name: string; role: "analyst" | "approver" | "admin" };
type Ctx = { user: User | null; loading: boolean; login: (email: string, password: string) => Promise<void>; logout: () => void };
const AuthCtx = createContext<Ctx>(null as unknown as Ctx);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(hasToken());

  useEffect(() => {
    if (hasToken()) api.get<User>("/api/auth/me").then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
    const out = () => setUser(null);
    window.addEventListener("opspilot:logout", out);
    return () => window.removeEventListener("opspilot:logout", out);
  }, []);

  const login = async (email: string, password: string) => {
    const r = await api.post<{ access_token: string; user: User }>("/api/auth/login", { email, password });
    setToken(r.access_token);
    setUser(r.user);
  };
  const logout = () => { setToken(null); setUser(null); };
  return <AuthCtx.Provider value={{ user, loading, login, logout }}>{children}</AuthCtx.Provider>;
}

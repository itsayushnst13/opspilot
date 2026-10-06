const KEY = "opspilot.token";
let token: string | null = (() => { try { return sessionStorage.getItem(KEY); } catch { return null; } })();

export function setToken(t: string | null) {
  token = t;
  try { t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}
export const hasToken = () => !!token;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function parse(res: Response) {
  if (res.ok) return res.status === 204 ? null : res.json();
  let msg = res.statusText;
  try {
    const j = await res.json();
    msg = typeof j.detail === "string" ? j.detail : j.errors ? j.errors.map((e: any) => e.msg).join("; ") : msg;
  } catch { /* non-json error */ }
  if (res.status === 401) { setToken(null); window.dispatchEvent(new Event("opspilot:logout")); }
  throw new ApiError(res.status, msg);
}

const headers = (extra: Record<string, string> = {}) => (token ? { Authorization: `Bearer ${token}`, ...extra } : extra);
const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export const api = {
  get: <T = any>(p: string): Promise<T> => fetch(BASE + p, { headers: headers() }).then(parse),
  post: <T = any>(p: string, body?: unknown): Promise<T> =>
    fetch(BASE + p, { method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body ?? {}) }).then(parse),
  patch: <T = any>(p: string, body: unknown): Promise<T> =>
    fetch(BASE + p, { method: "PATCH", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body) }).then(parse),
  upload: <T = any>(p: string, file: File): Promise<T> => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(BASE + p, { method: "POST", headers: headers(), body: fd }).then(parse);
  },
  async download(p: string, filename: string) {
    const res = await fetch(BASE + p, { headers: headers() });
    if (!res.ok) await parse(res);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  },
};

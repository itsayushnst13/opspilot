import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Fetch a resource; optionally re-fetch every `intervalMs` while `until` says it is not finished yet. */
export function useResource<T = any>(path: string | null, opts: { poll?: (d: T) => boolean; intervalMs?: number } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const pollRef = useRef(opts.poll);
  pollRef.current = opts.poll;

  const load = useCallback(async () => {
    if (!path) return null;
    try {
      const d = await api.get<T>(path);
      setData(d); setError(null);
      return d;
    } catch (e: any) {
      setError(e.message ?? "Request failed");
      return null;
    } finally { setLoading(false); }
  }, [path]);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    setLoading(!!path); setData(null);
    const tick = async () => {
      const d = await load();
      if (!stop && d && pollRef.current?.(d)) timer = setTimeout(tick, opts.intervalMs ?? 1000);
    };
    if (path) tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [path, load, opts.intervalMs]);

  return { data, error, loading, reload: load };
}

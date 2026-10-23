// Server-state cache tuned for responsiveness:
// - each component subscribes only to its own key, so a poll on one query never re-renders the rest of the page;
// - unchanged responses keep the previous object (no re-render when nothing changed);
// - cached data is shown immediately while a background refetch runs (stale-while-revalidate);
// - prefetch() lets links warm the next page on hover or focus.
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

type Entry = { data?: unknown; error?: Error; fetching: boolean; updatedAt: number; json?: string; promise?: Promise<void> };

const cache = new Map<string, Entry>();
const fetchers = new Map<string, () => Promise<unknown>>();
const listeners = new Map<string, Set<() => void>>();
const STALE_MS = 10_000;

function notify(key: string) {
  listeners.get(key)?.forEach((l) => l());
}

function load(key: string, force = false): Promise<void> {
  const fetcher = fetchers.get(key);
  if (!fetcher) return Promise.resolve();
  const prev = cache.get(key) ?? { fetching: false, updatedAt: 0 };
  if (prev.promise && !force) return prev.promise;
  const promise = fetcher()
    .then((data) => {
      const json = JSON.stringify(data);
      const cur = cache.get(key)!;
      if (json === cur.json) {
        cache.set(key, { ...cur, fetching: false, error: undefined, updatedAt: Date.now(), promise: undefined });
        if (cur.error) notify(key);
        return;
      }
      cache.set(key, { data, json, fetching: false, updatedAt: Date.now() });
      notify(key);
    })
    .catch((error: Error) => {
      if (error?.name === "AbortError") return;
      cache.set(key, { ...cache.get(key)!, error, fetching: false, promise: undefined });
      notify(key);
    });
  cache.set(key, { ...prev, fetching: true, promise });
  if (!prev.data) notify(key);
  return promise;
}

/** Refetch every cached query whose key starts with `prefix` (in the background). */
export function invalidate(prefix: string) {
  for (const key of cache.keys()) if (key.startsWith(prefix)) void load(key, true);
}

/** Warm a query before it is needed (link hover/focus). No-op if fresh data is cached. */
export function prefetch<T>(key: string, fetcher: () => Promise<T>) {
  fetchers.set(key, fetcher);
  const e = cache.get(key);
  if (e?.promise || (e?.data !== undefined && Date.now() - e.updatedAt < STALE_MS)) return;
  void load(key);
}

export function setQueryData<T>(key: string, data: T) {
  cache.set(key, { data, json: JSON.stringify(data), fetching: false, updatedAt: Date.now() });
  notify(key);
}

export function getQueryData<T>(key: string): T | undefined {
  return cache.get(key)?.data as T | undefined;
}

export function useQuery<T>(key: string | null, fetcher: () => Promise<T>, opts: { refetchMs?: number | false } = {}) {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  if (key) fetchers.set(key, () => fetcherRef.current());

  const subscribe = useCallback((cb: () => void) => {
    if (!key) return () => {};
    let set = listeners.get(key);
    if (!set) listeners.set(key, (set = new Set()));
    set.add(cb);
    return () => { set!.delete(cb); };
  }, [key]);
  const entry = useSyncExternalStore(subscribe, () => (key ? cache.get(key) : undefined));

  useEffect(() => {
    if (!key) return;
    const e = cache.get(key);
    if (!e || (!e.promise && (e.data === undefined || Date.now() - e.updatedAt > STALE_MS))) void load(key, !!e?.data);
  }, [key]);

  useEffect(() => {
    if (!key || !opts.refetchMs) return;
    const t = setInterval(() => { if (document.visibilityState === "visible") void load(key, true); }, opts.refetchMs);
    return () => clearInterval(t);
  }, [key, opts.refetchMs]);

  const refetch = useCallback(() => (key ? invalidate(key) : undefined), [key]);
  return {
    data: entry?.data as T | undefined,
    error: entry?.data === undefined ? entry?.error : undefined,
    loading: key ? entry?.data === undefined && !entry?.error : false,
    fetching: !!entry?.fetching,
    refetch,
  };
}

// Refresh what is on screen when the person comes back to the tab.
if (typeof window !== "undefined") {
  window.addEventListener("focus", () => {
    for (const [key, set] of listeners) if (set.size) void load(key, true);
  });
}

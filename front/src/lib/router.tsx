// Minimal History-API router: :param patterns, link interception, intent prefetch, scroll restoration,
// and View Transitions between pages where the browser supports them.
import { useSyncExternalStore, type FocusEvent, type MouseEvent, type ReactNode } from "react";

const listeners = new Set<() => void>();
const scrollPositions = new Map<string, number>();
let current = location.pathname + location.search;

function pathOf(url: string) {
  return url.split("?")[0];
}

let activeTransition = false;

function commit(update: () => void, scroll: () => void) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const doc = document as Document & {
    startViewTransition?: (cb: () => void) => { finished: Promise<unknown> };
  };
  const run = () => { update(); listeners.forEach((l) => l()); scroll(); };
  if (doc.startViewTransition && !reduce && !activeTransition) {
    activeTransition = true;
    const vt = doc.startViewTransition(run);
    vt.finished.catch(() => {}).finally(() => { activeTransition = false; });
  } else {
    run();
  }
}

history.scrollRestoration = "manual";
window.addEventListener("popstate", () => {
  const next = location.pathname + location.search;
  const changedPage = pathOf(next) !== pathOf(current);
  current = next;
  commit(() => {}, () => { if (changedPage) window.scrollTo(0, scrollPositions.get(pathOf(next)) ?? 0); });
});

export function navigate(to: string, opts: { replace?: boolean } = {}) {
  if (to === location.pathname + location.search) return;
  const samePage = pathOf(to) === location.pathname;
  scrollPositions.set(location.pathname, window.scrollY);
  // Same page, different query (a tab switch): update in place, keep the scroll position, no page transition.
  if (samePage) {
    (opts.replace ? history.replaceState : history.pushState).call(history, null, "", to);
    current = to;
    listeners.forEach((l) => l());
    return;
  }
  commit(() => {
    (opts.replace ? history.replaceState : history.pushState).call(history, null, "", to);
    current = to;
  }, () => window.scrollTo(0, 0));
}

export function useLocation() {
  return useSyncExternalStore((cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    () => location.pathname + location.search);
}

export function match(pattern: string, path: string): Record<string, string> | null {
  const p = pattern.split("/").filter(Boolean);
  const s = pathOf(path).split("/").filter(Boolean);
  if (p.length !== s.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < p.length; i++) {
    if (p[i].startsWith(":")) params[p[i].slice(1)] = decodeURIComponent(s[i]);
    else if (p[i] !== s[i]) return null;
  }
  return params;
}

export function useQueryParam(name: string): string | null {
  const loc = useLocation();
  return new URLSearchParams(loc.split("?")[1] ?? "").get(name);
}

// Pages register a prefetcher for their URL pattern; links call it on hover or focus.
const prefetchers: [string, (params: Record<string, string>) => void][] = [];
export function registerPrefetch(pattern: string, fn: (params: Record<string, string>) => void) {
  prefetchers.push([pattern, fn]);
}
function intent(to: string) {
  for (const [pattern, fn] of prefetchers) {
    const params = match(pattern, to);
    if (params) fn(params);
  }
}

export function Link({ to, className, children, ariaCurrent, title, style }:
  { to: string; className?: string; children: ReactNode; ariaCurrent?: boolean; title?: string; style?: Record<string, string> }) {
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    navigate(to);
  };
  return (
    <a href={to} onClick={onClick} onMouseEnter={() => intent(to)} onFocus={(_e: FocusEvent<HTMLAnchorElement>) => intent(to)}
      onTouchStart={() => intent(to)} className={className} aria-current={ariaCurrent ? "page" : undefined} title={title} style={style}>
      {children}
    </a>
  );
}

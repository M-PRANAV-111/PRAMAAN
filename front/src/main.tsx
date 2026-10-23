import { lazy, StrictMode, Suspense, useEffect, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { AppShell } from "./components/AppShell";
import { Empty, Skeleton, ToastProvider } from "./components/ui";
import { InstitutionHome } from "./pages/InstitutionHome";
import { Login } from "./pages/Login";
import { AuditPage, Benchmark, Rules } from "./pages/Oversight";
import { Queue } from "./pages/Queue";
import { Workspace } from "./pages/Workspace";
import { api } from "./api/client";
import { prefetch } from "./lib/query";
import { Link, match, navigate, registerPrefetch, useLocation } from "./lib/router";
import { SessionProvider, homeFor, useSession } from "./lib/session";

// The start page carries the scroll story; load it as its own chunk so signed-in screens never download it.
const Landing = lazy(() => import("./pages/Landing").then((m) => ({ default: m.Landing })));

type Role = "INSTITUTION" | "OFFICER" | "ADMIN" | "AUDITOR";
const ALL: Role[] = ["INSTITUTION", "OFFICER", "ADMIN", "AUDITOR"];
const OVERSIGHT: Role[] = ["OFFICER", "ADMIN", "AUDITOR"];

const ROUTES: { pattern: string; roles: Role[]; title: string; render: (p: Record<string, string>) => ReactElement }[] = [
  { pattern: "/institution", roles: ["INSTITUTION"], title: "Applications", render: () => <InstitutionHome /> },
  { pattern: "/queue", roles: OVERSIGHT, title: "Scrutiny queue", render: () => <Queue /> },
  { pattern: "/applications/:id", roles: ALL, title: "Application", render: (p) => <Workspace key={p.id} id={p.id} /> },
  { pattern: "/rules", roles: ALL, title: "Rule pack", render: () => <Rules /> },
  { pattern: "/audit", roles: OVERSIGHT, title: "Audit trail", render: () => <AuditPage /> },
  { pattern: "/benchmark", roles: OVERSIGHT, title: "Benchmark", render: () => <Benchmark /> },
];

// Warm the next page's data when a link is hovered, focused or touched, so navigation feels instant.
registerPrefetch("/applications/:id", ({ id }) => {
  prefetch(`application:${id}`, () => api("getApplication", { path: { application_id: id } }));
  prefetch(`findings:${id}:false`, () => api("listFindings", { path: { application_id: id }, query: { include_resolved: undefined } }));
  prefetch(`verifications:${id}`, () => api("listVerifications", { path: { application_id: id } }));
});
registerPrefetch("/queue", () => {
  prefetch("applications", () => api("listApplications"));
  prefetch("dashboard", () => api("dashboard"));
});
registerPrefetch("/institution", () => prefetch("applications", () => api("listApplications")));
registerPrefetch("/rules", () => prefetch("rules", () => api("getRules")));
registerPrefetch("/audit", () => prefetch("audit:all", () => api("listAudit", { query: { limit: "300" } })));
registerPrefetch("/benchmark", () => prefetch("benchmark", () => api("benchmark") as Promise<unknown>));

function Router() {
  const loc = useLocation();
  const path = loc.split("?")[0];
  const { user, ready } = useSession();
  const route = ROUTES.map((r) => ({ r, params: match(r.pattern, path) })).find((x) => x.params);

  useEffect(() => {
    document.title = route ? `${route.r.title} — PRAMAAN` : path === "/login" ? "Sign in — PRAMAAN" : "PRAMAAN — evidence-linked application validation";
  }, [route, path]);
  useEffect(() => {
    if (ready && route && !user) navigate(`/login`, { replace: true });
    if (ready && path === "/app" && user) navigate(homeFor(user), { replace: true });
  }, [ready, route, user, path]);

  if (path === "/") return <Suspense fallback={<div className="min-h-dvh" />}><Landing /></Suspense>;
  if (path === "/login") return <Login />;
  if (!ready) return <div className="p-8"><Skeleton /></div>;
  if (!route || !user) {
    return (
      <div className="grid min-h-dvh place-items-center p-6">
        <Empty title="This page does not exist" action={<Link to="/" className="btn btn-primary">Go to the start page</Link>}>
          Check the address, or start again from the home page.
        </Empty>
      </div>
    );
  }
  if (!route.r.roles.includes(user.role)) {
    return <AppShell><Empty title="Your role cannot open this page" action={<Link to={homeFor(user)} className="btn btn-primary">Back to your workspace</Link>} /></AppShell>;
  }
  return <AppShell>{route.r.render(route.params!)}</AppShell>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SessionProvider>
      <ToastProvider>
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-sm focus:bg-sheet focus:px-3 focus:py-2">Skip to content</a>
        <Router />
      </ToastProvider>
    </SessionProvider>
  </StrictMode>,
);

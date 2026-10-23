import { useEffect, useState, type ReactNode } from "react";
import { callEndpoint, hasEndpoint, useFeatures } from "../lib/features";
import { tr, useLang } from "../lib/i18n";
import { useQuery } from "../lib/query";
import { Link, useLocation } from "../lib/router";
import { ROLE_LABEL, useSession } from "../lib/session";
import { BlockWordmark } from "./BlockWordmark";
import { cx, useToast } from "./ui";

type BeforeInstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
let deferredInstall: BeforeInstallPromptEvent | null = null;
const installListeners = new Set<() => void>();

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstall = e as BeforeInstallPromptEvent;
    installListeners.forEach((cb) => cb());
  });
  window.addEventListener("appinstalled", () => {
    deferredInstall = null;
    installListeners.forEach((cb) => cb());
  });
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    });
  }
}

export function InstallPwaButton({ className }: { className?: string }) {
  const toast = useToast();
  const [, tick] = useState(0);
  useEffect(() => {
    const cb = () => tick((n) => n + 1);
    installListeners.add(cb);
    return () => { installListeners.delete(cb); };
  }, []);
  const standalone = typeof window !== "undefined" && window.matchMedia("(display-mode: standalone)").matches;
  if (standalone) return null;
  async function install() {
    if (deferredInstall) {
      await deferredInstall.prompt();
      await deferredInstall.userChoice.catch(() => {});
      deferredInstall = null;
      installListeners.forEach((cb) => cb());
    } else {
      toast("To install PRAMAAN: click the Install icon in your browser address bar, or tap Share → Add to Home Screen on mobile.");
    }
  }
  return (
    <button type="button" onClick={install} className={className ?? "shrink-0 py-2 text-xs font-medium text-ink-soft hover:text-ink"}>
      Install app
    </button>
  );
}

type NavItem = { to: string; label: string; roles: string[]; gate?: () => boolean };
const NAV: NavItem[] = [
  { to: "/institution", label: "Applications", roles: ["INSTITUTION"] },
  { to: "/queue", label: "Scrutiny queue", roles: ["OFFICER", "ADMIN", "AUDITOR"] },
  { to: "/rules", label: "Rule pack", roles: ["INSTITUTION", "OFFICER", "ADMIN", "AUDITOR"] },
  { to: "/audit", label: "Audit trail", roles: ["OFFICER", "ADMIN", "AUDITOR"] },
  { to: "/benchmark", label: "Benchmark", roles: ["OFFICER", "ADMIN", "AUDITOR"] },
  { to: "/admin/registrations", label: "Registrations", roles: ["ADMIN"], gate: () => hasEndpoint("listRegistrations") },
  { to: "/admin/users", label: "Users", roles: ["ADMIN"], gate: () => hasEndpoint("listUsers") },
  { to: "/admin/system", label: "System", roles: ["ADMIN"], gate: () => hasEndpoint("aiStatus") || hasEndpoint("adminSystem") },
  { to: "/account", label: "Account", roles: ["INSTITUTION", "OFFICER", "ADMIN", "AUDITOR"], gate: () => hasEndpoint("getAccount") || hasEndpoint("changePassword") },
  { to: "/help", label: "Help", roles: ["INSTITUTION", "OFFICER", "ADMIN", "AUDITOR"] },
];

/** Small square-cut wordmark used in headers and the sign-in page. */
export function Wordmark({ small }: { small?: boolean }) {
  return <BlockWordmark className={small ? "h-6 w-auto" : "h-8 w-auto"} />;
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut, expiresSoon, staySignedIn } = useSession();
  const { features } = useFeatures();
  const [lang, setLang] = useLang();
  const [offline, setOffline] = useState(typeof navigator !== "undefined" ? !navigator.onLine : false);
  const loc = useLocation();

  useEffect(() => {
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  const unread = useQuery(
    user && features.notifications && hasEndpoint("unreadNotificationsCount") ? "notifications:unread" : null,
    () => callEndpoint<{ count: number }>("unreadNotificationsCount"),
    { refetchMs: 30_000 },
  );

  if (!user) return <>{children}</>;
  const items = NAV.filter((n) => n.roles.includes(user.role) && (!n.gate || n.gate()));
  const home = items[0]?.to ?? "/";
  const isActive = (n: NavItem) => loc.startsWith(n.to) || (loc.startsWith("/applications") && n.to === home);
  return (
    <div className="min-h-dvh">
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="bg-ink text-paper" style={{ viewTransitionName: "app-header" } as Record<string, string>}>
        <div className="mx-auto flex max-w-[1600px] items-end justify-between gap-4 px-4 pt-4 pb-3 sm:px-6">
          <Link to={home} className="text-paper" title="PRAMAAN home"><BlockWordmark className="h-7 w-auto sm:h-9" /></Link>
          <div className="hidden text-right text-xs leading-tight text-paper/75 sm:block">
            <div className="font-medium text-paper">{user.name}</div>
            <div>{ROLE_LABEL[user.role]}{user.institution_name ? `, ${user.institution_name}` : ""}</div>
          </div>
        </div>
        <nav aria-label="Main" className="strip border-b border-ink/15">
          <div className="mx-auto flex max-w-[1600px] items-stretch gap-5 overflow-x-auto px-4 sm:px-6">
            {items.map((n) => (
              <Link key={n.to} to={n.to} ariaCurrent={isActive(n)}
                className={cx("shrink-0 py-2 font-medium decoration-2 underline-offset-[6px]",
                  isActive(n) ? "underline decoration-tape" : "no-underline text-ink-soft hover:text-ink")}>
                {tr(n.label, lang)}
              </Link>
            ))}
            <span className="flex-1" />
            {features.notifications && (
              <Link to="/notifications" className="shrink-0 py-2 font-medium text-ink-soft hover:text-ink">
                {tr("Notifications", lang)}{unread.data?.count ? ` (${unread.data.count})` : ""}
              </Link>
            )}
            <button type="button" aria-label={lang === "en" ? "Switch language to Hindi" : "Switch language to English"}
              className="shrink-0 py-2 text-xs font-medium text-ink-soft hover:text-ink"
              onClick={() => setLang(lang === "en" ? "hi" : "en")}>
              {lang === "en" ? "हिन्दी" : "EN"}
            </button>
            <InstallPwaButton />
            <span className="shrink-0 py-2 text-ink-soft sm:hidden">{ROLE_LABEL[user.role]}</span>
            <button className="shrink-0 py-2 font-medium" onClick={signOut} aria-label="Sign out">{tr("Sign out", lang)}</button>
          </div>
        </nav>
      </header>
      {offline && (
        <div role="status" className="border-b border-tape bg-tape-wash px-4 py-2 text-center text-xs font-semibold text-tape">
          You appear to be offline. Changes and uploads will resume when your connection returns.
        </div>
      )}
      {expiresSoon && (
        <div role="status" className="flex flex-wrap items-center justify-center gap-3 border-b border-turmeric bg-turmeric-wash px-4 py-2 text-xs font-semibold text-turmeric">
          <span>Your session will expire in less than 2 minutes.</span>
          <button type="button" className="btn btn-quiet min-h-7 px-2.5 text-xs" onClick={staySignedIn}>Stay signed in</button>
        </div>
      )}
      <main id="main" className="mx-auto min-w-0 max-w-[1600px] px-4 py-6 sm:px-6 lg:py-8">{children}</main>
    </div>
  );
}

export function PageHeader({ title, lead, actions, kicker }: { title: string; lead?: ReactNode; actions?: ReactNode; kicker?: ReactNode }) {
  return (
    <div className="mb-8 grid gap-4 border-b border-ink pb-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
      <div className="min-w-0">
        {kicker && <div className="mb-3 text-sm text-ink-soft">{kicker}</div>}
        <h1 className="text-[2.25rem] sm:text-[3.25rem] lg:text-[4rem]">{title}</h1>
        {lead && <div className="mt-4 max-w-4xl text-ink-soft">{lead}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2 lg:justify-end">{actions}</div>}
    </div>
  );
}

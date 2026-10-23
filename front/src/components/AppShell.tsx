import type { ReactNode } from "react";
import { Link, useLocation } from "../lib/router";
import { ROLE_LABEL, useSession } from "../lib/session";
import { BlockWordmark } from "./BlockWordmark";
import { cx } from "./ui";

type NavItem = { to: string; label: string; roles: string[] };
const NAV: NavItem[] = [
  { to: "/institution", label: "Applications", roles: ["INSTITUTION"] },
  { to: "/queue", label: "Scrutiny queue", roles: ["OFFICER", "ADMIN", "AUDITOR"] },
  { to: "/rules", label: "Rule pack", roles: ["INSTITUTION", "OFFICER", "ADMIN", "AUDITOR"] },
  { to: "/audit", label: "Audit trail", roles: ["OFFICER", "ADMIN", "AUDITOR"] },
  { to: "/benchmark", label: "Benchmark", roles: ["OFFICER", "ADMIN", "AUDITOR"] },
];

/** Small square-cut wordmark used in headers and the sign-in page. */
export function Wordmark({ small }: { small?: boolean }) {
  return <BlockWordmark className={small ? "h-6 w-auto" : "h-8 w-auto"} />;
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut } = useSession();
  const loc = useLocation();
  if (!user) return <>{children}</>;
  const items = NAV.filter((n) => n.roles.includes(user.role));
  const home = items[0]?.to ?? "/";
  const isActive = (n: NavItem) => loc.startsWith(n.to) || (loc.startsWith("/applications") && n.to === home);
  return (
    <div className="min-h-dvh">
      <header className="bg-ink text-paper" style={{ viewTransitionName: "app-header" } as Record<string, string>}>
        <div className="mx-auto flex max-w-[1600px] items-end justify-between gap-4 px-4 pt-4 pb-3 sm:px-6">
          <Link to={home} className="text-paper" title="PRAMAAN home"><BlockWordmark className="h-7 w-auto sm:h-9" /></Link>
          <div className="hidden text-right text-xs leading-tight text-paper/75 sm:block">
            <div className="font-medium text-paper">{user.name}</div>
            <div>{ROLE_LABEL[user.role]}{user.institution_name ? `, ${user.institution_name}` : ""}</div>
          </div>
        </div>
        <nav aria-label="Main" className="strip border-b border-ink/15">
          <div className="mx-auto flex max-w-[1600px] items-stretch gap-6 overflow-x-auto px-4 sm:px-6">
            {items.map((n) => (
              <Link key={n.to} to={n.to} ariaCurrent={isActive(n)}
                className={cx("shrink-0 py-2 font-medium decoration-2 underline-offset-[6px]",
                  isActive(n) ? "underline decoration-tape" : "no-underline text-ink-soft hover:text-ink")}>
                {n.label}
              </Link>
            ))}
            <span className="flex-1" />
            <span className="shrink-0 py-2 text-ink-soft sm:hidden">{ROLE_LABEL[user.role]}</span>
            <button className="shrink-0 py-2 font-medium" onClick={signOut}>Sign out</button>
          </div>
        </nav>
      </header>
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

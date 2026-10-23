import { useState } from "react";
import { api, type ApplicationStatus, type DashboardOut } from "../api/client";
import { PageHeader } from "../components/AppShell";
import { Empty, ErrorBox, Pill, Skeleton, cx } from "../components/ui";
import { STATUS_META, VERIFICATION_META, fmtDate, plural } from "../lib/format";
import { useQuery } from "../lib/query";
import { Link } from "../lib/router";

const ORDER: ApplicationStatus[] = ["DEFICIENCIES_FLAGGED", "MANUAL_REVIEW_REQUIRED", "PROCESSING", "READY_FOR_SCRUTINY", "DRAFT"];
const BAR: Record<string, string> = { tape: "bg-tape", turmeric: "bg-turmeric", leaf: "bg-leaf", dusk: "bg-dusk", neutral: "bg-rule-strong" };

function Distribution({ d }: { d: DashboardOut }) {
  const v = Object.entries(d.verification_by_status) as [keyof typeof VERIFICATION_META, number][];
  const total = v.reduce((s, [, n]) => s + n, 0);
  return (
    <section className="sheet grid gap-6 p-5 md:grid-cols-[1fr_1fr_auto]" aria-label="Summary of submitted applications">
      <div>
        <div className="font-display text-[3rem] leading-none tracking-[-0.04em]">{d.applications}</div>
        <div className="text-sm text-ink-soft">submitted {d.applications === 1 ? "application" : "applications"}, {plural(d.open_findings, "open finding")}</div>
        <div className="mt-3 text-sm text-ink-soft">{plural(d.reviews_recorded, "officer decision")} recorded</div>
      </div>
      <div>
        <div className="mb-2 text-sm font-semibold">Documents by source-verification result</div>
        {total === 0 ? <p className="text-sm text-ink-soft">No verifiable documents yet.</p> : (
          <>
            <div className="flex h-3 overflow-hidden rounded-full bg-rule" role="img"
              aria-label={v.map(([s, n]) => `${VERIFICATION_META[s].label}: ${n}`).join(", ")}>
              {v.map(([s, n]) => <span key={s} className={BAR[VERIFICATION_META[s].tone]} style={{ width: `${(n / total) * 100}%` }} />)}
            </div>
            <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
              {v.map(([s, n]) => (
                <li key={s} className="flex items-center gap-1.5"><span className={cx("h-2 w-2 rounded-full", BAR[VERIFICATION_META[s].tone])} />{VERIFICATION_META[s].label} {n}</li>
              ))}
            </ul>
          </>
        )}
      </div>
      {d.simulated_sources_in_use && (
        <p className="max-w-[16rem] self-center rounded-sm bg-dusk-wash px-3 py-2 text-xs text-dusk">
          Some results come from simulated AICTE records or issuer registries. They are labelled wherever they appear.
        </p>
      )}
    </section>
  );
}

export function Queue() {
  const [filter, setFilter] = useState<ApplicationStatus | "ALL">("ALL");
  const dash = useQuery("dashboard", () => api("dashboard"), { refetchMs: 15000 });
  const apps = useQuery("applications", () => api("listApplications"), { refetchMs: 15000 });
  const list = (apps.data ?? []).filter((a) => filter === "ALL" || a.status === filter)
    .sort((x, y) => ORDER.indexOf(x.status) - ORDER.indexOf(y.status) || y.counts.active - x.counts.active);
  const counts = Object.fromEntries(ORDER.map((s) => [s, (apps.data ?? []).filter((a) => a.status === s).length]));
  return (
    <>
      <PageHeader title="Scrutiny queue" lead="Applications submitted to AICTE, with deficiencies first. Statuses are derived from findings; none of them is a decision." />
      {dash.data && <div className="mb-6"><Distribution d={dash.data} /></div>}
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        {(["ALL", ...ORDER] as const).map((s) => (s === "ALL" || counts[s] > 0) && (
          <button key={s} onClick={() => setFilter(s)} aria-pressed={filter === s}
            className={cx("rounded-full px-3 py-1.5 text-sm font-semibold transition-colors",
              filter === s ? "bg-ink text-paper" : "bg-sheet text-ink-soft shadow-[inset_0_0_0_1px_var(--color-rule-strong)] hover:text-ink")}>
            {s === "ALL" ? `All (${apps.data?.length ?? 0})` : `${STATUS_META[s].label} (${counts[s]})`}
          </button>
        ))}
      </div>
      {apps.error ? <ErrorBox error={apps.error} retry={apps.refetch} /> : !apps.data ? <Skeleton rows={4} /> : list.length === 0 ? (
        <Empty title="No applications here">Applications appear once an institution submits them.</Empty>
      ) : (
        <div className="sheet overflow-x-auto">
          <table className="w-full min-w-[46rem] text-sm">
            <thead>
              <tr className="border-b border-rule text-left text-ink-soft">
                <th className="px-4 py-3 font-semibold">Institution</th>
                <th className="px-4 py-3 font-semibold">Category</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 text-right font-semibold">Deficiencies</th>
                <th className="px-4 py-3 text-right font-semibold">For review</th>
                <th className="px-4 py-3 font-semibold">Submitted</th>
              </tr>
            </thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id} className="border-b border-rule/60 last:border-0 hover:bg-paper/70">
                  <td className="px-4 py-3">
                    <Link to={`/applications/${a.id}`} className="link font-semibold">{a.institution.name}</Link>
                    <div className="text-xs text-ink-soft">{a.institution.aicte_permanent_id}, {a.institution.state}</div>
                  </td>
                  <td className="px-4 py-3">{a.category_label}<div className="text-xs text-ink-soft">{a.academic_year}</div></td>
                  <td className="px-4 py-3"><Pill tone={STATUS_META[a.status].tone}>{STATUS_META[a.status].label}</Pill></td>
                  <td className={cx("px-4 py-3 text-right font-semibold", a.counts.deficiencies ? "text-tape" : "text-ink-faint")}>{a.counts.deficiencies}</td>
                  <td className={cx("px-4 py-3 text-right font-semibold", a.counts.reviews ? "text-turmeric" : "text-ink-faint")}>{a.counts.reviews}</td>
                  <td className="px-4 py-3 text-ink-soft">{fmtDate(a.submitted_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

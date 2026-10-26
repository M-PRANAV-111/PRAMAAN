import { useState, type ChangeEvent } from "react";
import { api, type ApplicationStatus, type DashboardOut } from "../api/client";
import { PageHeader } from "../components/AppShell";
import { Empty, ErrorBox, Pill, Skeleton, cx } from "../components/ui";
import { STATUS_META, VERIFICATION_META, fmtDate, plural } from "../lib/format";
import { useQuery } from "../lib/query";
import { Link, navigate, useQueryParam } from "../lib/router";
import { useSession } from "../lib/session";
import { OnboardingTips } from "./Help";

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

type SortKey = "status" | "institution" | "deficiencies" | "reviews" | "submitted";

export function Queue() {
  const { user } = useSession();
  const filter = (useQueryParam("status") as ApplicationStatus | "ALL" | null) ?? "ALL";
  const q = useQueryParam("q") ?? "";
  const offset = Math.max(0, Number(useQueryParam("offset")) || 0);
  const [total, setTotal] = useState(0);
  const sort = (useQueryParam("sort") as SortKey | null) ?? "status";
  const dir = (useQueryParam("dir") as "asc" | "desc" | null) ?? "asc";

  function updateParams(patch: Record<string, string | null>) {
    const sp = new URLSearchParams(location.search);
    if ("q" in patch || "status" in patch) sp.delete("offset");
    for (const [k, v] of Object.entries(patch)) {
      if (!v || v === "ALL" || (k === "sort" && v === "status") || (k === "dir" && v === "asc")) sp.delete(k);
      else sp.set(k, v);
    }
    const qs = sp.toString();
    navigate(qs ? `/queue?${qs}` : "/queue", { replace: true });
  }

  function toggleSort(key: SortKey) {
    if (sort === key) updateParams({ dir: dir === "asc" ? "desc" : "asc" });
    else updateParams({ sort: key, dir: "asc" });
  }

  const dash = useQuery("dashboard", () => api("dashboard"), { refetchMs: 15000 });
  const apps = useQuery(`applications:queue:${q}:${filter}:${offset}`, () => api("listApplications", {
    query: { q, status: filter === "ALL" ? undefined : filter, limit: "25", offset: String(offset) },
    onResponse: response => setTotal(Number(response.headers.get("X-Total-Count") ?? 0)),
  }), { refetchMs: 15000 });
  const list = [...(apps.data ?? [])]
    .sort((x, y) => {
      const mul = dir === "desc" ? -1 : 1;
      if (sort === "institution") return mul * x.institution.name.localeCompare(y.institution.name);
      if (sort === "deficiencies") return mul * (y.counts.deficiencies - x.counts.deficiencies);
      if (sort === "reviews") return mul * (y.counts.reviews - x.counts.reviews);
      if (sort === "submitted") return mul * (y.submitted_at ?? "").localeCompare(x.submitted_at ?? "");
      return mul * (ORDER.indexOf(x.status) - ORDER.indexOf(y.status) || y.counts.active - x.counts.active);
    });
  // The list is one server-filtered page, so status totals come from the dashboard (same visibility scope).
  const counts = Object.fromEntries(ORDER.map((s) => [s, dash.data?.by_status[s] ?? 0]));
  const allCount = dash.data?.applications;
  return (
    <>
      <PageHeader title="Scrutiny queue" lead="Applications submitted to AICTE, with deficiencies first. Statuses are derived from findings; none of them is a decision." />
      {user && <OnboardingTips role={user.role} />}
      {dash.data && <div className="mb-6"><Distribution d={dash.data} /></div>}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          {(["ALL", ...ORDER] as const).map((s) => (s === "ALL" || counts[s] > 0 || filter === s) && (
            <button key={s} onClick={() => updateParams({ status: s })} aria-pressed={filter === s}
              className={cx("rounded-full px-3 py-1.5 text-sm font-semibold transition-colors",
                filter === s ? "bg-ink text-paper" : "bg-sheet text-ink-soft shadow-[inset_0_0_0_1px_var(--color-rule-strong)] hover:text-ink")}>
              {s === "ALL" ? (allCount === undefined ? "All" : `All (${allCount})`) : `${STATUS_META[s].label} (${counts[s]})`}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="sr-only">Search by institution name or Permanent ID</span>
          <input type="search" className="input min-h-9 w-64 text-sm" placeholder="Search institution or Permanent ID…"
            value={q} onChange={(e: ChangeEvent<HTMLInputElement>) => updateParams({ q: e.target.value })} />
        </label>
      </div>
      <div className="mb-3 flex items-center justify-between gap-3 text-sm">
        <span>{total} matching applications</span>
        <div className="flex gap-2">
          <button className="btn btn-quiet" disabled={offset === 0} onClick={() => updateParams({ offset: String(Math.max(0, offset - 25)) })}>Previous</button>
          <button className="btn btn-quiet" disabled={offset + 25 >= total} onClick={() => updateParams({ offset: String(offset + 25) })}>Next</button>
        </div>
      </div>
      {apps.error ? <ErrorBox error={apps.error} retry={apps.refetch} /> : !apps.data ? <Skeleton rows={4} /> : list.length === 0 ? (
        <Empty title="No applications here">Applications appear once an institution submits them.</Empty>
      ) : (
        <div className="sheet overflow-x-auto">
          <table className="w-full min-w-[46rem] text-sm">
            <thead>
              <tr className="border-b border-rule text-left text-ink-soft">
                <th className="px-4 py-3 font-semibold"><button type="button" className="hover:text-ink" onClick={() => toggleSort("institution")}>Institution</button></th>
                <th className="px-4 py-3 font-semibold">Category</th>
                <th className="px-4 py-3 font-semibold"><button type="button" className="hover:text-ink" onClick={() => toggleSort("status")}>Status</button></th>
                <th className="px-4 py-3 text-right font-semibold"><button type="button" className="hover:text-ink" onClick={() => toggleSort("deficiencies")}>Deficiencies</button></th>
                <th className="px-4 py-3 text-right font-semibold"><button type="button" className="hover:text-ink" onClick={() => toggleSort("reviews")}>For review</button></th>
                <th className="px-4 py-3 font-semibold"><button type="button" className="hover:text-ink" onClick={() => toggleSort("submitted")}>Submitted</button></th>
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
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Pill tone={STATUS_META[a.status].tone}>{STATUS_META[a.status].label}</Pill>
                      {a.counts.active === 0 && <span className="text-xs text-ink-soft">No open findings</span>}
                    </div>
                  </td>
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

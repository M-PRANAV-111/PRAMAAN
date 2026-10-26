import type { ApplicationDetail, RoutingOut } from "../../api/client";
import { callEndpoint, useFeatures } from "../../lib/features";
import { plural } from "../../lib/format";
import { useQuery } from "../../lib/query";
import { Link } from "../../lib/router";
import { Pill } from "../ui";

type Reason = { text: string; to?: string; code?: string };

/** Routing recommendation (advisory). Falls back to the derived status when routing is not available. */
export function OutcomeCard({
  app,
  onOpenPlan,
  onDownloadReport,
}: {
  app: ApplicationDetail;
  onOpenPlan: () => void;
  onDownloadReport?: () => void;
}) {
  const { features } = useFeatures();
  const routing = useQuery(
    features.routing ? `routing:${app.id}` : null,
    () => callEndpoint<RoutingOut>("applicationRouting", { path: { application_id: app.id } }),
  );

  const outcome = routing.data?.outcome;
  const kind = outcome === "READY_FOR_SCRUTINY" || (!outcome && app.status === "READY_FOR_SCRUTINY") ? "ready"
    : outcome === "CORRECTIONS_REQUIRED" || (!outcome && app.status === "DEFICIENCIES_FLAGGED") ? "corrections"
    : "review";
  const meta = kind === "ready"
    ? { tone: "leaf" as const, title: "Ready for scrutiny", lead: "No open findings · sources answered. Routed to the AICTE scrutiny queue; officials still decide." }
    : kind === "corrections"
    ? { tone: "tape" as const, title: "Corrections required", lead: `${plural(app.counts.deficiencies, "deficiency", "deficiencies")} can be fixed before scrutiny.` }
    : { tone: "turmeric" as const, title: "Officer review required", lead: `${plural(app.counts.reviews || app.counts.active, "item")} need an official to confirm with evidence attached.` };

  const reasons: Reason[] = routing.data
    ? routing.data.reasons.map((r) => ({
        text: r.text,
        code: r.code,
        to: r.finding_id ? `/applications/${app.id}?tab=findings&finding=${r.finding_id}`
          : r.document_id ? `/applications/${app.id}?tab=documents` : undefined,
      }))
    : [
        app.counts.deficiencies > 0 ? `${plural(app.counts.deficiencies, "deficiency", "deficiencies")} raised by Handbook rules.` : null,
        app.counts.reviews > 0 ? `${plural(app.counts.reviews, "item")} routed for official review.` : null,
        app.counts.active === 0 ? "All evaluated rules passed and no integrity indicator was raised." : null,
      ].filter((t): t is string => !!t).map((text) => ({ text }));

  return (
    <div data-outcome-card data-outcome={outcome ?? ""} className="rounded-sm border border-rule bg-paper p-4 text-sm animate-rise">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Pill tone={meta.tone}>{meta.title}</Pill>
        <span className="text-xs text-ink-soft">Routing recommendation — officials decide</span>
      </div>
      <p className="mt-2 font-semibold">{meta.lead}</p>
      {reasons.length > 0 && (
        <ul className="mt-1.5 grid gap-1 text-xs text-ink-soft">
          {reasons.map((r, i) => (
            <li key={i} data-reason-code={r.code}>• {r.to ? <Link to={r.to} className="underline">{r.text}</Link> : r.text}</li>
          ))}
        </ul>
      )}
      {routing.data?.ai_used && (
        <p className="mt-1.5 text-xs text-dusk">AI assistance contributed; every value it supplied was matched to the page or left for an officer.</p>
      )}
      {(routing.data?.automated_actions.length ?? 0) > 0 && (
        <ul className="mt-1.5 grid gap-1 text-xs text-ink-soft" aria-label="Automated actions">
          {routing.data!.automated_actions.map((a, i) => <li key={i}>Automated: {a.summary}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn btn-primary min-h-8 px-3 text-xs" onClick={onOpenPlan}>See what to fix</button>
        {onDownloadReport && (
          <button type="button" className="btn btn-quiet min-h-8 px-3 text-xs" onClick={onDownloadReport}>Download report</button>
        )}
      </div>
    </div>
  );
}

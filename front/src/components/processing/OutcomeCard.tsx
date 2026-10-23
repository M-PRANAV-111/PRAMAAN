import type { ApplicationDetail } from "../../api/client";
import { callEndpoint, useFeatures } from "../../lib/features";
import { plural } from "../../lib/format";
import { useQuery } from "../../lib/query";
import { Pill } from "../ui";

type RoutingOut = {
  outcome: "READY_FOR_SCRUTINY" | "DEFICIENCIES_FLAGGED" | "MANUAL_REVIEW_REQUIRED";
  reasons: string[];
};

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

  const status = routing.data?.outcome ?? app.status;
  const meta = status === "READY_FOR_SCRUTINY"
    ? { tone: "leaf" as const, title: "Ready for scrutiny", lead: "No open findings · sources answered. Routed to the AICTE scrutiny queue; officials still decide." }
    : status === "DEFICIENCIES_FLAGGED"
    ? { tone: "tape" as const, title: "Corrections required", lead: `${plural(app.counts.deficiencies, "deficiency", "deficiencies")} can be fixed before scrutiny.` }
    : { tone: "turmeric" as const, title: "Officer review required", lead: `${plural(app.counts.reviews || app.counts.active, "item")} need an official to confirm with evidence attached.` };

  const reasons = routing.data?.reasons ?? [
    app.counts.deficiencies > 0 ? `${plural(app.counts.deficiencies, "deficiency", "deficiencies")} raised by Handbook rules.` : null,
    app.counts.reviews > 0 ? `${plural(app.counts.reviews, "item")} routed for official review.` : null,
    app.counts.active === 0 ? "All evaluated rules passed and no integrity indicator was raised." : null,
  ].filter(Boolean) as string[];

  return (
    <div data-outcome-card className="rounded-sm border border-rule bg-paper p-4 text-sm animate-rise">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Pill tone={meta.tone}>{meta.title}</Pill>
        <span className="text-xs text-ink-soft">Routing recommendation — officials decide</span>
      </div>
      <p className="mt-2 font-semibold">{meta.lead}</p>
      {reasons.length > 0 && (
        <ul className="mt-1.5 grid gap-1 text-xs text-ink-soft">
          {reasons.map((r, i) => <li key={i}>• {r}</li>)}
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

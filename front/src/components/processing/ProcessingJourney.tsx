import { useState } from "react";
import { api, type ApplicationDetail, type JobOut } from "../../api/client";
import { CHANNEL_LABEL, SUGGESTION_REASON, VERIFICATION_META, label } from "../../lib/format";
import { useQuery } from "../../lib/query";
import { Pill, SimulatedTag } from "../ui";
import { JourneySheet } from "./JourneySheet";
import { OutcomeCard } from "./OutcomeCard";
import { StageRail } from "./StageRail";
import { STEPS } from "./stages";
import { useJobProgress } from "./useJobProgress";

export function ProcessingJourney({
  job: initialJob,
  documentId,
  app,
  onOpenPlan,
  onRetry,
  onDownloadReport,
}: {
  job: JobOut;
  documentId: string | null;
  app: ApplicationDetail;
  onOpenPlan: () => void;
  onRetry: () => void;
  onDownloadReport?: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const prog = useJobProgress(initialJob);
  const docId = documentId ?? prog.job?.document_id ?? null;
  const ev = useQuery(docId && prog.step >= 2 ? `evidence:${docId}:${prog.state}` : null,
    () => api("documentEvidence", { path: { document_id: docId! } }));
  const verifs = useQuery(prog.step >= 4 ? `verifications:${app.id}:${prog.state}` : null,
    () => api("listVerifications", { path: { application_id: app.id } }));

  const reduceMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const failed = prog.state === "FAILED";
  const stepName = STEPS[prog.step] ?? "Upload";
  const history = prog.job?.stage_history ?? [];
  const notes = prog.job?.ai_notes ?? [];

  return (
    <section aria-label="Document verification journey" data-stage-code={prog.stageCode} className="sheet mb-6 grid gap-4 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule pb-3">
        <div>
          <div className="text-xs font-semibold text-ink-soft">In-app document verification journey</div>
          <div role="status" aria-live="polite" className="text-sm font-semibold">
            Step {prog.step + 1} of 6: {stepName}. {prog.stageLabel}
            {prog.slow && !failed && prog.state !== "DONE" ? ` — Still working: ${prog.stageLabel}` : ""}
          </div>
        </div>
        <button type="button" className="btn btn-quiet min-h-8 px-2.5 text-xs" onClick={() => setCollapsed((c) => !c)}>
          {collapsed ? "Show journey" : "Hide journey"}
        </button>
      </div>

      {!collapsed && (
        <>
          <StageRail step={prog.step} failed={failed} aiAssisted={prog.aiAssisted} />
          {history.length > 0 && <details><summary className="text-sm">Recorded processing stages</summary>
            <ol data-stage-history className="grid gap-1 text-xs">{history.map((code, i) => <li key={i} data-code={code}>{code.replaceAll("_", " ").toLowerCase()}</li>)}</ol>
          </details>}
          {notes.map(note => <p key={note} role="status" className="text-sm text-dusk">{note}</p>)}
          {(ev.data?.ai_suggestions ?? []).map((suggestion, i) => <p key={i} data-ai-suggestion={suggestion.field} className="text-sm text-turmeric">
            AI suggestion — {SUGGESTION_REASON[suggestion.reason]}, not used by any rule: {label(suggestion.field)}: {suggestion.value}
          </p>)}

          {!reduceMotion && (
            <JourneySheet
              documentId={docId}
              step={prog.step}
              failed={failed}
              reduceMotion={reduceMotion}
              claims={ev.data?.claims ?? []}
              hasDeficiency={app.counts.deficiencies > 0}
              hasTextLayer={ev.data?.document.has_text_layer}
            />
          )}

          {prog.step >= 4 && (verifs.data?.length ?? 0) > 0 && (
            <div className="grid gap-1.5 text-xs">
              <div className="font-semibold text-ink-soft">Verification ladder</div>
              <ul className="flex flex-wrap gap-2">
                {(verifs.data ?? []).slice(0, 4).map((v) => (
                  <li key={v.id} className="flex items-center gap-1.5 rounded-sm bg-paper px-2 py-1">
                    <span>Tier {v.tier} ({CHANNEL_LABEL[v.channel] ?? v.channel}):</span>
                    <Pill tone={VERIFICATION_META[v.status].tone}>{VERIFICATION_META[v.status].label}</Pill>
                    {v.simulated && <SimulatedTag />}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {failed && (
            <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-sm border-l-4 border-tape bg-tape-wash px-3 py-2 text-sm">
              <span className="font-semibold text-tape">{prog.error ?? "The document could not be processed. Try a clearer copy or run the check again."}</span>
              <button type="button" className="btn btn-quiet min-h-8 px-3 text-xs" onClick={onRetry}>Retry</button>
            </div>
          )}

          {prog.step >= 5 && !failed && (
            <OutcomeCard app={app} onOpenPlan={onOpenPlan} onDownloadReport={onDownloadReport} />
          )}
        </>
      )}
    </section>
  );
}

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  api, ApiError, pageImageUrl, type ApplicationDetail, type ChecklistItemOut, type FindingOut, type JobOut, type RepairAction, type ReviewDecision,
  type VerificationOut,
} from "../api/client";
import { PageHeader } from "../components/AppShell";
import { EvidenceViewer, type Box } from "../components/EvidenceViewer";
import { ProofChain } from "../components/ProofChain";
import { ProcessingJourney } from "../components/processing/ProcessingJourney";
import { UploadSlot } from "../components/UploadSlot";
import { Dialog, Empty, ErrorBox, Pill, SimulatedTag, Skeleton, Spinner, cx, useToast } from "../components/ui";
import { callEndpoint, hasEndpoint, useFeatures } from "../lib/features";
import {
  CHANNEL_LABEL, FINDING_STATE_LABEL, SEVERITY_META, STATUS_META, VERIFICATION_META, fmtBytes, fmtDate, label, plural,
} from "../lib/format";
import { invalidate, useQuery } from "../lib/query";
import { navigate, useQueryParam } from "../lib/router";
import { useSession } from "../lib/session";
import { ProgressBar } from "./InstitutionHome";

type Tab = "findings" | "documents" | "plan" | "activity";

export function Workspace({ id }: { id: string }) {
  const { user } = useSession();
  const isInstitution = user?.role === "INSTITUTION";
  const canReview = user?.role === "OFFICER" || user?.role === "ADMIN";
  const tabParam = useQueryParam("tab") as Tab | null;
  const [tab, setTabState] = useState<Tab>(tabParam ?? (isInstitution ? "documents" : "findings"));
  const setTab = (t: Tab) => { setTabState(t); navigate(`/applications/${id}?tab=${t}`, { replace: true }); };
  const [selected, setSelected] = useState<string | null>(null);
  const [journeyState, setJourneyState] = useState<{ job: JobOut; docId: string | null; replacing: boolean } | null>(null);

  const detail = useQuery(`application:${id}`, () => api("getApplication", { path: { application_id: id } }));
  const busy = (detail.data?.active_jobs.length ?? 0) > 0;
  const wasBusy = useRef(false);
  useEffect(() => {
    if (busy) { wasBusy.current = true; const t = setInterval(() => invalidate(`application:${id}`), 1500); return () => clearInterval(t); }
    if (wasBusy.current) {
      wasBusy.current = false;
      ["findings", "plan", "verifications", "runs"].forEach((k) => invalidate(`${k}:${id}`));
    }
  }, [busy, id]);

  if (detail.error) return <ErrorBox error={detail.error} retry={detail.refetch} />;
  if (!detail.data) return <Skeleton rows={5} />;
  const a = detail.data;
  const status = STATUS_META[busy ? "PROCESSING" : a.status];

  const tabs: [Tab, string][] = [["findings", `Findings${a.counts.active ? ` (${a.counts.active})` : ""}`], ["documents", "Documents"],
    ["plan", "What to fix"], ["activity", "Activity"]];

  return (
    <>
      <PageHeader
        kicker={<>{a.institution.name}, Permanent ID {a.institution.aicte_permanent_id}</>}
        title={`${a.category_label}, ${a.academic_year}`}
        lead={
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Pill tone={status.tone} title={status.hint}>{status.label}</Pill>
            <ProgressBar done={a.documents_uploaded} total={a.documents_required} />
            <span className="text-sm">{a.submitted_at ? `Submitted to AICTE ${fmtDate(a.submitted_at)}` : "Not yet submitted"}</span>
            <span className="text-sm">Rule pack v{a.rule_pack_version}</span>
          </div>
        }
        actions={<HeaderActions a={a} isInstitution={isInstitution} onJob={(job) => { setJourneyState({ job, docId: job.document_id, replacing: false }); setTab("documents"); }} />}
      />
      <div role="tablist" aria-label="Application sections" className="mb-6 flex gap-1 overflow-x-auto border-b border-rule">
        {tabs.map(([t, l]) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={cx("-mb-px whitespace-nowrap border-b-[3px] px-3 py-2.5 text-sm font-semibold transition-colors",
              tab === t ? "border-tape text-ink" : "border-transparent text-ink-soft hover:text-ink")}>{l}</button>
        ))}
      </div>
      {tab === "findings" && <FindingsTab a={a} canReview={canReview && !!a.submitted_at} isInstitution={isInstitution} selected={selected} onSelect={setSelected} />}
      {tab === "documents" && (
        <DocumentsTab
          a={a}
          canUpload={isInstitution}
          journey={journeyState ?? (a.active_jobs[0] ? { job: a.active_jobs[0], docId: a.active_jobs[0].document_id, replacing: false } : null)}
          onJob={(job, docId, replacing) => setJourneyState({ job, docId, replacing })}
          onOpenPlan={() => setTab("plan")}
        />
      )}
      {tab === "plan" && <PlanTab id={id} onOpen={(fid) => { setSelected(fid); setTab("findings"); }} />}
      {tab === "activity" && <ActivityTab a={a} id={id} showAudit={!isInstitution} />}
    </>
  );
}

function HeaderActions({ a, isInstitution, onJob }: { a: ApplicationDetail; isInstitution: boolean; onJob?: (job: JobOut) => void }) {
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [pending, setPending] = useState(false);
  const busy = a.active_jobs.length > 0;
  async function rerun() {
    setPending(true);
    try {
      const job = await api("validateApplication", { path: { application_id: a.id } });
      onJob?.(job);
      invalidate(`application:${a.id}`);
      toast("Full check queued");
    } catch (e) { toast(e instanceof ApiError ? e.message : "Could not start the check", "error"); }
    finally { setPending(false); }
  }
  async function downloadReport() {
    try {
      const save = (blob: Blob, ext: string) => {
        const aEl = document.createElement("a");
        aEl.href = URL.createObjectURL(blob);
        aEl.download = `PRAMAAN-report-${a.institution.aicte_permanent_id}.${ext}`;
        aEl.click();
        URL.revokeObjectURL(aEl.href);
        toast("Verification report downloaded");
      };
      if (hasEndpoint("applicationReport")) {
        const res = await fetch(`/api/v1/applications/${encodeURIComponent(a.id)}/report`, { credentials: "same-origin", headers: { "X-Requested-With": "pramaan" } });
        if (res.ok) { save(await res.blob(), "pdf"); return; }
      }
      const lines = [
        "PRAMAAN — PRELIMINARY VERIFICATION SUMMARY (SYNTHETIC / ADVISORY ONLY)",
        `Institution: ${a.institution.name} (${a.institution.aicte_permanent_id}, ${a.institution.state})`,
        `Category: ${a.category_label} · Academic Year: ${a.academic_year} · Status: ${STATUS_META[a.status].label} (Rule pack v${a.rule_pack_version})`,
        `Documents: ${a.documents_uploaded}/${a.documents_required} · Open Findings: ${a.counts.active} (${a.counts.deficiencies} deficiencies)`,
        ...a.checklist.map((c) => `- ${c.label}: ${c.document ? `${c.document.original_name} (${c.document.verification_status ?? "Checked"})` : "Not uploaded"}`),
      ];
      save(new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" }), "txt");
    } catch {
      toast("Could not download verification report. Try again.", "error");
    }
  }
  async function submit() {
    setPending(true);
    try {
      await api("submitApplication", { path: { application_id: a.id } });
      invalidate(`application:${a.id}`);
      invalidate("applications");
      setConfirm(false);
      toast("Submitted to AICTE");
    } catch (e) { toast(e instanceof ApiError ? e.message : "Could not submit", "error"); }
    finally { setPending(false); }
  }
  return (
    <>
      <button className="btn btn-quiet" onClick={downloadReport}>Download report</button>
      <button className="btn btn-quiet" onClick={rerun} disabled={pending || busy || (!isInstitution && !a.submitted_at)}>
        {busy ? <Spinner label="Checking" /> : "Run full check"}
      </button>
      {isInstitution && !a.submitted_at && (
        <button className="btn btn-primary" onClick={() => setConfirm(true)} disabled={busy || !a.latest_run}>Submit to AICTE</button>
      )}
      <Dialog open={confirm} onClose={() => setConfirm(false)} title="Submit this application?">
        <div className="grid gap-4">
          <p>AICTE officers will see the application, its documents and every finding with its evidence.
            {a.counts.active > 0 ? ` ${plural(a.counts.active, "finding is", "findings are")} still open; officers will review them.` : " There are no open findings."}</p>
          <p className="text-sm text-ink-soft">You can still upload corrected documents after submitting. PRAMAAN does not approve or reject; officials decide.</p>
          <div className="flex justify-end gap-2">
            <button className="btn btn-quiet" onClick={() => setConfirm(false)}>Keep editing</button>
            <button className="btn btn-primary" onClick={submit} disabled={pending}>{pending ? "Submitting…" : "Submit to AICTE"}</button>
          </div>
        </div>
      </Dialog>
    </>
  );
}

// ------------------------------------------------------------------------------------- findings
function FindingsTab({ a, canReview, isInstitution, selected, onSelect }:
  { a: ApplicationDetail; canReview: boolean; isInstitution: boolean; selected: string | null; onSelect: (id: string) => void }) {
  const [showResolved, setShowResolved] = useState(false);
  const findings = useQuery(`findings:${a.id}:${showResolved}`, () =>
    api("listFindings", { path: { application_id: a.id }, query: { include_resolved: showResolved ? "true" : undefined } }));
  const verifs = useQuery(`verifications:${a.id}`, () => api("listVerifications", { path: { application_id: a.id } }));
  const list = findings.data ?? [];
  const current = list.find((f) => f.id === selected) ?? list.find((f) => f.state !== "RESOLVED") ?? list[0];
  const panel = useRef<HTMLDivElement | null>(null);
  // Warm the page images behind the first findings sequentially after the initial page renders, so selecting one is instant.
  useEffect(() => {
    const id = setTimeout(() => list.slice(0, 12).forEach(preloadEvidence), 350);
    return () => clearTimeout(id);
  }, [list]);

  if (findings.error) return <ErrorBox error={findings.error} retry={findings.refetch} />;
  if (!findings.data) return <Skeleton />;
  const groups: [string, FindingOut[]][] = [
    ["Deficiencies", list.filter((f) => f.severity === "DEFICIENCY" && f.state !== "RESOLVED")],
    ["Needs official review", list.filter((f) => f.severity !== "DEFICIENCY" && f.state !== "RESOLVED")],
    ["Resolved by re-check", list.filter((f) => f.state === "RESOLVED")],
  ];
  const toggle = (
    <label className="flex items-center gap-2 text-sm text-ink-soft">
      <input type="checkbox" checked={showResolved} onChange={(e: ChangeEvent<HTMLInputElement>) => setShowResolved(e.target.checked)} /> Show resolved findings
    </label>
  );
  if (list.length === 0)
    return (
      <div className="grid gap-4">
        {toggle}
        <Empty title={a.latest_run ? "No open findings" : "Nothing checked yet"}>
          {a.latest_run
            ? "Every rule that could be evaluated passed and no indicator was raised. This is not an approval; officials still scrutinise the application."
            : "Upload documents in the Documents tab. Checks run automatically after each upload."}
        </Empty>
      </div>
    );
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:items-start">
      <div className="grid gap-5">
        {toggle}
        {groups.map(([title, items]) => items.length > 0 && (
          <section key={title}>
            <h2 className="mb-2 font-sans text-sm font-semibold text-ink-soft">{title} ({items.length})</h2>
            <ul className="grid gap-2">
              {items.map((f) => (
                <li key={f.id}>
                  <button onClick={() => { onSelect(f.id); if (window.innerWidth < 1024) panel.current?.scrollIntoView({ behavior: "smooth" }); }}
                    onMouseEnter={() => preloadEvidence(f)} onFocus={() => preloadEvidence(f)}
                    aria-pressed={current?.id === f.id}
                    className={cx("grid w-full gap-1 rounded-sm px-3 py-2.5 text-left transition-[background-color,box-shadow]",
                      current?.id === f.id ? "bg-sheet shadow-[inset_3px_0_0_var(--color-tape),0_0_0_1px_rgb(29_43_79/0.12)]" : "hover:bg-sheet/70")}>
                    <span className="font-semibold leading-snug">{f.title}</span>
                    <span className="flex flex-wrap items-center gap-2 text-xs text-ink-soft">
                      <Pill tone={SEVERITY_META[f.severity].tone}>{SEVERITY_META[f.severity].label}</Pill>
                      {f.state !== "OPEN" && <span>{FINDING_STATE_LABEL[f.state]}</span>}
                      {f.source_kind !== "RULE" && <span>{f.source_kind === "INTEGRITY" ? "Integrity indicator" : f.source_kind === "DUPLICATE" ? "Possible reuse" : "Verification"}</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <div ref={panel} className="lg:sticky lg:top-6">
        {current && <FindingPanel key={current.id} f={current} verifications={verifs.data ?? []} canReview={canReview} isInstitution={isInstitution} />}
      </div>
    </div>
  );
}

const preloaded = new Set<string>();
const preloadQueue: string[] = [];
let preloading = false;

function pumpPreload() {
  if (preloading || preloadQueue.length === 0) return;
  const url = preloadQueue.shift()!;
  preloading = true;
  const img = new Image();
  img.decoding = "async";
  const done = () => { preloading = false; pumpPreload(); };
  img.onload = done;
  img.onerror = done;
  img.src = url;
}

function preloadEvidence(f: FindingOut) {
  const e = f.evidence.find((x) => x.document_id && !x.other_application);
  if (!e?.document_id) return;
  const url = pageImageUrl(e.document_id, e.page ?? 1);
  if (preloaded.has(url)) return;
  preloaded.add(url);
  preloadQueue.push(url);
  pumpPreload();
}

function boxesFor(f: FindingOut, docId: string, active: number, forceTone?: Box["tone"]): Box[] {
  return f.evidence.flatMap((e, i) => (e.document_id === docId && e.bbox && e.page_size
    ? [{ bbox: e.bbox, pageSize: e.page_size, label: `${label(e.field)}: ${e.value ?? ""}`,
        tone: forceTone ?? ((f.severity === "DEFICIENCY" ? "tape" : "turmeric") as Box["tone"]), active: i === active }] : []));
}

function ClarificationReplyForm({ f }: { f: FindingOut }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true); setErr(null);
    try {
      await callEndpoint("respondFinding", { path: { finding_id: f.id }, body: { message: text.trim() } });
      setText("");
      invalidate(`findings:${f.application_id}`);
      toast("Clarification reply recorded");
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Could not send reply.");
    } finally { setPending(false); }
  }
  return (
    <form onSubmit={submit} className="grid gap-2.5 rounded-sm bg-paper p-3 text-sm">
      <label className="field">
        <span>Your reply to the scrutiny officer (10–2000 characters)</span>
        <textarea className="input" minLength={10} maxLength={2000} required value={text}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setText(e.target.value)} />
      </label>
      {err && <p role="alert" className="text-xs font-semibold text-tape">{err}</p>}
      <button className="btn btn-primary min-h-8 justify-self-start px-3 text-xs" disabled={pending || text.trim().length < 10}>
        {pending ? "Sending…" : "Send clarification reply"}
      </button>
    </form>
  );
}

function FindingPanel({ f, verifications, canReview, isInstitution }:
  { f: FindingOut; verifications: VerificationOut[]; canReview: boolean; isInstitution: boolean }) {
  const { features } = useFeatures();
  const firstViewable = Math.max(0, f.evidence.findIndex((e) => e.document_id));
  const [active, setActive] = useState(firstViewable);
  const [sideBySide, setSideBySide] = useState(false);
  const ev = f.evidence[active];
  const docId = ev?.document_id ?? null;
  const [page, setPage] = useState(ev?.page ?? 1);
  useEffect(() => { setPage(ev?.page ?? 1); }, [active, ev?.page]);

  const viewableDocs = useMemo(() => {
    const seen = new Set<string>();
    return f.evidence.flatMap((e, idx) => {
      if (!e.document_id || e.other_application || seen.has(e.document_id)) return [];
      seen.add(e.document_id);
      return [{ e, idx, docId: e.document_id }];
    });
  }, [f.evidence]);

  const aiChecked = (f as unknown as Record<string, unknown>).explanation_source === "ai_checked";
  const resubmissionNeeded = f.action_owner === "INSTITUTION" && !!f.fix_doc_type;
  const decisionNode = canReview && f.state !== "RESOLVED"
    ? <ReviewForm f={f} />
    : isInstitution && f.state === "CLARIFICATION_REQUESTED" && features.clarifications
    ? <ClarificationReplyForm f={f} />
    : undefined;

  return (
    <article className="sheet grid gap-5 p-5 sm:p-6" aria-label={f.title}>
      <header className="grid gap-2 border-b border-rule pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={SEVERITY_META[f.severity].tone}>{SEVERITY_META[f.severity].label}</Pill>
          <span className="text-sm text-ink-soft">{FINDING_STATE_LABEL[f.state]}. Advisory, raised {fmtDate(f.created_at, true)}</span>
          {aiChecked && <Pill tone="dusk">Explained by AI and checked against the evidence</Pill>}
        </div>
        <h2 className="text-xl">{f.title}</h2>
        <p className="font-serif text-ink">{f.explanation}</p>
        <div className="grid gap-1 text-sm sm:grid-cols-2">
          <p><span className="font-semibold">What would clear this: </span>{f.remedy}</p>
          <p>
            <span className="font-semibold">Resubmission needed: </span>
            {resubmissionNeeded ? `Yes — replace ${label(f.fix_doc_type)}` : "No — awaiting officer review or source check"}
          </p>
        </div>
        {viewableDocs.length >= 2 && (
          <div className="pt-1">
            <button type="button" className="btn btn-quiet min-h-8 px-3 text-xs" onClick={() => setSideBySide((s) => !s)}>
              {sideBySide ? "Single page view" : "Compare both documents side by side"}
            </button>
          </div>
        )}
      </header>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <ProofChain finding={f} verifications={verifications} activeEvidence={active} onEvidence={setActive} decision={decisionNode} />
        <div>
          {sideBySide && viewableDocs.length >= 2 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {viewableDocs.slice(0, 2).map(({ e, idx, docId: dId }) => (
                <EvidenceViewer key={dId} documentId={dId} page={e.page ?? 1}
                  boxes={boxesFor(f, dId, idx, "tape")} maxHeight="58vh"
                  caption={`${label(e.doc_type)}, page ${e.page ?? 1} (${label(e.field)}: ${e.value ?? ""})`} />
              ))}
            </div>
          ) : docId ? (
            <EvidenceViewer documentId={docId} page={page} boxes={boxesFor(f, docId, active)} maxHeight="78vh"
              caption={ev?.other_application ? "Matched evidence from another application" : `${label(ev?.doc_type)}, page ${page}`} />
          ) : (
            <Empty title="No page to show">
              {ev?.other_application ? "The matching file belongs to another institution and is not shown to you." : "This finding is about a document that is missing, so there is no page to highlight."}
            </Empty>
          )}
        </div>
      </div>
    </article>
  );
}

const DECISIONS: [ReviewDecision, string, string][] = [
  ["CONFIRM", "Confirm", "The finding stands and will inform scrutiny."],
  ["REQUEST_CLARIFICATION", "Ask the institution", "The institution is asked to explain or correct."],
  ["ESCALATE", "Escalate", "Refer to a senior officer or for inspection."],
  ["DISMISS", "Dismiss", "The finding does not apply; your reason is recorded."],
];

function ReviewForm({ f }: { f: FindingOut }) {
  const toast = useToast();
  const [decision, setDecision] = useState<ReviewDecision>("CONFIRM");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await api("reviewFinding", { path: { finding_id: f.id }, body: { decision, reason: reason.trim() } });
      invalidate(`findings:${f.application_id}`);
      invalidate(`application:${f.application_id}`);
      invalidate(`plan:${f.application_id}`);
      toast("Decision recorded in the audit trail");
      setReason("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record the decision.");
    } finally {
      setPending(false);
    }
  }
  return (
    <form onSubmit={submit} className="grid gap-3 rounded-sm bg-paper p-4">
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-semibold">Your decision</legend>
        {DECISIONS.map(([v, l, hint]) => (
          <label key={v} className={cx("flex cursor-pointer gap-3 rounded-sm px-3 py-2", decision === v ? "bg-sheet shadow-[inset_0_0_0_2px_var(--color-ink)]" : "hover:bg-sheet")}>
            <input type="radio" name={`d-${f.id}`} value={v} checked={decision === v} onChange={() => setDecision(v)} className="mt-1" />
            <span><span className="block font-semibold">{l}</span><span className="block text-xs text-ink-soft">{hint}</span></span>
          </label>
        ))}
      </fieldset>
      <label className="field">
        <span>Reason (recorded with your name)</span>
        <textarea className="input" value={reason} onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setReason(e.target.value)} minLength={10} maxLength={2000} required />
      </label>
      {error && <p role="alert" className="text-sm font-semibold text-tape">{error}</p>}
      <button className="btn btn-primary" disabled={pending || reason.trim().length < 10}>{pending ? "Recording…" : "Record decision"}</button>
      {reason.trim().length > 0 && reason.trim().length < 10 && <p className="text-xs text-ink-soft">Write at least 10 characters so the reason is useful to the next reader.</p>}
    </form>
  );
}

// ------------------------------------------------------------------------------------- documents
const COMMON_FLAGS: Record<string, string[]> = {
  eoa_letter: ["Permanent ID must match AICTE records", "Issued for the previous academic cycle (2025-26)"],
  affidavit: ["Academic year must match 2026-27", "Total intake and faculty count must match the faculty summary"],
  fire_noc: ["Valid up to date must be on or after the start of the academic year (01-07-2026)", "Signed QR must verify against the issuer key"],
  building_stability: ["Valid up to date must cover the academic year", "Certificate number must match the issuer registry"],
  faculty_summary: ["Student–faculty ratio must not exceed 1:20", "Total intake must agree with the affidavit and AICTE records"],
  infra_photo: ["Photograph must belong to this institution (checked against cross-application reuse)"],
};

function DocumentsTab({
  a,
  canUpload,
  journey,
  onJob,
  onOpenPlan,
}: {
  a: ApplicationDetail;
  canUpload: boolean;
  journey: { job: JobOut; docId: string | null; replacing: boolean } | null;
  onJob: (job: JobOut, docId: string | null, replacing: boolean) => void;
  onOpenPlan: () => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [guideOpen, setGuideOpen] = useState<Record<string, boolean>>({});
  const toast = useToast();

  async function retryValidation() {
    try {
      const job = await api("validateApplication", { path: { application_id: a.id } });
      onJob(job, job.document_id, false);
      invalidate(`application:${a.id}`);
    } catch (e) { toast(e instanceof ApiError ? e.message : "Could not retry", "error"); }
  }

  return (
    <>
      {journey?.replacing && (
        <p role="status" className="mb-3 rounded-sm border-l-4 border-ink bg-sheet px-3.5 py-2 text-xs font-medium text-ink">
          Only the rules that read this document will run again.
        </p>
      )}
      {journey && (
        <ProcessingJourney
          job={journey.job}
          documentId={journey.docId}
          app={a}
          onOpenPlan={onOpenPlan}
          onRetry={retryValidation}
        />
      )}
      <ul className="grid gap-3">
        {a.checklist.map((item: ChecklistItemOut) => {
          const d = item.document;
          const v = d?.verification_status ? VERIFICATION_META[d.verification_status] : null;
          const earlier = a.documents.filter((x) => x.doc_type === item.doc_type && x.superseded);
          const showGuide = !!guideOpen[item.doc_type];
          return (
            <li key={item.doc_type} className="sheet grid gap-3 p-4 sm:p-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] md:items-center">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-[1.4rem] leading-tight tracking-[-0.025em]">{item.label}</span>
                  <span className="text-xs text-ink-soft">{item.required ? "Required" : "Optional"}</span>
                  <button type="button" className="link text-xs text-ink-soft"
                    onClick={() => setGuideOpen((g) => ({ ...g, [item.doc_type]: !g[item.doc_type] }))}>
                    {showGuide ? "Hide guidance" : "Before you upload"}
                  </button>
                </div>
                <p className="text-sm text-ink-soft">{item.note}</p>
                {showGuide && (
                  <div className="mt-2 rounded-sm bg-paper p-2.5 text-xs">
                    <div className="font-semibold">Common reasons this document is flagged:</div>
                    <ul className="mt-1 grid gap-0.5 text-ink-soft">
                      {(COMMON_FLAGS[item.doc_type] ?? [item.note]).map((f) => <li key={f}>• {f}</li>)}
                    </ul>
                  </div>
                )}
                {d && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                    <span className="max-w-full truncate font-semibold">{d.original_name}</span>
                    <span className="text-ink-soft">{fmtBytes(d.size_bytes)}, {plural(d.pages, "page")}{d.has_text_layer ? "" : d.mime === "application/pdf" ? ", scanned (OCR)" : ""}</span>
                    {d.processing_state !== "DONE" ? <Pill tone={d.processing_state === "FAILED" ? "tape" : "dusk"}>{d.processing_state === "FAILED" ? "Could not be read" : "Checking"}</Pill>
                      : v ? <Pill tone={v.tone}>{v.label}</Pill> : <span className="text-xs text-ink-soft">{d.mime.startsWith("image/") ? "Fingerprinted for reuse checks" : "Declaration, cross-checked by rules"}</span>}
                    {d.detected_type && d.detected_type !== d.doc_type && <Pill tone="turmeric">Looks like {label(d.detected_type)}</Pill>}
                  </div>
                )}
                {earlier.length > 0 && (
                  <div className="mt-1.5 text-xs text-ink-faint">
                    Superseded versions ({earlier.length}): {earlier.map((e) => `${e.original_name} (${fmtDate(e.uploaded_at, true)})`).join(", ")}
                  </div>
                )}
              </div>
              <div className="grid gap-2">
                {d && d.processing_state === "DONE" && (
                  <button className="btn btn-quiet justify-self-start" onClick={() => setOpen(d.id)}>View what was read</button>
                )}
                {canUpload && <UploadSlot applicationId={a.id} docType={item.doc_type} label={item.label} replacing={!!d}
                  onJob={(job, docId, rep) => onJob(job, docId, rep)}
                  accept={item.doc_type === "infra_photo" ? "image/png,image/jpeg" : "application/pdf"} />}
                {!d && !canUpload && <span className="text-sm text-ink-soft">Not uploaded.</span>}
              </div>
            </li>
          );
        })}
      </ul>
      {open && <DocumentDialog documentId={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function DocumentDialog({ documentId, onClose }: { documentId: string; onClose: () => void }) {
  const ev = useQuery(`evidence:${documentId}`, () => api("documentEvidence", { path: { document_id: documentId } }));
  const [activeClaim, setActiveClaim] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const d = ev.data;
  const boxes = useMemo<Box[]>(() => (d?.claims ?? []).filter((c) => c.page === page).map((c) => ({
    bbox: c.bbox, pageSize: c.page_size, label: `${label(c.field)}: ${c.value_raw}`, tone: "ink", active: c.id === activeClaim,
  })), [d, page, activeClaim]);
  return (
    <Dialog open onClose={onClose} title={d ? `${d.document.doc_type_label}: ${d.document.original_name}` : "Document"} wide>
      {ev.error ? <ErrorBox error={ev.error} /> : !d ? <Skeleton /> : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <EvidenceViewer documentId={d.document.id} page={page} pages={d.document.pages} onPage={setPage} boxes={boxes} />
          <div className="grid content-start gap-6">
            <section>
              <h3 className="mb-2 text-base">Values read</h3>
              {d.claims.length === 0 ? <p className="text-sm text-ink-soft">{d.document.mime.startsWith("image/") ? "Photographs are fingerprinted for reuse checks; no text is extracted." : "No template fields were found on this document."}</p> : (
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-rule text-left text-ink-soft"><th className="py-1.5 pr-2 font-semibold">Field</th><th className="pr-2 font-semibold">Value</th><th className="font-semibold">How</th></tr></thead>
                  <tbody>
                    {d.claims.map((c) => (
                      <tr key={c.id} className={cx("cursor-pointer border-b border-rule/60", activeClaim === c.id && "bg-tape-wash")}
                        onClick={() => { setActiveClaim(c.id); setPage(c.page); }}>
                        <td className="py-1.5 pr-2">{label(c.field)}</td>
                        <td className="pr-2 font-semibold">{c.value_raw}</td>
                        <td className="text-ink-soft">{c.extractor.startsWith("ocr") ? "OCR" : "Text layer"} {Math.round(c.confidence * 100)}%, p.{c.page}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
            <section>
              <h3 className="mb-2 text-base">Source verification</h3>
              {d.verifications.length === 0 ? <p className="text-sm text-ink-soft">No issuing source applies to this document type.</p> : (
                <ul className="grid gap-2 text-sm">
                  {d.verifications.map((v) => (
                    <li key={v.id} className="rounded-sm bg-paper px-3 py-2">
                      <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">Tier {v.tier}: {CHANNEL_LABEL[v.channel] ?? v.channel}</span>
                        <Pill tone={VERIFICATION_META[v.status].tone}>{VERIFICATION_META[v.status].label}</Pill>{v.simulated && <SimulatedTag />}</div>
                      <p className="mt-1 text-ink-soft">{String((v.detail as Record<string, unknown>).reason ?? "")}</p>
                      {v.response_hash && <p className="mt-1 break-all text-xs text-ink-faint">Response fingerprint {v.response_hash.slice(0, 16)}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section>
              <h3 className="mb-2 text-base">Integrity checks</h3>
              <IntegrityList extraction={d.extraction} signals={d.integrity} />
            </section>
          </div>
        </div>
      )}
    </Dialog>
  );
}

function IntegrityList({ extraction, signals }: { extraction: Record<string, any> | null; signals: Record<string, any>[] }) {
  const checks: Record<string, any>[] = extraction?.visible_text_checks ?? [];
  const facts = extraction?.structure ?? {};
  if (!extraction) return <p className="text-sm text-ink-soft">Not applicable to photographs.</p>;
  return (
    <ul className="grid gap-1.5 text-sm">
      <li>File revisions after creation: <strong>{facts.incremental_saves ?? 0}</strong>{facts.incremental_saves ? " (indicator raised)" : ""}</li>
      {checks.map((c, i) => (
        <li key={i}>
          Visible vs embedded {label(c.field)}: <strong className={c.outcome === "MISMATCH" ? "text-tape" : ""}>
            {c.outcome === "MATCH" ? "match" : c.outcome === "MISMATCH" ? `differs (${c.text_layer} vs ${c.rendered_ocr})` : "not decided — OCR unsure"}</strong>
        </li>
      ))}
      {signals.filter((s) => s.kind === "DECLARED_TYPE_MISMATCH").map((s, i) => <li key={`t${i}`} className="font-semibold text-turmeric">{String(s.title)}</li>)}
    </ul>
  );
}

// ------------------------------------------------------------------------------------- plan
function PlanTab({ id, onOpen }: { id: string; onOpen: (findingId: string) => void }) {
  const plan = useQuery(`plan:${id}`, () => api("repairPlan", { path: { application_id: id } }));
  if (plan.error) return <ErrorBox error={plan.error} retry={plan.refetch} />;
  if (!plan.data) return <Skeleton />;
  const p = plan.data;
  if (p.open_findings === 0) return <Empty title="Nothing to fix">There are no open findings. Officials still scrutinise the application before any decision.</Empty>;
  const block = (title: string, lead: string, actions: RepairAction[]) => actions.length > 0 && (
    <section className="grid gap-3">
      <div><h2 className="text-xl">{title}</h2><p className="text-sm text-ink-soft">{lead}</p></div>
      <ol className="grid gap-3">
        {actions.map((x) => (
          <li key={x.id} className="sheet grid grid-cols-[2.25rem_1fr] gap-3 p-4 sm:p-5">
            <span className={cx("font-display text-[2.5rem] leading-none tracking-[-0.04em]", x.severity === "DEFICIENCY" ? "text-tape" : "text-turmeric")}>{x.step}</span>
            <div className="grid gap-2">
              <div className="font-semibold">{x.title}</div>
              {(x.details ?? []).length > 0 && <ul className="grid gap-1 text-sm text-ink-soft">{(x.details ?? []).map((d) => <li key={d}>{d}</li>)}</ul>}
              <div className="flex flex-wrap gap-2 text-sm">
                <span className="text-ink-soft">Clears {plural(x.resolves.length, "finding")}:</span>
                {x.resolves.map((fid, i) => <button key={fid} className="link" onClick={() => onOpen(fid)}>{x.finding_titles[i]}</button>)}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
  return (
    <div className="grid max-w-4xl gap-10">
      {block("For the institution", "Ordered so that deficiencies come first and one corrected document clears as many findings as possible.", p.institution_actions)}
      {block("For AICTE officers", "Checks that need a person: confirming with an issuer, inspecting an indicator, or reviewing possible reuse.", p.officer_actions)}
      <p className="text-sm text-ink-soft">{p.note}</p>
    </div>
  );
}

// ------------------------------------------------------------------------------------- activity
function ActivityTab({ a, id, showAudit }: { a: ApplicationDetail; id: string; showAudit: boolean }) {
  const { features } = useFeatures();
  const runs = useQuery(`runs:${id}`, () => api("listRuns", { path: { application_id: id } }));
  const audit = useQuery(showAudit ? `audit:${id}` : null, () => api("listAudit", { query: { application_id: id, limit: "200" } }));
  const apiTimeline = useQuery(
    features.timeline ? `timeline:${id}` : null,
    () => callEndpoint<{ ts: string; title: string; detail?: string; tone?: string }[]>("applicationTimeline", { path: { application_id: id } }),
  );

  const timeline = useMemo(() => {
    if (apiTimeline.data) return apiTimeline.data;
    const items: { ts: string; title: string; detail: string; isDeficiency?: boolean }[] = [
      { ts: a.created_at, title: "Application created", detail: `${a.category_label} (${a.academic_year})` },
    ];
    for (const d of a.documents) {
      items.push({
        ts: d.uploaded_at,
        title: `${d.doc_type_label} uploaded${d.superseded ? " (superseded)" : ""}`,
        detail: `${d.original_name} (${fmtBytes(d.size_bytes)})`,
      });
    }
    for (const r of runs.data ?? []) {
      const s = (r.summary ?? {}) as Record<string, number>;
      items.push({
        ts: r.started_at,
        title: describeTrigger(r.trigger),
        detail: `Rule pack v${r.rule_pack_version}; ${plural(r.affected_rules.length, "rule")} evaluated; ${s.created ?? 0} new, ${s.resolved ?? 0} resolved.`,
        isDeficiency: (s.created ?? 0) > 0,
      });
    }
    if (a.submitted_at) {
      items.push({ ts: a.submitted_at, title: "Submitted to AICTE", detail: "Application entered the scrutiny queue." });
    }
    return items.sort((x, y) => y.ts.localeCompare(x.ts));
  }, [a, runs.data, apiTimeline.data]);

  return (
    <div className="grid gap-10 lg:grid-cols-2">
      <section className="grid content-start gap-8">
        <div>
          <h2 className="mb-3 text-xl">Application timeline</h2>
          <ol className="grid gap-2 text-sm">
            {timeline.map((item, idx) => (
              <li key={idx} className="sheet grid grid-cols-[0.75rem_1fr] items-start gap-3 p-3.5">
                <span aria-hidden className={cx("mt-1.5 h-2.5 w-2.5 rounded-full", (item as { isDeficiency?: boolean }).isDeficiency ? "bg-tape" : "bg-ink")} />
                <div>
                  <div className="flex flex-wrap justify-between gap-2">
                    <span className="font-semibold">{item.title}</span>
                    <span className="text-xs text-ink-soft">{fmtDate(item.ts, true)}</span>
                  </div>
                  {item.detail && <div className="mt-0.5 text-xs text-ink-soft">{item.detail}</div>}
                </div>
              </li>
            ))}
          </ol>
        </div>

        <div>
          <h2 className="mb-3 text-xl">Validation runs</h2>
          {runs.error ? <ErrorBox error={runs.error} /> : !runs.data ? <Skeleton /> : (
            <ol className="grid gap-2">
              {runs.data.map((r) => {
                const s = (r.summary ?? {}) as Record<string, any>;
                return (
                  <li key={r.id} className="sheet p-4 text-sm">
                    <div className="flex flex-wrap justify-between gap-2"><span className="font-semibold">{describeTrigger(r.trigger)}</span><span className="text-ink-soft">{fmtDate(r.started_at, true)}</span></div>
                    <div className="mt-1 text-ink-soft">
                      Rule pack v{r.rule_pack_version}; {plural(r.affected_rules.length, "rule")} evaluated; {s.created ?? 0} new, {s.resolved ?? 0} resolved.
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </section>
      {showAudit && (
        <section>
          <h2 className="mb-3 text-xl">Audit trail for this application</h2>
          {audit.error ? <ErrorBox error={audit.error} /> : !audit.data ? <Skeleton /> : <AuditList events={audit.data} />}
        </section>
      )}
    </div>
  );
}

export function describeTrigger(t: string) {
  if (t === "first-upload") return "First check after upload";
  if (t === "manual") return "Full check requested";
  if (t.startsWith("document:")) return `Re-check after new ${label(t.slice(9))}`;
  if (t.startsWith("duplicate-match")) return "Re-check after a match in another application";
  return t;
}

export function AuditList({ events }: { events: { seq: number; ts: string; action: string; actor_name: string | null; actor_role: string | null; object_type: string; hash: string; payload: Record<string, unknown> }[] }) {
  return (
    <ol className="grid gap-1.5 text-sm">
      {events.map((e) => (
        <li key={e.seq} className="grid grid-cols-[3.5rem_1fr] gap-3 rounded-sm px-2 py-1.5 hover:bg-sheet">
          <span className="text-ink-faint">#{e.seq}</span>
          <div className="min-w-0">
            <div><span className="font-semibold">{e.action.replace(/[._]/g, " ")}</span> <span className="text-ink-soft">by {e.actor_name ?? e.actor_role ?? "system"}</span></div>
            <div className="truncate text-xs text-ink-faint">{fmtDate(e.ts, true)}, hash {e.hash.slice(0, 16)}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

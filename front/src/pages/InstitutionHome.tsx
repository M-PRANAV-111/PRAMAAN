import { useState, type ChangeEvent, type FormEvent } from "react";
import { api, ApiError, type ApplicationSummary, type Category, type JobOut } from "../api/client";
import { PageHeader } from "../components/AppShell";
import { ProcessingJourney } from "../components/processing/ProcessingJourney";
import { UploadSlot } from "../components/UploadSlot";
import { Empty, ErrorBox, Pill, Skeleton, cx } from "../components/ui";
import { SEVERITY_META, STATUS_META, VERIFICATION_META, fmtBytes, fmtDate, label, plural } from "../lib/format";
import { useLang } from "../lib/i18n";
import { invalidate, useQuery } from "../lib/query";
import { Link, navigate, useQueryParam } from "../lib/router";
import { ROLE_LABEL, useSession } from "../lib/session";
import { OnboardingTips } from "./Help";

export function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-xs text-ink-soft">
      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-rule" role="progressbar" aria-valuenow={done} aria-valuemax={total} aria-label="Required documents uploaded">
        <span className="block h-full rounded-full bg-ink transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </span>
      {done} of {total} required documents
    </div>
  );
}

const CHECKLIST_PREVIEW: Record<Category, string[]> = {
  EOA_EXISTING: ["Previous Extension of Approval letter", "Affidavit (EoA format)", "Fire safety NOC", "Structural stability certificate", "Faculty & student strength summary", "Infrastructure photograph (optional)"],
  EOA_INTAKE_INCREASE: ["Previous Extension of Approval letter", "Affidavit (EoA format)", "Fire safety NOC", "Structural stability certificate", "Faculty & student strength summary", "Infrastructure photograph (required for intake increase)"],
};

type SectionId = "overview" | "new" | "upload" | "documents" | "applications" | "results" | "corrections" | "timeline" | "notifications" | "profile";

const SECTIONS: [SectionId, string][] = [
  ["overview", "Overview"],
  ["new", "New Application"],
  ["upload", "Upload / Scan"],
  ["documents", "My Documents"],
  ["applications", "My Applications"],
  ["results", "Verification Results"],
  ["corrections", "Corrections & Resubmissions"],
  ["timeline", "Application Timeline"],
  ["notifications", "Notifications"],
  ["profile", "Profile & Settings"],
];

function StartApplication({ onDone }: { onDone: () => void }) {
  const meta = useQuery("meta", () => api("meta"));
  const [category, setCategory] = useState<Category>("EOA_EXISTING");
  const [year, setYear] = useState("2026-27");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      const a = await api("createApplication", { body: { category, academic_year: year } });
      invalidate("applications");
      onDone();
      navigate(`/applications/${a.id}`);
    } catch (err) {
      const dup = err instanceof ApiError && err.code === "duplicate_application" ? (err.details as { application_id?: string })?.application_id : null;
      if (dup) navigate(`/applications/${dup}`);
      else setError(err instanceof ApiError ? err.message : "Could not create the application.");
    } finally {
      setPending(false);
    }
  }
  return (
    <form onSubmit={submit} className="sheet grid gap-4 p-5 sm:grid-cols-[1fr_10rem_auto] sm:items-end">
      <label className="field">
        <span>Application category</span>
        <select className="input" value={category} onChange={(e: ChangeEvent<HTMLSelectElement>) => setCategory(e.target.value as Category)}>
          {Object.entries(meta.data?.categories ?? { EOA_EXISTING: "Extension of Approval — no change in intake" }).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <label className="field">
        <span>Academic year</span>
        <input className="input" value={year} pattern="20\d{2}-\d{2}" onChange={(e: ChangeEvent<HTMLInputElement>) => setYear(e.target.value)} />
      </label>
      <button className="btn btn-primary" disabled={pending}>{pending ? "Creating…" : "Create application"}</button>
      <div className="text-xs text-ink-soft sm:col-span-3">
        <span className="font-semibold text-ink">Checklist preview ({CHECKLIST_PREVIEW[category].length} items): </span>
        {CHECKLIST_PREVIEW[category].join(" · ")}
      </div>
      {error && <p role="alert" className="text-sm font-semibold text-tape sm:col-span-3">{error}</p>}
    </form>
  );
}

export function InstitutionHome() {
  const { user, signOut } = useSession();
  const [lang, setLang] = useLang();
  const apps = useQuery("applications", () => api("listApplications"));
  const secParam = (useQueryParam("section") as SectionId | null) ?? "overview";
  const [section, setSectionState] = useState<SectionId>(secParam);
  const [starting, setStarting] = useState(false);
  const [journeyState, setJourneyState] = useState<{ job: JobOut; docId: string | null } | null>(null);

  const setSection = (s: SectionId) => {
    setSectionState(s);
    navigate(s === "overview" ? "/institution" : `/institution?section=${s}`, { replace: true });
  };

  const list = apps.data ?? [];
  const primaryApp = list[0] ?? null;
  const needDetail = section !== "overview" && section !== "new" && section !== "applications" && section !== "profile";
  const detail = useQuery(needDetail && primaryApp ? `application:${primaryApp.id}` : null,
    () => api("getApplication", { path: { application_id: primaryApp!.id } }));
  const findings = useQuery((section === "results" || section === "notifications") && primaryApp ? `findings:${primaryApp.id}` : null,
    () => api("listFindings", { path: { application_id: primaryApp!.id }, query: { include_resolved: "true" } }));
  const plan = useQuery(section === "corrections" && primaryApp ? `plan:${primaryApp.id}` : null,
    () => api("repairPlan", { path: { application_id: primaryApp!.id } }));

  const totalOpen = list.reduce((s, a) => s + a.counts.active, 0);
  const pendingDocs = list.reduce((s, a) => s + Math.max(0, a.documents_required - a.documents_uploaded), 0);
  const openDefs = list.reduce((s, a) => s + a.counts.deficiencies, 0);
  const pendingActions = pendingDocs + openDefs;
  const lastUpdated = list.map((a) => a.updated_at).sort().at(-1);

  return (
    <>
      <PageHeader title="Your applications" kicker={user?.institution_name}
        lead="Upload or camera-scan documents for a pre-flight check before you submit. Each finding says what to fix and why."
        actions={!starting && <button className="btn btn-primary" onClick={() => setStarting(true)}>Start an application</button>} />
      {user && <OnboardingTips role={user.role} />}

      <nav aria-label="Applicant portal sections" className="mb-6 flex gap-1 overflow-x-auto border-b border-rule pb-px text-xs font-semibold">
        {SECTIONS.map(([id, title]) => (
          <button key={id} type="button" aria-pressed={section === id} onClick={() => setSection(id)}
            className={cx("shrink-0 border-b-2 px-2.5 py-2 transition-colors",
              section === id ? "border-tape text-ink" : "border-transparent text-ink-soft hover:text-ink")}>
            {title}
          </button>
        ))}
      </nav>

      {(starting || section === "new") && (
        <div className="mb-8">
          <StartApplication onDone={() => { setStarting(false); setSection("overview"); }} />
        </div>
      )}

      {(section === "overview" || section === "applications") && (
        <>
          {list.length > 0 && (
            <section aria-label="Application summary" className="sheet mb-6 grid grid-cols-2 gap-4 p-4 text-sm sm:grid-cols-4">
              <div><div className="font-display text-2xl leading-none">{list.length}</div><div className="text-xs text-ink-soft">{plural(list.length, "application").replace(/^\d+\s/, "")}</div></div>
              <div><div className="font-display text-2xl leading-none">{pendingActions}</div><div className="text-xs text-ink-soft">pending actions ({pendingDocs} missing docs, {openDefs} deficiencies)</div></div>
              <div><div className="font-display text-2xl leading-none">{totalOpen}</div><div className="text-xs text-ink-soft">open findings</div></div>
              <div><div className="font-semibold">{fmtDate(lastUpdated, true)}</div><div className="text-xs text-ink-soft">last update</div></div>
            </section>
          )}
          {apps.error ? <ErrorBox error={apps.error} retry={apps.refetch} /> : !apps.data ? <Skeleton /> :
            apps.data.length === 0 ? (
              <Empty title="Start your first application" action={!starting && <button className="btn btn-primary" onClick={() => setStarting(true)}>Start an application</button>}>
                Start one to see the document checklist for your category ({CHECKLIST_PREVIEW.EOA_EXISTING.slice(0, 5).join(", ")}). Nothing is sent to AICTE until you submit.
              </Empty>
            ) : (
              <ul className="grid gap-3">
                {apps.data.map((a: ApplicationSummary) => {
                  const missing = Math.max(0, a.documents_required - a.documents_uploaded);
                  const nextStep = missing > 0 ? `Next step: Upload ${plural(missing, "remaining required document")}`
                    : a.counts.deficiencies > 0 ? `Next step: Fix ${plural(a.counts.deficiencies, "deficiency", "deficiencies")} in 'What to fix'`
                    : !a.submitted_at ? "Next step: Ready to submit to AICTE" : "Submitted — under AICTE scrutiny";
                  return (
                    <li key={a.id}>
                      <Link to={`/applications/${a.id}`} className="sheet grid gap-3 p-5 transition-shadow hover:shadow-[0_0_0_2px_var(--color-ink)] sm:grid-cols-[1fr_auto] sm:items-center">
                        <div className="grid gap-1.5">
                          <div className="font-display text-[1.4rem] leading-tight tracking-[-0.025em]">{a.category_label}, {a.academic_year}</div>
                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-soft">
                            <ProgressBar done={a.documents_uploaded} total={a.documents_required} />
                            <span>{plural(a.counts.deficiencies, "deficiency", "deficiencies")}</span>
                            <span>{plural(a.counts.reviews, "item")} awaiting officer</span>
                          </div>
                          <div className="text-xs font-medium text-ink">{nextStep}</div>
                          <div className="text-xs text-ink-soft">
                            {a.submitted_at ? `Submitted ${fmtDate(a.submitted_at)}` : "Not submitted"}. Updated {fmtDate(a.updated_at, true)}.
                          </div>
                        </div>
                        <div className="grid justify-items-start gap-1.5 sm:justify-items-end">
                          <Pill tone={STATUS_META[a.status].tone} title={STATUS_META[a.status].hint}>{STATUS_META[a.status].label}</Pill>
                          <span className="text-sm text-ink-soft">{a.counts.active ? plural(a.counts.active, "open finding") : "No open findings"}</span>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
        </>
      )}

      {section === "upload" && (
        !primaryApp ? <Empty title="Start an application first" action={<button className="btn btn-primary" onClick={() => setSection("new")}>Create application</button>}>Create an application to upload or scan documents.</Empty>
        : !detail.data ? <Skeleton rows={4} /> : (
          <section className="grid gap-4">
            <h2 className="text-xl">Upload or camera-scan documents ({detail.data.category_label})</h2>
            {journeyState && <ProcessingJourney job={journeyState.job} documentId={journeyState.docId} app={detail.data} onOpenPlan={() => setSection("corrections")} onRetry={() => invalidate(`application:${detail.data!.id}`)} />}
            <ul className="grid gap-3">
              {detail.data.checklist.map((item) => (
                <li key={item.doc_type} className="sheet grid gap-3 p-4 md:grid-cols-[1fr_1.1fr] md:items-center">
                  <div>
                    <div className="font-semibold">{item.label} <span className="text-xs font-normal text-ink-soft">({item.required ? "Required" : "Optional"})</span></div>
                    <p className="text-xs text-ink-soft">{item.note}</p>
                    {item.document && <div className="mt-1 text-xs font-medium">{item.document.original_name} · {fmtBytes(item.document.size_bytes)}</div>}
                  </div>
                  <UploadSlot applicationId={detail.data!.id} docType={item.doc_type} label={item.label} replacing={!!item.document}
                    onJob={(job, docId) => setJourneyState({ job, docId })} accept={item.doc_type === "infra_photo" ? "image/png,image/jpeg" : "application/pdf"} />
                </li>
              ))}
            </ul>
          </section>
        )
      )}

      {section === "documents" && (
        !primaryApp || !detail.data ? <Empty title="No documents uploaded yet">Start an application and upload or scan your first document.</Empty> : (
          <section className="grid gap-3">
            <h2 className="text-xl">My uploaded documents ({detail.data.documents.length})</h2>
            <div className="sheet overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-rule text-left text-ink-soft"><th className="px-4 py-2">Slot</th><th className="px-4 py-2">File</th><th className="px-4 py-2">Status</th><th className="px-4 py-2">Uploaded</th></tr></thead>
                <tbody>
                  {detail.data.documents.map((d) => (
                    <tr key={d.id} className="border-b border-rule/60 last:border-0">
                      <td className="px-4 py-2 font-semibold">{d.doc_type_label}{d.superseded && " (Superseded)"}</td>
                      <td className="px-4 py-2">{d.original_name} ({fmtBytes(d.size_bytes)}, {plural(d.pages, "page")})</td>
                      <td className="px-4 py-2">{d.verification_status ? <Pill tone={VERIFICATION_META[d.verification_status].tone}>{VERIFICATION_META[d.verification_status].label}</Pill> : "Checked"}</td>
                      <td className="px-4 py-2 text-ink-soft">{fmtDate(d.uploaded_at, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )
      )}

      {section === "results" && (
        !primaryApp || !findings.data ? <Empty title="No verification results yet">Upload or scan documents to run AI and regulatory checks.</Empty> : (
          <section className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-xl">Verification results ({findings.data.length})</h2>
              <Link to={`/applications/${primaryApp.id}?tab=findings`} className="btn btn-quiet text-xs">Open full evidence viewer</Link>
            </div>
            {findings.data.length === 0 ? <Empty title="Verification completed without detected issues">All evaluated rules passed.</Empty> : (
              <ul className="grid gap-3">
                {findings.data.map((f) => (
                  <li key={f.id} className="sheet grid gap-1.5 p-4 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <Pill tone={SEVERITY_META[f.severity].tone}>{SEVERITY_META[f.severity].label}</Pill>
                      <span className="text-xs text-ink-soft">{f.rule_id ?? f.source_kind} · {f.state}</span>
                    </div>
                    <div className="font-semibold">{f.title}</div>
                    <p className="text-ink-soft">{f.explanation}</p>
                    <p className="text-xs"><span className="font-semibold">Recommended correction: </span>{f.remedy}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )
      )}

      {section === "corrections" && (
        !primaryApp || !plan.data ? <Empty title="No active corrections">No open deficiencies require replacement.</Empty> : (
          <section className="grid gap-4">
            <h2 className="text-xl">Corrections and resubmissions</h2>
            {plan.data.institution_actions.length === 0 ? <Empty title="Nothing for your institution to replace">No open deficiencies require document replacement.</Empty> : (
              <ul className="grid gap-3">
                {plan.data.institution_actions.map((act) => (
                  <li key={act.id} className="sheet grid gap-3 p-4">
                    <div className="font-semibold">{act.title}</div>
                    <ul className="grid gap-1 text-xs text-ink-soft">{(act.details ?? []).map((d) => <li key={d}>• {d}</li>)}</ul>
                    {act.doc_type && <UploadSlot applicationId={primaryApp.id} docType={act.doc_type} label={label(act.doc_type)} replacing onJob={(job, docId) => { setJourneyState({ job, docId }); setSection("upload"); }} accept={act.doc_type === "infra_photo" ? "image/png,image/jpeg" : "application/pdf"} />}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )
      )}

      {section === "timeline" && (
        !primaryApp || !detail.data ? <Empty title="No timeline events yet">Start an application to track its history.</Empty> : (
          <section className="grid gap-3">
            <h2 className="text-xl">Application timeline</h2>
            <ol className="grid gap-2 text-sm">
              <li className="sheet p-3.5"><strong>Application created</strong> · {fmtDate(detail.data.created_at, true)}</li>
              {detail.data.documents.map((d) => <li key={d.id} className="sheet p-3.5"><strong>{d.superseded ? `Replaced ${label(d.doc_type)}` : `Uploaded ${d.doc_type_label}`}</strong> ({d.original_name}) · {fmtDate(d.uploaded_at, true)}</li>)}
              {detail.data.submitted_at && <li className="sheet p-3.5"><strong>Submitted to AICTE</strong> · {fmtDate(detail.data.submitted_at, true)}</li>}
            </ol>
          </section>
        )
      )}

      {section === "notifications" && (
        <section className="grid gap-3">
          <h2 className="text-xl">Applicant notifications</h2>
          {!primaryApp ? <Empty title="No notifications">Notifications appear here as documents are verified.</Empty> : (
            <ul className="grid gap-2 text-sm">
              <li className="sheet flex items-center justify-between gap-2 p-3.5">
                <span><strong>Status update:</strong> {primaryApp.category_label} is <em>{STATUS_META[primaryApp.status].label}</em> ({plural(primaryApp.counts.deficiencies, "deficiency", "deficiencies")}).</span>
                <Link to={`/applications/${primaryApp.id}`} className="link text-xs">Open workspace</Link>
              </li>
              {(findings.data ?? []).filter((f) => f.state === "CLARIFICATION_REQUESTED").map((f) => (
                <li key={f.id} className="sheet flex items-center justify-between gap-2 border-l-4 border-turmeric p-3.5">
                  <span><strong>Clarification requested:</strong> {f.title} — {f.reviews.at(-1)?.reason}</span>
                  <Link to={`/applications/${primaryApp.id}?tab=findings`} className="link text-xs">Respond</Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {section === "profile" && user && (
        <section className="sheet grid max-w-2xl gap-4 p-5 text-sm">
          <h2 className="text-xl">Profile & settings</h2>
          <dl className="grid gap-2 sm:grid-cols-2">
            <div><dt className="text-xs text-ink-soft">Nodal officer</dt><dd className="font-semibold">{user.name}</dd></div>
            <div><dt className="text-xs text-ink-soft">Email</dt><dd className="font-semibold">{user.email}</dd></div>
            <div><dt className="text-xs text-ink-soft">Role</dt><dd>{ROLE_LABEL[user.role]}</dd></div>
            <div><dt className="text-xs text-ink-soft">Institution</dt><dd>{user.institution_name ?? "—"}</dd></div>
          </dl>
          <div className="flex flex-wrap items-center gap-3 border-t border-rule pt-3">
            <button type="button" className="btn btn-quiet text-xs" onClick={() => setLang(lang === "en" ? "hi" : "en")}>
              Language: {lang === "en" ? "English (हिन्दी)" : "हिन्दी (English)"}
            </button>
            <button type="button" className="btn btn-quiet text-xs" onClick={signOut}>Sign out</button>
          </div>
        </section>
      )}
    </>
  );
}

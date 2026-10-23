import type { MouseEvent } from "react";
import { api, VERIFICATION_STATUS_VALUES, type VerificationStatus } from "../api/client";
import { BlockWordmark } from "../components/BlockWordmark";
import { DocumentJourney, Mark, Scene, UPLOAD_STAGES } from "../components/journey/DocumentJourney";
import { STORY_FIELDS, StoryDocument } from "../components/journey/StoryDocument";
import { openSignIn, SignInDialog } from "../components/SignInDialog";
import { Pill, SimulatedTag } from "../components/ui";
import { VERIFICATION_META } from "../lib/format";
import { useQuery } from "../lib/query";
import { Link } from "../lib/router";
import { homeFor, ROLE_LABEL, useSession } from "../lib/session";

/** Sign-in links point at /login (works without the dialog) and open the dialog when it is there. */
function signInClick(e: MouseEvent<HTMLAnchorElement>) {
  if (openSignIn()) e.preventDefault();
}

const ROLES: [string, string][] = [
  [ROLE_LABEL.INSTITUTION, "Starts applications, uploads documents, sees findings and what to fix for its own institution only."],
  [ROLE_LABEL.OFFICER, "Works the scrutiny queue, checks each finding's proof and records a decision with a reason."],
  [ROLE_LABEL.ADMIN, "Proposes rule-pack changes. A second administrator must activate them."],
  [ROLE_LABEL.AUDITOR, "Reads everything, changes nothing, and can verify that the audit trail is unbroken."],
];

const LIMITS: [string, string][] = [
  ["Never approves or rejects", "The only outputs are findings and a derived scrutiny status. Decisions stay with AICTE officials."],
  ["Never calls a document forged", "Integrity checks raise indicators that need a person, because scans and re-saves trigger them too."],
  ["Abstains when unsure", "An unreadable value or a source that does not answer goes to an officer instead of becoming a deficiency."],
  ["Uses only authorized sources", "DigiLocker and issuer systems connect only after AICTE authorization. Until then nothing is shown as verified by them."],
];

const STATUS_MEANING: Record<VerificationStatus, string> = {
  VERIFIED: "Signature or source response checked out and the printed values match the issuer's record.",
  MISMATCH_DETECTED: "The signature failed or at least one printed value differs from what the source holds.",
  EXPIRED: "The issuer confirms the certificate is authentic, but its validity ends before the academic year starts.",
  VERIFICATION_PENDING: "Queued for source verification while the document pipeline is still running.",
  SOURCE_UNAVAILABLE: "The source is not connected or did not respond; routed to an officer instead of guessing.",
  MANUAL_REVIEW_REQUIRED: "No registered issuer key or registry entry matched; an officer confirms with the issuer.",
};

const PREVIEW_DECISIONS: [string, string][] = [
  ["Confirm", "The finding stands and will inform scrutiny."],
  ["Ask the institution", "The institution is asked to explain or correct."],
  ["Escalate", "Refer to a senior officer or for inspection."],
  ["Dismiss", "The finding does not apply; your reason is recorded."],
];

const AUDIT_CHAIN_ILLUSTRATION: { seq: string; action: string; actor: string; prev: string; hash: string }[] = [
  { seq: "#101", action: "document.uploaded", actor: "nodal@godavari.synthetic.in", prev: "00000000", hash: "4a9c18e2" },
  { seq: "#102", action: "validation.completed", actor: "system", prev: "4a9c18e2", hash: "9f31b04d" },
  { seq: "#103", action: "finding.reviewed", actor: "officer@aicte.synthetic.in", prev: "9f31b04d", hash: "c72e65a1" },
];

export function Landing() {
  const { user } = useSession();
  const meta = useQuery("meta", () => api("meta"));
  const pack = meta.data?.rule_pack_version ?? "2026.1";
  const field = (id: string) => STORY_FIELDS.find((f) => f.id === id)!;

  const primary = user
    ? <Link to={homeFor(user)} className="btn btn-primary min-h-11 px-5 text-base">Open your workspace</Link>
    : <a href="/login" onClick={signInClick} className="btn btn-primary min-h-11 px-5 text-base">Sign in</a>;

  return (
    <div className="min-h-dvh">
      {!user && (
        <a href="/login" onClick={signInClick}
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-48 focus:z-50 focus:rounded-sm focus:bg-sheet focus:px-3 focus:py-2">
          Skip to sign in
        </a>
      )}

      <header className="sticky top-0 z-30 border-b border-ink bg-paper">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-4 px-4 sm:px-6">
          <a href="#main" className="text-ink" title="PRAMAAN, back to the top"><BlockWordmark className="h-5 w-auto sm:h-6" /></a>
          <nav aria-label="Page" className="hidden items-center gap-6 text-sm md:flex">
            <a className="link no-underline hover:underline" href="#scene-1">How a check works</a>
            <a className="link no-underline hover:underline" href="#product">After you sign in</a>
            <a className="link no-underline hover:underline" href="#trust">Safeguards</a>
          </nav>
          {user
            ? <Link to={homeFor(user)} className="btn btn-primary min-h-9 px-4">Open your workspace</Link>
            : <a href="/login" onClick={signInClick} className="btn btn-primary min-h-9 px-4">Sign in</a>}
        </div>
      </header>

      <main id="main">
        <h1 className="sr-only">PRAMAAN — evidence-linked validation for AICTE approval applications</h1>
        <DocumentJourney>
          <Scene index={0} label="Introduction">
            <BlockWordmark animate className="h-auto w-full text-ink" />
            <div className="mt-3 flex flex-wrap justify-between gap-x-2 gap-y-1 border-y border-ink py-1.5 text-[0.625rem] whitespace-nowrap sm:text-xs">
              <span>Validation</span><span>Document authentication</span><span>Regulatory compliance</span>
            </div>
            <p className="mt-8 font-display text-[clamp(1.5rem,2.6vw,2.4rem)] leading-[1.08] tracking-[-0.03em]">
              Every flag carries its proof. PRAMAAN checks AICTE approval applications before scrutiny begins, and shows
              the rule, the place on the page and what the issuer said.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              {primary}
              <a href="#scene-1" className="btn btn-quiet min-h-11 px-5 text-base">Follow a document</a>
            </div>
            <p className="mt-4 text-sm text-ink-soft">Officials make every decision. The document below is synthetic, from the demo data.</p>
          </Scene>

          <Scene index={1} id="scene-1" label="The problem">
            <p className="label">(1) The pile</p>
            <h2 className="mt-2 text-[clamp(2rem,3.3vw,3.2rem)]">One application, a stack of papers.</h2>
            <p className="mt-4 text-[1.0625rem] text-ink-soft">
              An Extension of Approval application comes with an EoA letter, an affidavit, a fire safety NOC, a structural
              stability certificate and a faculty summary. Each has to be read, compared with the others, checked against
              the Approval Process Handbook and, where possible, confirmed with whoever issued it.
            </p>
            <ul className="mt-6 grid gap-2.5 text-[0.9375rem]">
              <Mark at={1.15}>Values compared between documents by eye</Mark>
              <Mark at={1.3}>Validity dates checked against the academic calendar by hand</Mark>
              <Mark at={1.45}>Issuers contacted one at a time</Mark>
              <Mark at={1.6}>A changed figure is easy to miss</Mark>
            </ul>
          </Scene>

          <Scene index={2} label="Upload">
            <p className="label">(2) Upload</p>
            <h2 className="mt-2 text-[clamp(2rem,3.3vw,3.2rem)]">The institution uploads its fire safety NOC.</h2>
            <p className="mt-4 text-[1.0625rem] text-ink-soft">
              The checklist for its application category asks for one. PRAMAAN checks the file by what it contains, not by
              its name, and shows each stage while it works. These are the stage names the real pipeline reports.
            </p>
            <ol className="mt-6 grid gap-2.5 text-[0.9375rem]">
              {UPLOAD_STAGES.map((s, i) => <Mark key={s} at={Number((2.15 + (0.6 * i) / UPLOAD_STAGES.length).toFixed(2))}>{s}</Mark>)}
            </ol>
          </Scene>

          <Scene index={3} tall label="Handover">
            <p className="label">(3) Handover</p>
            <h2 className="mt-2 text-[clamp(2rem,3.3vw,3.2rem)]">From the institution's desk into the record.</h2>
            <p className="mt-4 text-[1.0625rem] text-ink-soft">Once the file is accepted, it is no longer just an attachment. It becomes evidence with a history.</p>
            <ul className="mt-6 grid gap-2.5 text-[0.9375rem]">
              <Mark at={3.45}>Type confirmed from the file's own bytes</Mark>
              <Mark at={3.6}>SHA-256 fingerprint recorded</Mark>
              <Mark at={3.75}>Stored privately; shown only to people allowed to see it</Mark>
              <Mark at={3.88}>Entry written to the hash-chained audit trail</Mark>
            </ul>
          </Scene>

          <Scene index={4} tall label="Reading" still={{ boxes: STORY_FIELDS.map((f) => f.id) }}>
            <p className="label">(4) Reading</p>
            <h2 className="mt-2 text-[clamp(2rem,3.3vw,3.2rem)]">Every value keeps its place on the page.</h2>
            <p className="mt-4 text-[1.0625rem] text-ink-soft">
              Text is read with its position; scanned pages go through OCR. Each value keeps its page, its box and how sure
              the reader was, so anyone can check it against the page.
            </p>
            <ul className="mt-6 grid gap-2.5 text-[0.9375rem]">
              {STORY_FIELDS.map((f, i) => (
                <Mark key={f.id} at={Number((4.12 + i * 0.1).toFixed(2))}>
                  <span className="font-medium">{f.label}</span> <span className="text-ink-soft">·</span> {f.value} <span className="text-ink-soft">· page 1</span>
                </Mark>
              ))}
            </ul>
          </Scene>

          <Scene index={5} label="Integrity" still={{ textLayer: true }}>
            <p className="label">(5) Integrity</p>
            <h2 className="mt-2 text-[clamp(2rem,3.3vw,3.2rem)]">Indicators, never verdicts.</h2>
            <p className="mt-4 text-[1.0625rem] text-ink-soft">
              PRAMAAN compares what a reader sees on the page with the text stored inside the file, looks at how the file
              was saved, and checks whether the same evidence appears in another application.
            </p>
            <ul className="mt-6 grid gap-2.5 text-[0.9375rem]">
              <Mark at={5.3}>Visible text and embedded text agree</Mark>
              <Mark at={5.44}>Saved once, with no later revisions</Mark>
              <Mark at={5.58}>Issued before its validity ends</Mark>
              <Mark at={5.72}>Fingerprint not seen in another application</Mark>
            </ul>
            <p className="mt-6 text-sm text-ink-soft">
              Scans and re-saves can raise these indicators too, so an indicator is a reason to look closer, never proof
              that a document was altered.
            </p>
          </Scene>

          <Scene index={6} label="Sources">
            <p className="label">(6) Sources</p>
            <h2 className="mt-2 text-[clamp(2rem,3.3vw,3.2rem)]">Ask the issuer, strongest source first.</h2>
            <p className="mt-4 text-[1.0625rem] text-ink-soft">
              The verification ladder tries the most reliable source it has and stops at the first clear answer. Every
              attempt is recorded, and anything standing in for a real source is labelled.
            </p>
            <ul className="mt-6 grid gap-2.5 text-[0.9375rem]">
              <Mark at={6.2}>Signed QR: the signature checks out against the registered key of the synthetic issuer SYN-FIRE-TS</Mark>
              <Mark at={6.34}>The signed data says valid until 31-03-2026, the same as the print</Mark>
              <Mark at={6.46} className="font-semibold">Result: Authentic, expired</Mark>
              <Mark at={6.58}>Issuer registry not needed here; in this prototype it is a simulated source</Mark>
              <Mark at={6.7}>DigiLocker not connected; it needs AICTE authorization</Mark>
            </ul>
          </Scene>

          <Scene index={7} label="Rules" still={{ flag: true }}>
            <p className="label">(7) Rules</p>
            <h2 className="mt-2 text-[clamp(2rem,3.3vw,3.2rem)]">Then the rules, each tied to a Handbook clause.</h2>
            <p className="mt-4 text-[1.0625rem] text-ink-soft">Rule pack v{pack} runs the rules that read this document. Each one ends Met, Not met, Could not be evaluated (sent to an officer) or Not applicable.</p>
            <ul className="mt-6 grid gap-2.5 text-[0.9375rem]">
              <Mark at={7.2}><b className="font-semibold">DOC.FIRE_NOC.PRESENT</b> Fire safety NOC submitted · Met</Mark>
              <Mark at={7.32}><b className="font-semibold">VERIFY.FIRE_NOC</b> Confirmed with its issuer · Met</Mark>
              <Mark at={7.46} tone="tape"><b className="font-semibold">FIRE.VALID</b> Valid at the start of the academic year · Not met</Mark>
            </ul>
            <p className="mt-6 text-sm text-ink-soft">
              Clause references stay marked “not yet verified” until checked against the Handbook. The academic year start,
              01-07-2026, is a stated assumption in the rule pack.
            </p>
          </Scene>

          <Scene index={8} label="The finding" still={{ flag: true, boxes: ["validTo"] }}>
            <p className="label">(8) The finding</p>
            <h2 className="mt-2 text-[clamp(2rem,3.3vw,3.2rem)]">A finding an officer can check in seconds.</h2>
            <ol className="mt-6 grid gap-2.5 text-[0.9375rem]">
              <Mark at={8.15} tone="tape"><b className="font-semibold">Rule applied</b> FIRE.VALID, pack v{pack}, clause not yet verified</Mark>
              <Mark at={8.22} tone="tape"><b className="font-semibold">Evidence read</b> {field("validTo").label} {field("validTo").value}, page 1</Mark>
              <Mark at={8.29} tone="tape"><b className="font-semibold">What the check found</b> 31-03-2026 is before 01-07-2026</Mark>
              <Mark at={8.36} tone="tape"><b className="font-semibold">Source check</b> Signed QR: Authentic, expired</Mark>
              <Mark at={8.43} tone="tape"><b className="font-semibold">Official decision</b> Waiting for an officer</Mark>
            </ol>
            <p className="mt-6 text-sm text-ink-soft">
              What would clear it: a renewed NOC valid beyond the start of the academic year. When the institution uploads
              one, only the rules that read the NOC run again.
            </p>
          </Scene>
        </DocumentJourney>

        <section id="product" className="mx-auto max-w-[1400px] scroll-mt-16 px-4 py-14 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-ink pb-3">
            <div>
              <h2 className="text-[clamp(1.9rem,3vw,2.9rem)]">After you sign in</h2>
              <p className="mt-1 max-w-2xl text-sm text-ink-soft">
                Institutions check their own bundle before submitting; scrutiny officers review submitted applications with
                every finding's proof beside the page.
              </p>
            </div>
            {user
              ? <Link to={homeFor(user)} className="btn btn-primary min-h-9 px-4 text-sm">Open your workspace</Link>
              : <a href="/login" onClick={signInClick} className="btn btn-primary min-h-9 px-4 text-sm">Sign in to open your workspace</a>}
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-2 lg:items-start">
            {/* Institution nodal officer preview */}
            <article className="sheet cut grid gap-2.5 p-3.5 [--cut:20px]" aria-label="Institution nodal officer preview">
              <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule pb-2">
                <div>
                  <div className="label">Institution nodal officer</div>
                  <h3 className="mt-0.5 text-base font-semibold sm:text-lg">Godavari College of Engineering (Synthetic)</h3>
                </div>
                <span className="rounded-sm bg-paper px-2 py-0.5 text-[11px] font-medium text-ink-soft">
                  Synthetic demo preview
                </span>
              </header>

              <div>
                <div className="mb-1 text-xs font-semibold text-ink-soft">Document checklist · Extension of Approval, 2026-27</div>
                <ul className="grid gap-1 text-xs sm:text-sm">
                  <li className="flex flex-wrap items-center justify-between gap-2 rounded-sm bg-paper px-2.5 py-1">
                    <span className="font-semibold">Previous Extension of Approval letter</span>
                    <span className="flex flex-wrap items-center gap-1.5">
                      <Pill tone={VERIFICATION_META.VERIFIED.tone}>{VERIFICATION_META.VERIFIED.label}</Pill>
                      <SimulatedTag />
                    </span>
                  </li>
                  <li className="flex flex-wrap items-center justify-between gap-2 rounded-sm bg-paper px-2.5 py-1">
                    <span className="font-semibold">Fire safety NOC</span>
                    <Pill tone={VERIFICATION_META.EXPIRED.tone}>{VERIFICATION_META.EXPIRED.label}</Pill>
                  </li>
                  <li className="flex flex-wrap items-center justify-between gap-2 rounded-sm bg-paper px-2.5 py-1">
                    <span className="font-semibold">Structural stability certificate</span>
                    <Pill tone="tape">Required, not uploaded</Pill>
                  </li>
                </ul>
              </div>

              <div className="border-t border-rule pt-2">
                <div className="mb-1 text-xs font-semibold text-ink-soft">What to fix</div>
                <div className="grid grid-cols-[1.25rem_1fr] gap-2 rounded-sm bg-paper p-2 text-xs sm:text-sm">
                  <span className="font-display text-xl leading-none tracking-[-0.04em] text-tape">1</span>
                  <div>
                    <div className="font-semibold leading-snug">Upload a renewed fire safety NOC valid beyond the start of the academic year.</div>
                    <div className="mt-0.5 text-[11px] text-ink-soft">Clears: Fire safety NOC valid at the start of the academic year</div>
                  </div>
                </div>
              </div>
            </article>

            {/* Scrutiny officer preview */}
            <article className="sheet cut grid gap-2.5 p-3.5 [--cut:20px]" aria-label="Scrutiny officer preview">
              <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule pb-2">
                <div>
                  <div className="label">Scrutiny officer</div>
                  <h3 className="mt-0.5 text-base font-semibold sm:text-lg">Scrutiny queue and finding review</h3>
                </div>
                <span className="rounded-sm bg-paper px-2 py-0.5 text-[11px] font-medium text-ink-soft">
                  Synthetic demo preview
                </span>
              </header>

              <div className="flex flex-wrap items-center justify-between gap-2 rounded-sm bg-paper px-2.5 py-1 text-xs sm:text-sm">
                <div>
                  <span className="font-semibold">Godavari College of Engineering (Synthetic)</span>{" "}
                  <span className="text-xs text-ink-soft">· 1-SYN-5520-0002 · EoA 2026-27</span>
                </div>
                <Pill tone="tape">Deficiencies flagged</Pill>
              </div>

              <div className="grid gap-1.5 border-t border-rule pt-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <strong className="text-xs font-semibold sm:text-sm">Fire safety NOC valid at the start of the academic year</strong>
                  <Pill tone="tape">Deficiency</Pill>
                </div>

                <div aria-disabled="true" className="grid gap-1.5 rounded-sm bg-paper p-2 opacity-75 select-none">
                  <div>
                    <div className="mb-1 text-[11px] font-semibold text-ink-soft">Your decision (preview — sign in as an officer to record)</div>
                    <div className="grid grid-cols-2 gap-1">
                      {PREVIEW_DECISIONS.map(([labelText, hint], i) => (
                        <div key={labelText} className="flex items-start gap-1.5 rounded-sm bg-sheet/80 px-2 py-1 text-xs shadow-[inset_0_0_0_1px_var(--color-rule)]">
                          <span aria-hidden="true" className="mt-0.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full border border-ink-faint">
                            {i === 0 && <span className="m-0.5 block h-1 w-1 rounded-full bg-ink-faint" />}
                          </span>
                          <span>
                            <span className="block font-semibold leading-tight text-ink">{labelText}</span>
                            <span className="hidden text-[0.68rem] leading-tight text-ink-soft xl:block">{hint}</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <span className="text-[11px] font-medium text-ink-soft">Reason (recorded with your name)</span>
                    <div className="mt-0.5 rounded-sm bg-sheet/80 px-2 py-1 font-serif text-xs leading-snug text-ink-soft shadow-[inset_0_0_0_1px_var(--color-rule)]">
                      Certificate FNOC/SYN/2024/3310 expires on 31-03-2026, before the 2026-27 academic year starts.
                    </div>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section id="trust" className="mx-auto max-w-[1400px] scroll-mt-16 px-4 pb-14 sm:px-6">
          <div className="border-b border-ink pb-2.5"><h2 className="text-[clamp(1.9rem,3vw,2.9rem)]">Safeguards</h2></div>

          <dl className="mt-3.5 grid grid-cols-2 gap-3.5 lg:grid-cols-4">
            {ROLES.map(([t, d]) => <div key={t} className="border-t border-ink pt-2"><dt className="text-sm font-semibold">{t}</dt><dd className="mt-0.5 text-xs leading-snug text-ink-soft">{d}</dd></div>)}
          </dl>

          <dl className="mt-4 grid grid-cols-2 gap-3.5 lg:grid-cols-4">
            {LIMITS.map(([t, d]) => <div key={t} className="border-t border-rule pt-2"><dt className="text-sm font-semibold">{t}</dt><dd className="mt-0.5 text-xs leading-snug text-ink-soft">{d}</dd></div>)}
          </dl>

          <div className="mt-4 grid gap-4 border-t border-rule pt-3 lg:grid-cols-[1.45fr_1fr] lg:items-start">
            <div>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold">Six verification statuses from the problem statement</h3>
                <span className="text-xs text-ink-soft">Unconnected or unresponsive sources never appear as verified.</span>
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {VERIFICATION_STATUS_VALUES.map((s) => {
                  const m = VERIFICATION_META[s];
                  return (
                    <div key={s} className="sheet p-2">
                      <dt className="flex flex-wrap items-center justify-between gap-1">
                        <Pill tone={m.tone}>{m.label}</Pill>
                        <code className="hidden text-[10px] text-ink-faint xl:inline">{s}</code>
                      </dt>
                      <dd className="mt-1 text-[11px] leading-snug text-ink-soft">{STATUS_MEANING[s]}</dd>
                    </div>
                  );
                })}
              </dl>
            </div>

            <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-1">
              <div className="sheet p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">Tamper-evident audit trail</h3>
                  <span className="text-xs text-ink-soft">Hash-chained · one-click auditor check</span>
                </div>
                <ol className="mt-1.5 grid gap-1 text-xs">
                  {AUDIT_CHAIN_ILLUSTRATION.map((e) => (
                    <li key={e.seq} className="flex flex-wrap items-center justify-between gap-2 rounded-sm bg-paper px-2 py-0.5">
                      <span>
                        <strong className="font-semibold text-ink">{e.seq}</strong>{" "}
                        <span className="font-medium">{e.action}</span>{" "}
                        <span className="text-ink-soft">by {e.actor}</span>
                      </span>
                      <code className="text-[11px] text-ink-soft">{e.prev} → <strong className="text-ink">{e.hash}</strong></code>
                    </li>
                  ))}
                </ol>
              </div>

              <div className="sheet p-3">
                <h3 className="text-sm font-semibold">Four-eyes rule governance</h3>
                <p className="mt-1 text-xs leading-snug text-ink-soft">
                  A rule change needs a second administrator to activate it. Every validation run records the rule-pack
                  version and content hash it used, so past findings remain reproducible.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto grid max-w-[1400px] grid-cols-[1fr_7.5rem] items-center gap-6 px-4 pb-16 sm:grid-cols-[1fr_11rem] sm:gap-10 sm:px-6 lg:grid-cols-[1fr_18rem]">
          <div>
            <h2 className="text-[clamp(2rem,3.6vw,3.4rem)]">Every flag carries its proof.</h2>
            <p className="mt-4 max-w-2xl text-ink-soft">Sign in as an institution to upload and fix, or as AICTE staff to review. Demo accounts are listed in the sign-in form.</p>
            <div className="mt-6">{primary}</div>
          </div>
          <div className="journey-paper relative mx-auto w-full max-w-[18rem]" style={{ aspectRatio: "210 / 297" }}>
            <StoryDocument still={{ flag: true }} />
            <span aria-hidden="true" className="journey-ribbon" style={{ transform: "scaleY(1)" }} />
          </div>
        </section>
      </main>

      <footer className="border-t border-ink">
        <div className="mx-auto flex max-w-[1400px] flex-wrap justify-between gap-x-6 gap-y-2 px-4 py-3 text-xs text-ink-soft sm:px-6">
          <span>Smart India Hackathon 2026, problem statement SIH26261 (AICTE)</span>
          <span>Decision support only. Officials decide.</span>
        </div>
      </footer>
      <SignInDialog />
    </div>
  );
}

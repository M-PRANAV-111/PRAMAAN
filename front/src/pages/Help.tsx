import { useState } from "react";
import { VERIFICATION_STATUS_VALUES, type Role, type VerificationStatus } from "../api/client";
import { PageHeader } from "../components/AppShell";
import { Pill } from "../components/ui";
import { VERIFICATION_META } from "../lib/format";
import { ROLE_LABEL, useSession } from "../lib/session";

const ROLE_GUIDES: Record<Role, { summary: string; steps: [string, string][] }> = {
  INSTITUTION: {
    summary: "Run a complete pre-flight check on your Extension of Approval bundle before submitting to AICTE.",
    steps: [
      ["Start an application", "Choose your category and academic year to generate the required checklist."],
      ["Upload or scan documents", "Upload PDFs or scan pages. PRAMAAN extracts fields and runs active Handbook rules."],
      ["Review 'What to fix' & replace", "Upload a corrected document to re-run only the rules that read that document."],
    ],
  },
  OFFICER: {
    summary: "Inspect submitted applications with every flag linked to its Handbook rule, page coordinates, and source check.",
    steps: [
      ["Work the scrutiny queue", "Search by institution or Permanent ID, filter by status, and open applications."],
      ["Check the 5-link proof chain", "Click any evidence item to zoom the viewer directly to the extracted value."],
      ["Record a reasoned decision", "Confirm, ask for clarification, escalate, or dismiss with a reason (≥ 10 chars)."],
    ],
  },
  ADMIN: {
    summary: "Maintain the versioned YAML rule pack under four-eyes governance and oversee system readiness.",
    steps: [
      ["Propose parameter updates", "Submit a rule parameter change citing the Handbook clause or circular."],
      ["Four-eyes activation", "A second administrator reviews and activates the proposed version."],
      ["Review registrations & users", "Accept or decline registrations with a reason and invite scrutiny staff."],
    ],
  },
  AUDITOR: {
    summary: "Read-only oversight across all submitted applications, rule versions, and the tamper-evident hash chain.",
    steps: [
      ["Inspect any application or rule", "Open any submitted bundle, proof chain, or rule pack version read-only."],
      ["Verify the hash chain", "Run 'Verify the chain' on the Audit trail page to recompute every SHA-256 link."],
      ["Review benchmark metrics", "Inspect recall across planted defects and false-alarm rates on valid bundles."],
    ],
  },
};

const STATUS_MEANING: Record<VerificationStatus, string> = {
  VERIFIED: "Signature or source response checked out and printed values match the issuer record.",
  MISMATCH_DETECTED: "Signature failed or a printed value differs from what the source holds.",
  EXPIRED: "Authentic certificate, but validity ends before the academic year starts.",
  VERIFICATION_PENDING: "Queued for source verification while the pipeline is running.",
  SOURCE_UNAVAILABLE: "Source unreachable or offline; routed to an officer instead of guessing.",
  MANUAL_REVIEW_REQUIRED: "No registered issuer key matched; an officer confirms with the issuer.",
};

const LIMITS: [string, string][] = [
  ["Never approves or rejects", "Outputs advisory findings and scrutiny routing; decisions stay with AICTE officials."],
  ["Never calls a document forged", "Integrity checks raise human-review indicators because scans can trigger them too."],
  ["Abstains when unsure", "Low-confidence OCR or unreachable sources route to an officer instead of guessing."],
  ["Uses only authorized sources", "Simulated sources are labelled 'Simulated source'; real adapters stay off until authorized."],
];

export function OnboardingTips({ role }: { role: Role }) {
  const key = `pramaan:tips:${role}`;
  const [dismissed, setDismissed] = useState<boolean>(() => {
    try { return localStorage.getItem(key) === "1"; } catch { return false; }
  });
  if (dismissed) return null;
  const guide = ROLE_GUIDES[role];
  return (
    <section aria-label="First-visit tips" className="sheet mb-6 border-l-4 border-ink p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong className="font-semibold">Getting started as {ROLE_LABEL[role]}</strong>
        <button type="button" className="btn btn-quiet min-h-7 px-2.5 text-xs"
          onClick={() => { try { localStorage.setItem(key, "1"); } catch { /* ignore */ } setDismissed(true); }}>
          Dismiss tips
        </button>
      </div>
      <ol className="mt-2.5 grid gap-3 sm:grid-cols-3">
        {guide.steps.map(([title, desc], i) => (
          <li key={title} className="rounded-sm bg-paper p-3">
            <div className="font-semibold">({i + 1}) {title}</div>
            <p className="mt-1 text-xs text-ink-soft">{desc}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Help() {
  const { user } = useSession();
  const [tipsReset, setTipsReset] = useState(false);

  function restoreTips() {
    try {
      (["INSTITUTION", "OFFICER", "ADMIN", "AUDITOR"] as const).forEach((r) => localStorage.removeItem(`pramaan:tips:${r}`));
    } catch { /* ignore */ }
    setTipsReset(true);
  }

  return (
    <>
      <PageHeader
        title="Help & role guide"
        lead="How PRAMAAN works for each role, what the six verification statuses mean, and the strict boundaries of automated decision support."
        actions={
          <button type="button" className="btn btn-quiet" onClick={restoreTips}>
            {tipsReset ? "Onboarding tips restored" : "Show onboarding tips again"}
          </button>
        }
      />

      {user && <OnboardingTips key={tipsReset ? "reset" : "init"} role={user.role} />}

      <section className="mb-10">
        <h2 className="mb-3 text-xl">Guide by role</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {(Object.entries(ROLE_GUIDES) as [Role, typeof ROLE_GUIDES[Role]][]).map(([r, g]) => (
            <article key={r} className="sheet grid gap-3 p-5">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-lg">{ROLE_LABEL[r]}</h3>
                {user?.role === r && <Pill tone="leaf">Your role</Pill>}
              </div>
              <p className="text-sm text-ink-soft">{g.summary}</p>
              <ol className="grid gap-2 text-sm">
                {g.steps.map(([t, d], i) => (
                  <li key={t} className="rounded-sm bg-paper px-3 py-2">
                    <span className="font-semibold">{i + 1}. {t}: </span>
                    <span className="text-ink-soft">{d}</span>
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </div>
      </section>

      <section className="mb-10">
        <h2 className="mb-3 text-xl">Six verification statuses</h2>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {VERIFICATION_STATUS_VALUES.map((s) => (
            <div key={s} className="sheet p-4">
              <dt className="flex items-center justify-between gap-2">
                <Pill tone={VERIFICATION_META[s].tone}>{VERIFICATION_META[s].label}</Pill>
                <code className="text-xs text-ink-faint">{s}</code>
              </dt>
              <dd className="mt-2 text-sm text-ink-soft">{STATUS_MEANING[s]}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section>
        <h2 className="mb-3 text-xl">What PRAMAAN never does</h2>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {LIMITS.map(([t, d]) => (
            <div key={t} className="sheet p-4">
              <dt className="font-semibold">{t}</dt>
              <dd className="mt-1 text-sm text-ink-soft">{d}</dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}

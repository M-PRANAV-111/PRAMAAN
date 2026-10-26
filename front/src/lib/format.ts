import type { ApplicationStatus, VerificationStatus } from "../api/client";

export function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-IN", withTime
    ? { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

type Tone = "tape" | "turmeric" | "leaf" | "dusk" | "neutral";

export const STATUS_META: Record<ApplicationStatus, { label: string; tone: Tone; hint: string }> = {
  DRAFT: { label: "Draft", tone: "neutral", hint: "No checks have run yet" },
  PROCESSING: { label: "Checking documents", tone: "dusk", hint: "Documents are being read and checked" },
  READY_FOR_SCRUTINY: { label: "Ready for scrutiny", tone: "leaf", hint: "No open findings; officials still decide" },
  DEFICIENCIES_FLAGGED: { label: "Deficiencies flagged", tone: "tape", hint: "At least one required item is missing or invalid" },
  MANUAL_REVIEW_REQUIRED: { label: "Needs official review", tone: "turmeric", hint: "Items need an officer to confirm" },
};

export const VERIFICATION_META: Record<VerificationStatus, { label: string; tone: Tone }> = {
  VERIFIED: { label: "Verified at source", tone: "leaf" },
  MISMATCH_DETECTED: { label: "Mismatch with source", tone: "tape" },
  EXPIRED: { label: "Authentic, expired", tone: "tape" },
  VERIFICATION_PENDING: { label: "Verification pending", tone: "dusk" },
  SOURCE_UNAVAILABLE: { label: "Source unavailable", tone: "turmeric" },
  MANUAL_REVIEW_REQUIRED: { label: "Manual check needed", tone: "turmeric" },
};

export const TONE_CLASS: Record<Tone, string> = {
  tape: "bg-tape-wash text-tape",
  turmeric: "bg-turmeric-wash text-turmeric",
  leaf: "bg-leaf-wash text-leaf",
  dusk: "bg-dusk-wash text-dusk",
  neutral: "bg-paper text-ink-soft",
};

export const SEVERITY_META = {
  DEFICIENCY: { label: "Deficiency", tone: "tape" as Tone },
  REVIEW: { label: "Needs review", tone: "turmeric" as Tone },
  INFO: { label: "Note", tone: "neutral" as Tone },
};

export const FINDING_STATE_LABEL: Record<string, string> = {
  OPEN: "Open", CONFIRMED: "Confirmed by officer", DISMISSED: "Dismissed by officer", ESCALATED: "Escalated",
  CLARIFICATION_REQUESTED: "Clarification requested", RESOLVED: "Resolved by re-check",
};

export const CHANNEL_LABEL: Record<string, string> = {
  signed_qr: "Signed QR on the certificate",
  aicte_records: "AICTE institutional records",
  issuer_registry: "Issuer registry lookup",
  manual: "Officer confirmation",
};

export const FIELD_LABEL: Record<string, string> = {
  permanent_id: "Permanent ID", application_ref: "Application ID", academic_year: "Academic year",
  issue_date: "Issue date", print_date: "Print date", total_intake: "Total intake", faculty_count: "Regular faculty",
  student_strength: "Student strength", ref_no: "Certificate number", valid_to: "Valid up to", built_up_area: "Built-up area (sq.m)",
};

export const label = (field: string | null | undefined) => (field ? FIELD_LABEL[field] ?? field.replace(/_/g, " ") : "");

/** Why an AI-proposed value was not taken as a claim (rules never read suggestions). */
export const SUGGESTION_REASON: Record<"not_found_on_page" | "conflicts_with_page" | "low_confidence", string> = {
  not_found_on_page: "not found on the page",
  conflicts_with_page: "differs from what the page shows",
  low_confidence: "could not be matched confidently",
};

/** How a value was read: the template extractor, or an AI proposal that was matched on the page. */
export const extractorLabel = (extractor: string) =>
  extractor === "ai+text" ? "AI-assisted, matched on the text layer"
  : extractor === "ai+ocr" ? "AI-assisted, matched on the scan (OCR)"
  : extractor.startsWith("ocr") ? "OCR" : "Text layer";

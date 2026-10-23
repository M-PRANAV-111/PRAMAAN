import type { ReactNode } from "react";
import type { EvidenceRef, FindingOut, VerificationOut } from "../api/client";
import { CHANNEL_LABEL, FINDING_STATE_LABEL, VERIFICATION_META, fmtDate, label } from "../lib/format";
import { Pill, SimulatedTag, cx } from "./ui";

type Obj = Record<string, any>;

function Link_({ step, title, children, last }: { step: number; title: string; children: ReactNode; last?: boolean }) {
  return (
    <li className="relative grid grid-cols-[1.75rem_1fr] gap-3">
      <div className="relative flex justify-center">
        <span className="z-10 mt-0.5 grid h-7 w-7 place-items-center bg-tape text-xs font-semibold text-white tabular [clip-path:polygon(0_0,calc(100%-7px)_0,100%_7px,100%_100%,0_100%)]">{step}</span>
        {!last && <span aria-hidden className="absolute top-8 bottom-[-0.75rem] w-[3px] rounded bg-tape/70" />}
      </div>
      <div className="min-w-0 pb-5">
        <h4 className="text-base font-semibold tracking-[-0.01em]">{title}</h4>
        <div className="mt-1.5 text-sm">{children}</div>
      </div>
    </li>
  );
}

function ClauseBadge({ clause }: { clause?: Obj }) {
  if (!clause) return null;
  if (clause.status === "TO_VERIFY")
    return <Pill tone="turmeric" title="The clause reference and any threshold must be checked against the official Handbook before use on real applications.">Clause not yet verified</Pill>;
  return <Pill tone="leaf">Source seen</Pill>;
}

function Evaluation({ f }: { f: FindingOut }) {
  const p = f.proof as Obj;
  if (p.outcome === "NOT_EVALUABLE") {
    return <p>The rule <strong>abstained</strong>: {f.explanation} No pass or fail was recorded.</p>;
  }
  if (f.source_kind === "INTEGRITY") {
    const d = (p.detail ?? {}) as Obj;
    if (p.indicator === "VISIBLE_TEXT_MISMATCH")
      return (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-ink-soft">Embedded text</dt><dd className="font-semibold">{d.embedded_text}</dd>
          <dt className="text-ink-soft">What the page shows</dt><dd className="font-semibold text-tape">{d.visible_text}</dd>
          <dt className="text-ink-soft">OCR confidence</dt><dd>{Math.round((d.ocr_confidence ?? 0) * 100)}%</dd>
        </dl>
      );
    if (p.indicator === "INCREMENTAL_UPDATE")
      return <p>The file contains {d.incremental_saves} later revision(s) appended after it was produced. {d.note}</p>;
    return <p>{String(d.title ?? p.indicator)}</p>;
  }
  if (f.source_kind === "DUPLICATE")
    return <p>{p.method === "sha256" ? "Byte-for-byte identical file" : `Perceptual image match — ${p.hamming_distance} of 64 bits differ`} in another institution's application.</p>;
  const type = p.rule?.type;
  if (type === "require_document")
    return <p>Required document type <strong>{label(p.required_doc_type)}</strong> was not among the uploaded documents.</p>;
  if (type === "expiry")
    return <p>Valid up to <strong className="text-tape">{fmtDate(p.valid_to)}</strong>; must be on or after <strong>{fmtDate(p.must_be_on_or_after)}</strong> (start of the academic year). Print and issue dates are not used for expiry.</p>;
  if (type === "consistency") {
    const conflict = (p.conflict ?? {}) as Record<string, string[]>;
    return (
      <div className="grid gap-1.5">
        {Object.entries(conflict).map(([value, sources]) => (
          <div key={value} className="flex flex-wrap items-baseline gap-2">
            <span className="rounded-sm bg-paper px-2 py-0.5 font-semibold">{value}</span>
            <span className="text-ink-soft">in {sources.map((s) => (s.startsWith("record:") ? "AICTE records" : label(s))).join(", ")}</span>
          </div>
        ))}
        {p.tiebreak && <p className="text-ink-soft">AICTE records hold {p.tiebreak.value}; records prevail when deciding which document to correct.</p>}
      </div>
    );
  }
  if (type === "assert") {
    const inputs = (p.inputs ?? {}) as Record<string, Obj>;
    return (
      <div className="grid gap-1.5">
        <code className="w-fit rounded-sm bg-paper px-2 py-1 text-[0.9em]">{p.expr}</code>
        <p className="text-ink-soft">
          {Object.entries(inputs).map(([k, v]) => `${k} = ${v.value}`).join(", ")}
          {p.params && Object.keys(p.params).length > 0 && `; ${Object.entries(p.params).map(([k, v]) => `${k} = ${v}`).join(", ")}`}
          {" "}→ <strong className="text-tape">false</strong>
        </p>
      </div>
    );
  }
  if (type === "verification") return <p>Source check returned <strong>{VERIFICATION_META[p.verification_status as keyof typeof VERIFICATION_META]?.label ?? p.verification_status}</strong>.</p>;
  return <p>{f.explanation}</p>;
}

export function ProofChain({ finding, verifications, activeEvidence, onEvidence, decision }:
  { finding: FindingOut; verifications: VerificationOut[]; activeEvidence: number; onEvidence: (i: number) => void; decision?: ReactNode }) {
  const p = finding.proof as Obj;
  const rule = p.rule as Obj | undefined;
  const docs = new Set(finding.evidence.map((e) => e.document_id).filter(Boolean));
  const attempts = verifications.filter((v) => docs.has(v.document_id));
  return (
    <ol key={finding.id} className="grid animate-fade" aria-label="Proof chain for this finding">
      <Link_ step={1} title={rule ? "Rule applied" : "Check applied"}>
        {rule ? (
          <div className="grid gap-1">
            <div><span className="font-semibold">{rule.id}</span> — {rule.title}</div>
            <div className="flex flex-wrap items-center gap-2 text-ink-soft">
              Rule pack {rule.pack} v{rule.version}. {rule.clause?.ref}
              <ClauseBadge clause={rule.clause} />
            </div>
          </div>
        ) : (
          <p>{finding.source_kind === "DUPLICATE" ? "Duplicate-evidence index across applications" : "Document integrity indicators (explainable, non-ML)"}</p>
        )}
      </Link_>
      <Link_ step={2} title="Evidence read">
        {finding.evidence.length === 0 ? <p className="text-ink-soft">No value was read — the finding is about something absent.</p> : (
          <ul className="grid gap-1.5">
            {finding.evidence.map((e: EvidenceRef, i) => (
              <li key={i}>
                <button type="button" disabled={!e.bbox && !e.document_id || !!e.other_application && !e.document_id}
                  onClick={() => onEvidence(i)}
                  className={cx("w-full rounded-sm px-3 py-2 text-left transition-colors",
                    i === activeEvidence ? "bg-tape-wash shadow-[inset_3px_0_0_var(--color-tape)]" : "bg-paper hover:bg-rule/40")}>
                  <span className="block font-semibold">
                    {e.field ? `${label(e.field)}: ${e.value ?? "—"}` : e.document_name}
                  </span>
                  <span className="block text-xs text-ink-soft">
                    {e.other_application ? "Another institution's application" : label(e.doc_type)}
                    {e.page ? `, page ${e.page}` : ""}
                    {typeof e.confidence === "number" ? `, ${e.extractor?.startsWith("ocr") ? "OCR" : "text layer"} ${Math.round(e.confidence * 100)}%` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Link_>
      <Link_ step={3} title="What the check found"><Evaluation f={finding} /></Link_>
      <Link_ step={4} title="Source check">
        {attempts.length === 0 ? (
          <p className="text-ink-soft">No issuing source applies to these documents; they are declarations checked against each other and AICTE records.</p>
        ) : (
          <ul className="grid gap-1.5">
            {attempts.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2">
                <span className="text-ink-soft">Tier {a.tier}, {CHANNEL_LABEL[a.channel] ?? a.channel}:</span>
                <Pill tone={VERIFICATION_META[a.status].tone}>{VERIFICATION_META[a.status].label}</Pill>
                {a.simulated && <SimulatedTag />}
                <span className="basis-full text-xs text-ink-soft">{String((a.detail as Obj).reason ?? "")}</span>
              </li>
            ))}
          </ul>
        )}
      </Link_>
      <Link_ step={5} title="Official decision" last>
        {finding.reviews.length > 0 && (
          <ul className="mb-3 grid gap-2">
            {finding.reviews.map((r) => (
              <li key={r.id} className="rounded-sm bg-paper px-3 py-2">
                <div className="font-semibold">{FINDING_STATE_LABEL[{ CONFIRM: "CONFIRMED", DISMISS: "DISMISSED", ESCALATE: "ESCALATED", REQUEST_CLARIFICATION: "CLARIFICATION_REQUESTED" }[r.decision]]}</div>
                <p className="font-serif">{r.reason}</p>
                <div className="text-xs text-ink-soft">{r.reviewer_name}, {fmtDate(r.created_at, true)}</div>
              </li>
            ))}
          </ul>
        )}
        {decision ?? (finding.reviews.length === 0 && <p className="text-ink-soft">Awaiting an officer. PRAMAAN only flags; it does not decide.</p>)}
      </Link_>
    </ol>
  );
}

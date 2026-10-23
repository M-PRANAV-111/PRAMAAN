import { useState, type ChangeEvent, type FormEvent } from "react";
import { api, ApiError, type RuleOut } from "../api/client";
import { PageHeader } from "../components/AppShell";
import { Empty, ErrorBox, Pill, Skeleton, cx, useToast } from "../components/ui";
import { fmtDate, label } from "../lib/format";
import { invalidate, useQuery } from "../lib/query";
import { useSession } from "../lib/session";
import { AuditList } from "./Workspace";

const TYPE_LABEL: Record<string, string> = {
  require_document: "Completeness", assert: "Condition", consistency: "Cross-document", expiry: "Validity", verification: "Source check",
};

export function Rules() {
  const { user } = useSession();
  const rules = useQuery("rules", () => api("getRules"));
  if (rules.error) return <ErrorBox error={rules.error} retry={rules.refetch} />;
  if (!rules.data) return <Skeleton rows={6} />;
  const r = rules.data;
  const unverified = r.rules.filter((x) => x.clause.status === "TO_VERIFY").length;
  return (
    <>
      <PageHeader title="Rule pack" kicker={`${r.title}, version ${r.version.version}`}
        lead={<>Rules are data, not code. Each run records the version it used, and changes need a second administrator to take effect. Source: {r.source.document}, checked {r.source.checked_on}.</>} />
      {unverified > 0 && (
        <p className="mb-6 max-w-3xl rounded-sm border-l-4 border-turmeric bg-turmeric-wash px-4 py-3 text-sm">
          <strong>{unverified} of {r.rules.length} rules</strong> cite a clause that has not yet been checked against the Approval Process Handbook text. Their thresholds are placeholders until a domain reviewer confirms them.
        </p>
      )}
      <div className="sheet mb-10 overflow-x-auto">
        <table className="w-full min-w-[52rem] text-sm">
          <thead><tr className="border-b border-rule text-left text-ink-soft">
            <th className="px-4 py-3 font-semibold">Rule</th><th className="px-4 py-3 font-semibold">Kind</th><th className="px-4 py-3 font-semibold">Reads</th>
            <th className="px-4 py-3 font-semibold">Clause</th><th className="px-4 py-3 font-semibold">Parameters</th></tr></thead>
          <tbody>
            {r.rules.map((x: RuleOut) => (
              <tr key={x.id} className="border-b border-rule/60 align-top last:border-0">
                <td className="px-4 py-3"><div className="font-semibold">{x.title}</div><div className="text-xs text-ink-soft">{x.id}{x.applies_to ? `, only ${x.applies_to.join(", ")}` : ""}</div></td>
                <td className="px-4 py-3">{TYPE_LABEL[x.type] ?? x.type}<div className={cx("text-xs", x.severity === "DEFICIENCY" ? "text-tape" : "text-turmeric")}>{x.severity === "DEFICIENCY" ? "Deficiency" : "Review"}</div></td>
                <td className="px-4 py-3 text-ink-soft">{x.reads.map(label).join(", ")}</td>
                <td className="px-4 py-3"><div className="max-w-xs">{x.clause.ref}</div>
                  {x.clause.status === "TO_VERIFY" ? <Pill tone="turmeric">Not yet verified</Pill> : <Pill tone="leaf">Source seen</Pill>}</td>
                <td className="px-4 py-3">{Object.keys(x.params).length ? Object.entries(x.params).map(([k, v]) => <div key={k}><code>{k}</code> = {String(v)}</div>) : <span className="text-ink-faint">None</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid gap-10 lg:grid-cols-2">
        <section>
          <h2 className="mb-3 text-xl">Versions</h2>
          <ol className="grid gap-2">
            {r.versions.map((v) => <VersionRow key={v.id} v={v} canActivate={user?.role === "ADMIN"} />)}
          </ol>
        </section>
        {user?.role === "ADMIN" && <ProposeChange rules={r.rules} />}
      </div>
    </>
  );
}

function VersionRow({ v, canActivate }: { v: { id: string; version: string; status: string; change_note: string; proposed_by_name: string | null; activated_by_name: string | null; created_at: string; activated_at: string | null }; canActivate: boolean }) {
  const toast = useToast();
  const [pending, setPending] = useState(false);
  async function activate() {
    setPending(true);
    try {
      await api("activateRules", { path: { version_id: v.id } });
      invalidate("rules");
      toast(`Version ${v.version} is now active`);
    } catch (e) { toast(e instanceof ApiError ? e.message : "Could not activate", "error"); }
    finally { setPending(false); }
  }
  return (
    <li className="sheet flex flex-wrap items-start justify-between gap-3 p-4 text-sm">
      <div className="min-w-0">
        <div className="flex items-center gap-2"><span className="font-semibold">v{v.version}</span>
          <Pill tone={v.status === "ACTIVE" ? "leaf" : v.status === "PROPOSED" ? "turmeric" : "neutral"}>{v.status === "ACTIVE" ? "Active" : v.status === "PROPOSED" ? "Proposed" : "Retired"}</Pill></div>
        <p className="mt-1 text-ink-soft">{v.change_note}</p>
        <p className="text-xs text-ink-faint">{v.proposed_by_name ? `Proposed by ${v.proposed_by_name}` : "Installed from file"}, {fmtDate(v.created_at, true)}{v.activated_by_name ? `; activated by ${v.activated_by_name}` : ""}</p>
      </div>
      {canActivate && v.status === "PROPOSED" && <button className="btn btn-quiet" disabled={pending} onClick={activate}>Activate</button>}
    </li>
  );
}

function ProposeChange({ rules }: { rules: RuleOut[] }) {
  const toast = useToast();
  const tunable = rules.filter((r) => Object.keys(r.params).length);
  const [ruleId, setRuleId] = useState(tunable[0]?.id ?? "");
  const rule = tunable.find((r) => r.id === ruleId);
  const [param, setParam] = useState(Object.keys(rule?.params ?? {})[0] ?? "");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (!tunable.length) return null;
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await api("proposeRules", { body: { changes: { [ruleId]: { [param]: Number(value) } }, note } });
      invalidate("rules");
      toast(`Proposed v${res.version.version}. Another administrator must activate it.`);
      setValue(""); setNote("");
    } catch (err) { setError(err instanceof ApiError ? err.message : "Could not propose the change."); }
  }
  return (
    <section>
      <h2 className="mb-1 text-xl">Propose a parameter change</h2>
      <p className="mb-3 text-sm text-ink-soft">Creates a new version. It takes effect only when a different administrator activates it, and every run after that records the new version.</p>
      <form onSubmit={submit} className="sheet grid gap-4 p-5">
        <label className="field"><span>Rule</span>
          <select className="input" value={ruleId} onChange={(e: ChangeEvent<HTMLSelectElement>) => { setRuleId(e.target.value); setParam(Object.keys(tunable.find((r) => r.id === e.target.value)?.params ?? {})[0] ?? ""); }}>
            {tunable.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
          </select></label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="field"><span>Parameter</span>
            <select className="input" value={param} onChange={(e: ChangeEvent<HTMLSelectElement>) => setParam(e.target.value)}>
              {Object.entries(rule?.params ?? {}).map(([k, v]) => <option key={k} value={k}>{k} (now {String(v)})</option>)}
            </select></label>
          <label className="field"><span>New value</span><input className="input" type="number" step="any" required value={value} onChange={(e: ChangeEvent<HTMLInputElement>) => setValue(e.target.value)} /></label>
        </div>
        <label className="field"><span>Why (cite the Handbook clause or circular)</span><textarea className="input" required minLength={10} value={note} onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setNote(e.target.value)} /></label>
        {error && <p role="alert" className="text-sm font-semibold text-tape">{error}</p>}
        <button className="btn btn-primary justify-self-start" disabled={!value || note.trim().length < 10}>Propose version</button>
      </form>
    </section>
  );
}

export function AuditPage() {
  const events = useQuery("audit:all", () => api("listAudit", { query: { limit: "300" } }));
  const [result, setResult] = useState<{ valid: boolean; events_checked: number; first_broken_seq: number | null; problem: string | null; head_hash: string | null } | null>(null);
  const [pending, setPending] = useState(false);
  async function verify() {
    setPending(true);
    try { setResult(await api("verifyAudit")); } finally { setPending(false); }
  }
  return (
    <>
      <PageHeader title="Audit trail" lead="Every upload, check, source query and decision is chained: each entry stores the hash of the one before it, so a changed or deleted entry is detectable."
        actions={<button className="btn btn-primary" onClick={verify} disabled={pending}>{pending ? "Checking…" : "Verify the chain"}</button>} />
      {result && (
        <div role="status" className={cx("mb-6 max-w-3xl rounded-sm border-l-4 px-4 py-3 text-sm", result.valid ? "border-leaf bg-leaf-wash" : "border-tape bg-tape-wash")}>
          {result.valid
            ? <><strong>Chain intact.</strong> {result.events_checked} entries recomputed; head hash <code className="break-all">{result.head_hash?.slice(0, 24)}</code>.</>
            : <><strong className="text-tape">Chain broken at entry #{result.first_broken_seq}.</strong> {result.problem}. Entries after it cannot be trusted until investigated.</>}
        </div>
      )}
      {events.error ? <ErrorBox error={events.error} retry={events.refetch} /> : !events.data ? <Skeleton rows={8} /> :
        events.data.length === 0 ? <Empty title="No events yet" /> : <div className="sheet max-w-4xl p-3"><AuditList events={events.data} /></div>}
    </>
  );
}

export function Benchmark() {
  const report = useQuery("benchmark", () => api("benchmark") as Promise<Record<string, any>>);
  return (
    <>
      <PageHeader title="Synthetic benchmark" lead="Planted faults and valid look-alikes run through the real pipeline. These numbers describe behaviour on this project's synthetic documents, not accuracy on real submissions." />
      {report.error ? (
        <Empty title="No benchmark has been run yet">Run <code className="rounded-sm bg-sheet px-1">python -m eval.benchmark</code> in <code className="rounded-sm bg-sheet px-1">backend/</code>, then reload this page.</Empty>
      ) : !report.data ? <Skeleton /> : <BenchmarkReport r={report.data} />}
    </>
  );
}

function BenchmarkReport({ r }: { r: Record<string, any> }) {
  const per = Object.entries(r.per_fault as Record<string, { bundles: number; detected: number; recall: number }>);
  return (
    <div className="grid gap-8">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="sheet p-5"><div className="font-display text-[3rem] leading-none tracking-[-0.04em]">{per.reduce((s, [, v]) => s + v.detected, 0)} of {per.reduce((s, [, v]) => s + v.bundles, 0)}</div><div className="text-sm text-ink-soft">planted faults detected</div></div>
        <div className="sheet p-5"><div className="font-display text-[3rem] leading-none tracking-[-0.04em]">{r.hard_negatives.with_any_finding} of {r.hard_negatives.bundles}</div><div className="text-sm text-ink-soft">valid look-alike bundles that still got a finding</div></div>
        <div className="sheet p-5"><div className="font-display text-[3rem] leading-none tracking-[-0.04em]">{Number(r.seconds_per_bundle.median).toFixed(1)} s</div><div className="text-sm text-ink-soft">median processing per bundle (p95 {Number(r.seconds_per_bundle.p95).toFixed(1)} s, CPU only)</div></div>
      </div>
      <div className="grid gap-8 lg:grid-cols-[3fr_2fr]">
        <section className="sheet overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-rule text-left text-ink-soft"><th className="px-4 py-3 font-semibold">Planted fault</th><th className="px-4 py-3 text-right font-semibold">Detected</th></tr></thead>
            <tbody>{per.map(([k, v]) => (
              <tr key={k} className="border-b border-rule/60 last:border-0"><td className="px-4 py-2.5">{k.replace(/_/g, " ")}</td>
                <td className={cx("px-4 py-2.5 text-right font-semibold", v.detected < v.bundles && "text-tape")}>{v.detected} / {v.bundles}</td></tr>
            ))}</tbody>
          </table>
        </section>
        <section className="grid content-start gap-4 text-sm">
          <h2 className="text-xl">False alarms</h2>
          <p>{r.unexpected_findings.count} of {r.unexpected_findings.of_total_findings} findings were not explained by a planted fault:</p>
          <ul className="grid gap-1">{Object.entries(r.unexpected_findings.by_key as Record<string, number>).map(([k, n]) => <li key={k}><strong>{k}</strong>: {n}</li>)}</ul>
          <p className="text-ink-soft">A legitimately re-saved PDF raises the "modified after creation" indicator. That is by design, which is why it is an indicator for review and never a deficiency.</p>
          <p className="text-ink-soft">Caveat: the generator and the extractors were built together, so detection on these documents is optimistic. Real scans, regional languages and handwriting are not covered.</p>
          <p className="text-xs text-ink-faint">Generated {fmtDate(r.generated_at, true)}; {r.bundles} bundles; Python {r.environment?.python}.</p>
        </section>
      </div>
    </div>
  );
}

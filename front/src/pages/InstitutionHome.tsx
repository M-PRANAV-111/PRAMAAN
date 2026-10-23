import { useState, type ChangeEvent, type FormEvent } from "react";
import { api, ApiError, type ApplicationSummary, type Category } from "../api/client";
import { PageHeader } from "../components/AppShell";
import { Empty, ErrorBox, Pill, Skeleton } from "../components/ui";
import { STATUS_META, fmtDate, plural } from "../lib/format";
import { invalidate, useQuery } from "../lib/query";
import { Link, navigate } from "../lib/router";
import { useSession } from "../lib/session";

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
      {error && <p role="alert" className="text-sm font-semibold text-tape sm:col-span-3">{error}</p>}
    </form>
  );
}

export function InstitutionHome() {
  const { user } = useSession();
  const apps = useQuery("applications", () => api("listApplications"));
  const [starting, setStarting] = useState(false);
  return (
    <>
      <PageHeader title="Your applications" kicker={user?.institution_name}
        lead="Upload documents for a pre-flight check before you submit. Each finding says what to fix and why."
        actions={!starting && <button className="btn btn-primary" onClick={() => setStarting(true)}>Start an application</button>} />
      {starting && <div className="mb-8"><StartApplication onDone={() => setStarting(false)} /></div>}
      {apps.error ? <ErrorBox error={apps.error} retry={apps.refetch} /> : !apps.data ? <Skeleton /> :
        apps.data.length === 0 ? (
          <Empty title="No applications yet" action={!starting && <button className="btn btn-primary" onClick={() => setStarting(true)}>Start an application</button>}>
            Start one to see the document checklist for your category. Nothing is sent to AICTE until you submit.
          </Empty>
        ) : (
          <ul className="grid gap-3">
            {apps.data.map((a: ApplicationSummary) => (
              <li key={a.id}>
                <Link to={`/applications/${a.id}`} className="sheet grid gap-3 p-5 transition-shadow hover:shadow-[0_0_0_2px_var(--color-ink)] sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="grid gap-1.5">
                    <div className="font-display text-[1.4rem] leading-tight tracking-[-0.025em]">{a.category_label}, {a.academic_year}</div>
                    <ProgressBar done={a.documents_uploaded} total={a.documents_required} />
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
            ))}
          </ul>
        )}
    </>
  );
}

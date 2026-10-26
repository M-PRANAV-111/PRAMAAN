import { useState, type ChangeEvent, type FormEvent } from "react";
import { api, ApiError, type AiStatusOut, type RegistrationOut, type NotificationOut, type AdminUserOut } from "../api/client";
import { PageHeader } from "../components/AppShell";
import { Empty, ErrorBox, Pill, Skeleton, useToast } from "../components/ui";
import { callEndpoint, hasEndpoint } from "../lib/features";
import { fmtDate } from "../lib/format";
import { invalidate, useQuery } from "../lib/query";
import { navigate } from "../lib/router";

export function AdminRegistrationsPage() {
  const toast = useToast();
  const regs = useQuery(hasEndpoint("listRegistrations") ? "admin:registrations" : null,
    () => callEndpoint<RegistrationOut[]>("listRegistrations"));
  const [reasons, setReasons] = useState<Record<string, string>>({});

  async function decide(id: string, accept: boolean) {
    const reason = (reasons[id] ?? "").trim();
    if (reason.length < 10) { toast("Provide a reason of at least 10 characters", "error"); return; }
    try {
      await callEndpoint(accept ? "acceptRegistration" : "declineRegistration", { path: { registration_id: id }, body: accept ? { note: reason } : { reason } });
      invalidate("admin:registrations");
      toast(`Registration ${accept ? "accepted" : "declined"}`);
    } catch (e) { toast(e instanceof ApiError ? e.message : "Action failed", "error"); }
  }

  return (
    <>
      <PageHeader title="Institution registrations" lead="Review pending nodal officer registrations. Decisions use Accept or Decline with a recorded reason." />
      {regs.error ? <ErrorBox error={regs.error} retry={regs.refetch} /> : !regs.data ? <Skeleton /> :
        regs.data.length === 0 ? <Empty title="No pending registrations" /> : (
          <ul className="grid gap-3">
            {regs.data.map((r) => (
              <li key={r.id} className="sheet grid gap-3 p-5 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold">{r.institution.name} ({r.institution.aicte_permanent_id}, {r.institution.state})</div>
                    <div className="text-xs text-ink-soft">{r.contact_name} · {r.email} · {fmtDate(r.created_at, true)}</div>
                  </div>
                  <Pill tone={r.status === "ACCEPTED" ? "leaf" : r.status === "DECLINED" ? "tape" : "turmeric"}>{r.status}</Pill>
                </div>
                {r.status === "PENDING" && (
                  <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-end">
                    <label className="field"><span>Reason (≥ 10 chars)</span><input className="input" value={reasons[r.id] ?? ""} onChange={(e: ChangeEvent<HTMLInputElement>) => setReasons({ ...reasons, [r.id]: e.target.value })} /></label>
                    <button className="btn btn-primary" onClick={() => decide(r.id, true)}>Accept</button>
                    <button className="btn btn-quiet" onClick={() => decide(r.id, false)}>Decline</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
    </>
  );
}

export function AdminUsersPage() {
  const toast = useToast();
  const users = useQuery(hasEndpoint("listUsers") ? "admin:users" : null,
    () => callEndpoint<AdminUserOut[]>("listUsers"));
  const [roleFilter, setRoleFilter] = useState("ALL");
  const [invName, setInvName] = useState("");
  const [invEmail, setInvEmail] = useState("");
  const [invRole, setInvRole] = useState("OFFICER");
  const [reasons, setReasons] = useState<Record<string, string>>({});

  async function invite(e: FormEvent) {
    e.preventDefault();
    try {
      await callEndpoint("inviteUser", { body: { name: invName, email: invEmail.trim().toLowerCase(), role: invRole } });
      setInvName(""); setInvEmail("");
      invalidate("admin:users");
      toast("Invitation created");
    } catch (err) { toast(err instanceof ApiError ? err.message : "Could not invite user", "error"); }
  }

  const list = (users.data ?? []).filter((u) => roleFilter === "ALL" || u.role === roleFilter);

  return (
    <>
      <PageHeader title="Users & invitations" lead="Manage scrutiny officers, rule administrators, and auditors." />
      {hasEndpoint("inviteUser") && (
        <form onSubmit={invite} className="sheet mb-6 grid gap-3 p-5 sm:grid-cols-[1fr_1fr_10rem_auto] sm:items-end">
          <label className="field"><span>Name</span><input className="input" required value={invName} onChange={(e: ChangeEvent<HTMLInputElement>) => setInvName(e.target.value)} /></label>
          <label className="field"><span>Email</span><input className="input" type="email" required value={invEmail} onChange={(e: ChangeEvent<HTMLInputElement>) => setInvEmail(e.target.value)} /></label>
          <label className="field"><span>Role</span>
            <select className="input" value={invRole} onChange={(e: ChangeEvent<HTMLSelectElement>) => setInvRole(e.target.value)}>
              <option value="OFFICER">Scrutiny officer</option>
              <option value="ADMIN">Rule administrator</option>
              <option value="AUDITOR">Auditor</option>
            </select>
          </label>
          <button className="btn btn-primary">Invite user</button>
        </form>
      )}
      <div className="mb-4 flex flex-wrap gap-2">
        {["ALL", "INSTITUTION", "OFFICER", "ADMIN", "AUDITOR"].map((r) => (
          <button key={r} className={`btn min-h-8 px-3 text-xs ${roleFilter === r ? "btn-primary" : "btn-quiet"}`} onClick={() => setRoleFilter(r)}>{r}</button>
        ))}
      </div>
      {users.error ? <ErrorBox error={users.error} retry={users.refetch} /> : !users.data ? <Skeleton /> : (
        <div className="sheet overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-rule text-left text-ink-soft"><th className="px-4 py-3">Name</th><th className="px-4 py-3">Email</th><th className="px-4 py-3">Role</th><th className="px-4 py-3">Status</th><th className="px-4 py-3" /></tr></thead>
            <tbody>
              {list.map((u) => (
                <tr key={u.id} className="border-b border-rule/60 last:border-0">
                  <td className="px-4 py-3 font-semibold">{u.name}</td>
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3">{u.role}</td>
                  <td className="px-4 py-3"><Pill tone={u.is_active ? "leaf" : "neutral"}>{u.is_active ? "Active" : "Inactive"}</Pill></td>
                  <td className="px-4 py-3 text-right">
                    {u.is_active && <label className="field"><span>Deactivation reason</span><input className="input" value={reasons[u.id] ?? ""} onChange={e => setReasons({ ...reasons, [u.id]: e.target.value })} /></label>}
                    {(hasEndpoint("deactivateUser") || hasEndpoint("reactivateUser")) && (
                      <button className="btn btn-quiet min-h-7 px-2.5 text-xs"
                        onClick={async () => {
                          try { await callEndpoint(u.is_active ? "deactivateUser" : "reactivateUser", { path: { user_id: u.id }, body: u.is_active ? { reason: reasons[u.id] ?? "" } : undefined }); invalidate("admin:users"); } catch (error) { toast(error instanceof ApiError ? error.message : "Could not update user. Try again.", "error"); }
                        }}>
                        {u.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function AdminSystemPage() {
  const health = useQuery("sys:health", () => api("health"));
  const system = useQuery("sys:system", () => api("systemStatus"));
  const ready = useQuery("sys:ready", () => api("ready"));
  const ai = useQuery(hasEndpoint("aiStatus") ? "sys:ai" : null, () => callEndpoint<AiStatusOut>("aiStatus"));

  return (
    <>
      <PageHeader title="System status" lead="Liveness, readiness checks, worker health, and AI provider configuration (keys are never shown)." />
      {system.error && <ErrorBox error={system.error} retry={system.refetch} />}
      {system.data && <p className="mb-4 text-sm">Worker: {system.data.worker.running}; email: {system.data.email_provider}; last backup: {system.data.backups.last_ok_at ?? "None"}</p>}
      <div className="grid gap-6 md:grid-cols-2">
        <section className="sheet grid gap-3 p-5 text-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-xl">Readiness & subsystems</h2>
            {ready.data && <Pill tone={ready.data.status === "ok" ? "leaf" : "tape"}>{ready.data.status}</Pill>}
          </div>
          {ready.error ? <ErrorBox error={ready.error} retry={ready.refetch} /> : !ready.data ? <Skeleton /> : (
            <dl className="grid grid-cols-[10rem_1fr] gap-y-2">
              {Object.entries(ready.data.checks).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-ink-soft">{k}</dt>
                  <dd className="font-semibold">{v}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        <section className="sheet grid gap-3 p-5 text-sm">
          <h2 className="text-xl">AI & external adapters</h2>
          {ai.error ? <ErrorBox error={ai.error} retry={ai.refetch} /> : ai.data ? (
            <>
              <dl data-ai-status className="grid grid-cols-[10rem_1fr] gap-y-2">
                <dt className="text-ink-soft">Provider</dt>
                <dd className="font-semibold">{ai.data.provider}{ai.data.simulated && <span className="ml-2 rounded-sm bg-dusk-wash px-1.5 py-0.5 text-xs font-semibold text-dusk">Simulated — recorded test answers</span>}</dd>
                <dt className="text-ink-soft">Models</dt><dd>{Object.entries(ai.data.models).map(([k, v]) => `${k}: ${v}`).join(" · ")}</dd>
                <dt className="text-ink-soft">Mode</dt><dd>{ai.data.mode}</dd>
                <dt className="text-ink-soft">Kill switch</dt><dd>{ai.data.kill_switch ? "Engaged — AI off" : "Released"}</dd>
                <dt className="text-ink-soft">Requests today</dt><dd>{ai.data.requests_today} / {ai.data.budget.requests}</dd>
                <dt className="text-ink-soft">Pages today</dt><dd>{ai.data.pages_today} / {ai.data.budget.pages}</dd>
                <dt className="text-ink-soft">Cache hits today</dt><dd>{ai.data.cache_hits_today}</dd>
                <dt className="text-ink-soft">Fallback active</dt><dd>{ai.data.fallback_active ? "Yes" : "No"}</dd>
                {ai.data.last_error_code && <><dt className="text-ink-soft">Last error</dt><dd className="text-turmeric">{ai.data.last_error_code}{ai.data.last_error_at ? ` · ${fmtDate(ai.data.last_error_at, true)}` : ""}</dd></>}
              </dl>
              {hasEndpoint("aiKillSwitch") && ai.data.provider !== "none" && <KillSwitchForm engaged={ai.data.kill_switch} />}
            </>
          ) : (
            <p className="text-ink-soft">
              Deterministic pipeline active (<code>AI_PROVIDER=none</code>). Liveness: <strong>{health.data?.status ?? "checking"}</strong>.
            </p>
          )}
        </section>
      </div>
    </>
  );
}

function KillSwitchForm({ engaged }: { engaged: boolean }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await callEndpoint("aiKillSwitch", { body: { engaged: !engaged, reason: reason.trim() } });
      invalidate("sys:ai");
      setReason("");
      toast(engaged ? "AI kill switch released" : "AI kill switch engaged");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the kill switch.");
    } finally {
      setPending(false);
    }
  }
  return (
    <form onSubmit={submit} className="grid gap-2 border-t border-rule pt-3">
      <label className="field">
        <span>Reason (recorded in the audit trail)</span>
        <textarea className="input" value={reason} minLength={10} maxLength={2000} required
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setReason(e.target.value)} />
      </label>
      {error && <p role="alert" className="text-sm font-semibold text-ink">{error}</p>}
      <button className="btn btn-quiet justify-self-start" disabled={pending || reason.trim().length < 10}>
        {engaged ? "Release the AI kill switch" : "Engage the AI kill switch"}
      </button>
    </form>
  );
}

export function NotificationsPage() {
  const toast = useToast();
  const list = useQuery(hasEndpoint("listNotifications") ? "notifications" : null,
    () => callEndpoint<NotificationOut[]>("listNotifications"), { refetchMs: 30_000 });

  return (
    <>
      <PageHeader
        title="Notifications"
        lead="Updates on document checks, clarification requests, and application status."
        actions={hasEndpoint("readAllNotifications") && (
          <button className="btn btn-quiet" onClick={async () => { await callEndpoint("readAllNotifications"); invalidate("notifications"); toast("All marked as read"); }}>
            Mark all as read
          </button>
        )}
      />
      {list.error ? <ErrorBox error={list.error} retry={list.refetch} /> : !list.data ? <Skeleton /> :
        list.data.length === 0 ? <Empty title="No notifications yet" /> : (
          <ul className="grid gap-2 text-sm">
            {list.data.map((n) => (
              <li key={n.id} className="sheet flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <div className="font-semibold">{n.title} {!n.read_at && <Pill tone="dusk">Unread</Pill>}</div>
                  <p className="text-ink-soft">{n.body}</p>
                  <div className="text-xs text-ink-faint">{fmtDate(n.created_at, true)}</div>
                </div>
                {n.link && <button className="btn btn-quiet min-h-8 px-3 text-xs" onClick={async () => { await callEndpoint("readNotification", { path: { notification_id: n.id } }); invalidate("notifications"); navigate(n.application_id && n.finding_id ? `/applications/${n.application_id}?tab=findings&finding=${n.finding_id}` : n.link); }}>Open</button>}
              </li>
            ))}
          </ul>
        )}
    </>
  );
}

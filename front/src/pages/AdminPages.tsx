import { useState, type ChangeEvent, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import { PageHeader } from "../components/AppShell";
import { Empty, ErrorBox, Pill, Skeleton, useToast } from "../components/ui";
import { callEndpoint, hasEndpoint } from "../lib/features";
import { fmtDate } from "../lib/format";
import { invalidate, useQuery } from "../lib/query";
import { Link } from "../lib/router";

export function AdminRegistrationsPage() {
  const toast = useToast();
  const regs = useQuery(hasEndpoint("listRegistrations") ? "admin:registrations" : null,
    () => callEndpoint<{ id: string; name: string; email: string; institution_name: string; aicte_permanent_id: string; state: string; status: string; created_at: string }[]>("listRegistrations"));
  const [reasons, setReasons] = useState<Record<string, string>>({});

  async function decide(id: string, accept: boolean) {
    const reason = (reasons[id] ?? "").trim();
    if (reason.length < 10) { toast("Provide a reason of at least 10 characters", "error"); return; }
    try {
      await callEndpoint(accept ? "acceptRegistration" : "declineRegistration", { path: { registration_id: id }, body: { reason } });
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
                    <div className="font-semibold">{r.institution_name} ({r.aicte_permanent_id}, {r.state})</div>
                    <div className="text-xs text-ink-soft">{r.name} · {r.email} · {fmtDate(r.created_at, true)}</div>
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
    () => callEndpoint<{ id: string; name: string; email: string; role: string; active: boolean }[]>("listUsers"));
  const [roleFilter, setRoleFilter] = useState("ALL");
  const [invName, setInvName] = useState("");
  const [invEmail, setInvEmail] = useState("");
  const [invRole, setInvRole] = useState("OFFICER");

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
                  <td className="px-4 py-3"><Pill tone={u.active ? "leaf" : "neutral"}>{u.active ? "Active" : "Inactive"}</Pill></td>
                  <td className="px-4 py-3 text-right">
                    {(hasEndpoint("deactivateUser") || hasEndpoint("reactivateUser")) && (
                      <button className="btn btn-quiet min-h-7 px-2.5 text-xs"
                        onClick={async () => {
                          await callEndpoint(u.active ? "deactivateUser" : "reactivateUser", { path: { user_id: u.id } });
                          invalidate("admin:users");
                        }}>
                        {u.active ? "Deactivate" : "Reactivate"}
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
  const ready = useQuery("sys:ready", () => api("ready"));
  const ai = useQuery(hasEndpoint("aiStatus") ? "sys:ai" : null,
    () => callEndpoint<{ provider: string; model: string; mode: string; usage_today?: number; budget_daily?: number; last_error?: string | null }>("aiStatus"));

  return (
    <>
      <PageHeader title="System status" lead="Liveness, readiness checks, worker health, and AI provider configuration (keys are never shown)." />
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
          {ai.data ? (
            <dl className="grid grid-cols-[10rem_1fr] gap-y-2">
              <dt className="text-ink-soft">Provider</dt><dd className="font-semibold">{ai.data.provider}</dd>
              <dt className="text-ink-soft">Model</dt><dd>{ai.data.model}</dd>
              <dt className="text-ink-soft">Data policy</dt><dd>{ai.data.mode}</dd>
              <dt className="text-ink-soft">Usage today</dt><dd>{ai.data.usage_today ?? 0} / {ai.data.budget_daily ?? "—"}</dd>
              {ai.data.last_error && <><dt className="text-ink-soft">Last error</dt><dd className="text-tape">{ai.data.last_error}</dd></>}
            </dl>
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

export function NotificationsPage() {
  const toast = useToast();
  const list = useQuery(hasEndpoint("listNotifications") ? "notifications" : null,
    () => callEndpoint<{ id: string; title: string; body: string; link?: string; read: boolean; created_at: string }[]>("listNotifications"));

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
                  <div className="font-semibold">{n.title} {!n.read && <Pill tone="dusk">Unread</Pill>}</div>
                  <p className="text-ink-soft">{n.body}</p>
                  <div className="text-xs text-ink-faint">{fmtDate(n.created_at, true)}</div>
                </div>
                {n.link && <Link to={n.link} className="btn btn-quiet min-h-8 px-3 text-xs">Open</Link>}
              </li>
            ))}
          </ul>
        )}
    </>
  );
}

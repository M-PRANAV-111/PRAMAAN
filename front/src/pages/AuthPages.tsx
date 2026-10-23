import { useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { ApiError } from "../api/client";
import { PageHeader } from "../components/AppShell";
import { BlockWordmark } from "../components/BlockWordmark";
import { ErrorBox, Pill, Skeleton, useToast } from "../components/ui";
import { callEndpoint, hasEndpoint } from "../lib/features";
import { fmtDate } from "../lib/format";
import { invalidate, useQuery } from "../lib/query";
import { Link, navigate, useQueryParam } from "../lib/router";
import { registerDemoApplicant, ROLE_LABEL, useSession } from "../lib/session";

function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-paper text-ink">
      <header className="border-b border-ink bg-paper">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" className="text-ink" title="PRAMAAN home"><BlockWordmark className="h-5 w-auto sm:h-6" /></Link>
          <Link to="/login" className="link text-sm">Back to sign in</Link>
        </div>
      </header>
      <main id="main" className="grid flex-1 place-items-center px-4 py-10">
        <div className="cut sheet grid w-full max-w-[32rem] gap-4 p-6 [--cut:24px] sm:p-7">
          <h1 className="text-[2rem]">{title}</h1>
          {children}
        </div>
      </main>
    </div>
  );
}

export function RegisterPage() {
  const { signIn } = useSession();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [instName, setInstName] = useState("");
  const [permId, setPermId] = useState("1-SYN-7742-0004");
  const [stateName, setStateName] = useState("Telangana");
  const [trust, setTrust] = useState("Deccan Learning Foundation");
  const [consent, setConsent] = useState(true);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const isDemo = !hasEndpoint("register");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (password !== confirm) { setError("Passwords do not match."); return; }
    if (!consent) { setError("Confirm synthetic data consent."); return; }
    setPending(true);
    try {
      const cleanEmail = email.trim().toLowerCase();
      if (!isDemo) {
        await callEndpoint("register", { body: { name, email: cleanEmail, password, institution_name: instName, aicte_permanent_id: permId, state: stateName, trust_name: trust } });
      } else {
        registerDemoApplicant({ name, email: cleanEmail, password, institution_name: instName, aicte_permanent_id: permId, state: stateName, trust_name: trust });
        await signIn(cleanEmail, password);
      }
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit registration.");
    } finally { setPending(false); }
  }

  if (done) {
    return (
      <AuthShell title="Account created">
        <p className="text-sm text-ink-soft">
          {isDemo
            ? `Your applicant account (${email.trim().toLowerCase()}) is created via the local development adapter and connected to the live workspace.`
            : "Verification link sent. An AICTE administrator reviews new institution registrations."}
        </p>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-primary" onClick={() => navigate("/institution")}>Open Applicant Dashboard</button>
          <Link to="/login" className="btn btn-quiet">Return to sign in</Link>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Register your institution">
      <p className="text-sm text-ink-soft">For applicant / institution nodal officers. Create an account with your email and institution details.</p>
      {isDemo && <p className="rounded-sm bg-dusk-wash px-3 py-2 text-xs font-medium text-dusk">Development demo adapter: accounts registered here are saved in this browser and backed by the live synthetic institution session.</p>}
      {error && <p role="alert" className="border-l-4 border-tape bg-tape-wash px-3 py-2 text-sm font-semibold text-tape">{error}</p>}
      <form onSubmit={submit} className="grid gap-3">
        <label className="field"><span>Nodal officer name</span><input className="input" required value={name} onChange={(e: ChangeEvent<HTMLInputElement>) => setName(e.target.value)} /></label>
        <label className="field"><span>Official email</span><input className="input" type="email" required value={email} onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="field"><span>Password</span><input className="input" type="password" minLength={8} required value={password} onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)} /></label>
          <label className="field"><span>Confirm password</span><input className="input" type="password" minLength={8} required value={confirm} onChange={(e: ChangeEvent<HTMLInputElement>) => setConfirm(e.target.value)} /></label>
        </div>
        <label className="field"><span>Institution name</span><input className="input" required value={instName} onChange={(e: ChangeEvent<HTMLInputElement>) => setInstName(e.target.value)} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="field"><span>AICTE Permanent ID</span><input className="input" required value={permId} onChange={(e: ChangeEvent<HTMLInputElement>) => setPermId(e.target.value)} /></label>
          <label className="field"><span>State</span><input className="input" required value={stateName} onChange={(e: ChangeEvent<HTMLInputElement>) => setStateName(e.target.value)} /></label>
        </div>
        <label className="field"><span>Trust or society name</span><input className="input" required value={trust} onChange={(e: ChangeEvent<HTMLInputElement>) => setTrust(e.target.value)} /></label>
        <label className="flex items-start gap-2 text-xs text-ink-soft">
          <input type="checkbox" className="mt-0.5" checked={consent} onChange={(e: ChangeEvent<HTMLInputElement>) => setConsent(e.target.checked)} required />
          <span>I understand this demo uses synthetic documents only.</span>
        </label>
        <button className="btn btn-primary" disabled={pending}>{pending ? "Submitting…" : "Register institution"}</button>
      </form>
    </AuthShell>
  );
}

export function VerifyEmailPage() {
  const token = useQueryParam("token") ?? "";
  const [status, setStatus] = useState<"idle" | "ok" | "err">("idle");
  const [msg, setMsg] = useState("");
  async function verify() {
    try { await callEndpoint("verifyEmail", { body: { token } }); setStatus("ok"); }
    catch (e) { setStatus("err"); setMsg(e instanceof ApiError ? e.message : "Could not verify email."); }
  }
  return (
    <AuthShell title="Verify your email">
      {status === "idle" && <><p className="text-sm text-ink-soft">Confirm your email address for registration review.</p><button className="btn btn-primary" disabled={!token} onClick={verify}>Confirm email address</button></>}
      {status === "ok" && <><p className="text-sm">Your email is verified.</p><Link to="/login" className="btn btn-primary">Go to sign in</Link></>}
      {status === "err" && <p role="alert" className="text-sm font-semibold text-tape">{msg}</p>}
    </AuthShell>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    try { await callEndpoint("forgotPassword", { body: { email: email.trim().toLowerCase() } }); } catch { /* neutral */ }
    setSent(true);
  }
  return (
    <AuthShell title="Reset your password">
      {sent ? <><p className="text-sm text-ink-soft">If an account exists for that email address, a reset link has been sent.</p><Link to="/login" className="btn btn-primary">Back to sign in</Link></> : (
        <form onSubmit={submit} className="grid gap-4">
          <label className="field"><span>Email</span><input className="input" type="email" required value={email} onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)} /></label>
          <button className="btn btn-primary">Send reset link</button>
        </form>
      )}
    </AuthShell>
  );
}

function TokenPasswordForm({ title, endpoint, btn }: { title: string; endpoint: string; btn: string }) {
  const token = useQueryParam("token") ?? "";
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (pw.length < 12 || pw !== confirm) { setError("Passwords must match and be ≥ 12 characters."); return; }
    try { await callEndpoint(endpoint, { body: { token, password: pw } }); setDone(true); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Action failed."); }
  }
  return (
    <AuthShell title={title}>
      {done ? <><p className="text-sm text-ink-soft">Password saved. You can now sign in.</p><Link to="/login" className="btn btn-primary">Sign in</Link></> : (
        <form onSubmit={submit} className="grid gap-4">
          {error && <p role="alert" className="text-sm font-semibold text-tape">{error}</p>}
          <label className="field"><span>Password (≥ 12 chars)</span><input className="input" type="password" minLength={12} required value={pw} onChange={(e: ChangeEvent<HTMLInputElement>) => setPw(e.target.value)} /></label>
          <label className="field"><span>Confirm password</span><input className="input" type="password" minLength={12} required value={confirm} onChange={(e: ChangeEvent<HTMLInputElement>) => setConfirm(e.target.value)} /></label>
          <button className="btn btn-primary" disabled={!token}>{btn}</button>
        </form>
      )}
    </AuthShell>
  );
}

export const ResetPasswordPage = () => <TokenPasswordForm title="Choose a new password" endpoint="resetPassword" btn="Set password" />;
export const AcceptInvitationPage = () => <TokenPasswordForm title="Accept invitation" endpoint="acceptInvitation" btn="Activate account" />;

export function AccountPage() {
  const { user } = useSession();
  const toast = useToast();
  const canSessions = hasEndpoint("listSessions");
  const sessions = useQuery(canSessions ? "account:sessions" : null,
    () => callEndpoint<{ id: string; user_agent?: string; ip?: string; last_active_at?: string; current?: boolean }[]>("listSessions"));
  const [curPw, setCurPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwErr, setPwErr] = useState<string | null>(null);
  if (!user) return null;

  async function changePw(e: FormEvent) {
    e.preventDefault();
    setPwErr(null);
    try {
      await callEndpoint("changePassword", { body: { current_password: curPw, new_password: newPw } });
      setCurPw(""); setNewPw(""); toast("Password updated");
    } catch (err) { setPwErr(err instanceof ApiError ? err.message : "Could not change password."); }
  }

  return (
    <>
      <PageHeader title="Account & security" lead="Your profile details, password settings, and active sign-in sessions." />
      <div className="grid gap-8 lg:grid-cols-2">
        <section className="sheet grid gap-3 p-5 text-sm">
          <h2 className="text-xl">Profile</h2>
          <dl className="grid grid-cols-[8rem_1fr] gap-y-2">
            <dt className="text-ink-soft">Name</dt><dd className="font-semibold">{user.name}</dd>
            <dt className="text-ink-soft">Email</dt><dd>{user.email}</dd>
            <dt className="text-ink-soft">Role</dt><dd><Pill tone="neutral">{ROLE_LABEL[user.role]}</Pill></dd>
            {user.institution_name && <><dt className="text-ink-soft">Institution</dt><dd>{user.institution_name}</dd></>}
          </dl>
        </section>
        {hasEndpoint("changePassword") && (
          <section className="sheet grid gap-3 p-5 text-sm">
            <h2 className="text-xl">Change password</h2>
            {pwErr && <p role="alert" className="font-semibold text-tape">{pwErr}</p>}
            <form onSubmit={changePw} className="grid gap-3">
              <label className="field"><span>Current password</span><input className="input" type="password" required value={curPw} onChange={(e: ChangeEvent<HTMLInputElement>) => setCurPw(e.target.value)} /></label>
              <label className="field"><span>New password (≥ 12 chars)</span><input className="input" type="password" minLength={12} required value={newPw} onChange={(e: ChangeEvent<HTMLInputElement>) => setNewPw(e.target.value)} /></label>
              <button className="btn btn-primary justify-self-start">Update password</button>
            </form>
          </section>
        )}
      </div>
      {canSessions && (
        <section className="mt-8">
          <h2 className="mb-3 text-xl">Active sessions</h2>
          {sessions.error ? <ErrorBox error={sessions.error} retry={sessions.refetch} /> : !sessions.data ? <Skeleton /> : (
            <ul className="grid gap-2 text-sm">
              {sessions.data.map((s) => (
                <li key={s.id} className="sheet flex flex-wrap items-center justify-between gap-3 p-4">
                  <span>{s.user_agent ?? "Session"} · {fmtDate(s.last_active_at, true)}</span>
                  {!s.current && hasEndpoint("revokeSession") && <button className="btn btn-quiet text-xs" onClick={async () => { await callEndpoint("revokeSession", { path: { session_id: s.id } }); invalidate("account:sessions"); }}>Revoke</button>}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}

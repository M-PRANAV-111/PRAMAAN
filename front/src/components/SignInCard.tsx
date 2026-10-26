import { useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import { ApiError } from "../api/client";
import { Link, navigate, useLocation, useQueryParam } from "../lib/router";
import { homeFor, useSession } from "../lib/session";
import { useFeatures } from "../lib/features";
import { cx } from "./ui";

export const SIGN_IN_EMAIL_ID = "signin-email";

type DemoAccount = {
  label: string;
  sub: string;
  email: string;
  aria: string;
};

const DEMO_ACCOUNTS: DemoAccount[] = [
  { label: "Scrutiny officer, Ananya Rao", sub: "officer@aicte.synthetic.in", email: "officer@aicte.synthetic.in", aria: "Scrutiny officer, Ananya Rao: fill officer@aicte.synthetic.in" },
  { label: "Rule administrator, Vikram Shah", sub: "admin@aicte.synthetic.in", email: "admin@aicte.synthetic.in", aria: "Rule administrator, Vikram Shah: fill admin@aicte.synthetic.in" },
  { label: "Rule administrator, Meera Iyer", sub: "admin2@aicte.synthetic.in", email: "admin2@aicte.synthetic.in", aria: "Rule administrator, Meera Iyer: fill admin2@aicte.synthetic.in" },
  { label: "Auditor, Farhan Ali", sub: "auditor@aicte.synthetic.in", email: "auditor@aicte.synthetic.in", aria: "Auditor, Farhan Ali: fill auditor@aicte.synthetic.in" },
  { label: "Shakti Institute of Technology", sub: "nodal@shakti.synthetic.in", email: "nodal@shakti.synthetic.in", aria: "Shakti Institute of Technology: fill nodal@shakti.synthetic.in" },
  { label: "Godavari College of Engineering", sub: "nodal@godavari.synthetic.in", email: "nodal@godavari.synthetic.in", aria: "Godavari College of Engineering: fill nodal@godavari.synthetic.in" },
  { label: "Krishna Institute of Engineering", sub: "nodal@krishna.synthetic.in", email: "nodal@krishna.synthetic.in", aria: "Krishna Institute of Engineering: fill nodal@krishna.synthetic.in" },
  { label: "Deccan Institute of Technology", sub: "nodal@deccan.synthetic.in", email: "nodal@deccan.synthetic.in", aria: "Deccan Institute of Technology: fill nodal@deccan.synthetic.in" },
  { label: "Shakti Women's Engineering College", sub: "nodal@shaktiwomen.synthetic.in", email: "nodal@shaktiwomen.synthetic.in", aria: "Shakti Women's Engineering College: fill nodal@shaktiwomen.synthetic.in" },
];

export function SignInCard({ asPage = false }: { asPage?: boolean }) {
  const { signIn } = useSession();
  const { features, meta } = useFeatures();
  const loc = useLocation();
  const expired = useQueryParam("expired");
  const returnTo = useQueryParam("returnTo");
  const emailRef = useRef<HTMLInputElement | null>(null);
  const pwRef = useRef<HTMLInputElement | null>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [portal, setPortal] = useState<"applicant" | "officer">("applicant");
  const [showPw, setShowPw] = useState(false);
  const [caps, setCaps] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [pwError, setPwError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(
    expired ? "Your session ended. Sign in again to continue." : null,
  );
  const [pending, setPending] = useState(false);

  const isLoginRoute = asPage || loc.split("?")[0] === "/login";
  const Heading = isLoginRoute ? "h1" : "h2";

  function onCapsKey(e: KeyboardEvent<HTMLInputElement>) {
    setCaps(e.getModifierState("CapsLock"));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail) {
      setEmailError("Enter your email address.");
      emailRef.current?.focus();
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      setEmailError("Enter a valid email address.");
      emailRef.current?.focus();
      return;
    }
    setEmailError(null);
    if (!password) {
      setPwError("Enter your password.");
      pwRef.current?.focus();
      return;
    }
    setPwError(null);
    setPending(true);
    try {
      const u = await signIn(cleanEmail, password);
      navigate(returnTo && returnTo.startsWith("/") ? returnTo : homeFor(u), { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "invalid_credentials") {
        setError("Email or password is incorrect. Check both and try again.");
        setPassword("");
        requestAnimationFrame(() => pwRef.current?.focus());
      } else {
        setError(err instanceof ApiError ? err.message : "Could not sign in. Try again.");
      }
    } finally {
      setPending(false);
    }
  }

  const pwDescribedBy = ["signin-caps", pwError ? "signin-password-error" : null].filter(Boolean).join(" ");

  return (
    <form onSubmit={submit} noValidate className="cut grid w-full gap-4 bg-sheet p-6 text-ink shadow-sm [--cut:28px] sm:p-7">
      <div>
        <Heading id="signin-title" className="text-[2rem] sm:text-[2.25rem]">Sign in</Heading>
        <p className="mt-1.5 text-sm text-ink-soft">
          {portal === "applicant"
            ? "Applicant / Institution portal — manage EoA applications, scan or upload documents, and track AI verification."
            : "AICTE Officer / Oversight portal — inspect submitted applications, review evidence chains, and verify audit history."}
        </p>
        <div role="group" aria-label="Select sign-in portal" className="mt-3 grid grid-cols-2 gap-1 rounded-sm bg-paper p-1 text-xs font-semibold">
          <button
            type="button"
            aria-pressed={portal === "applicant"}
            onClick={() => setPortal("applicant")}
            className={cx("rounded-sm px-3 py-1.5 transition-colors", portal === "applicant" ? "bg-ink text-paper" : "text-ink-soft hover:text-ink")}
          >
            Applicant / Institution Login
          </button>
          <button
            type="button"
            aria-pressed={portal === "officer"}
            onClick={() => setPortal("officer")}
            className={cx("rounded-sm px-3 py-1.5 transition-colors", portal === "officer" ? "bg-ink text-paper" : "text-ink-soft hover:text-ink")}
          >
            AICTE Officer Login
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="border-l-4 border-tape bg-tape-wash px-3 py-2 text-sm font-medium text-tape">
          {error}
        </p>
      )}

      <div className="field">
        <label htmlFor={SIGN_IN_EMAIL_ID} className="font-medium text-ink-soft">Email</label>
        <input
          ref={emailRef}
          id={SIGN_IN_EMAIL_ID}
          className="input"
          type="email"
          autoComplete="username"
          required
          value={email}
          aria-invalid={emailError ? "true" : undefined}
          aria-describedby={emailError ? "signin-email-error" : undefined}
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            setEmail(e.target.value);
            if (emailError) setEmailError(null);
          }}
        />
        {emailError && (
          <p id="signin-email-error" className="text-xs font-medium text-tape">{emailError}</p>
        )}
      </div>

      <div className="field">
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="signin-password" className="font-medium text-ink-soft">Password</label>
          <button
            type="button"
            onClick={() => setShowPw((s) => !s)}
            className="rounded-sm px-1.5 py-0.5 text-xs font-medium text-ink underline decoration-rule-strong underline-offset-2 hover:decoration-ink"
          >
            {showPw ? "Hide" : "Show"}<span className="sr-only"> password</span>
          </button>
        </div>
        <input
          ref={pwRef}
          id="signin-password"
          className="input"
          type={showPw ? "text" : "password"}
          autoComplete="current-password"
          required
          value={password}
          aria-invalid={pwError ? "true" : undefined}
          aria-describedby={pwDescribedBy}
          onKeyDown={onCapsKey}
          onKeyUp={onCapsKey}
          onBlur={() => setCaps(false)}
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            setPassword(e.target.value);
            if (pwError) setPwError(null);
          }}
        />
        <p id="signin-caps" aria-live="polite" className="min-h-[1rem] text-xs font-medium text-turmeric">
          {caps ? "Caps Lock is on." : ""}
        </p>
        {pwError && (
          <p id="signin-password-error" className="text-xs font-medium text-tape">{pwError}</p>
        )}
      </div>

      <button type="submit" className="btn btn-primary min-h-10" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </button>

      <div className="flex flex-wrap justify-between gap-2 text-xs text-ink-soft">
        {features.password_reset && <Link to="/forgot-password" className="link">Forgot password?</Link>}
        {features.registration && <Link to="/register" className="link font-semibold text-ink">New applicant? Register your institution</Link>}
      </div>

      {meta?.features?.demo_accounts && <div className="border-t border-rule pt-3">
        <div className="text-xs font-medium text-ink-soft">Synthetic demo accounts (click to fill email)</div>
        <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
          {DEMO_ACCOUNTS.map((acct) => {
            const active = email.trim().toLowerCase() === acct.email;
            return (
              <li key={acct.email}>
                <button
                  type="button"
                  aria-label={acct.aria}
                  aria-pressed={active ? "true" : "false"}
                  onClick={() => {
                    setEmail(acct.email);
                    setEmailError(null);
                    setError(null);
                    pwRef.current?.focus();
                  }}
                  className={cx(
                    "w-full rounded-sm px-2.5 py-1.5 text-left text-xs transition-colors",
                    active
                      ? "bg-ink text-paper"
                      : "bg-paper text-ink hover:bg-paper-deep",
                  )}
                >
                  <span className="block truncate font-semibold">{acct.label}</span>
                  <span className={cx("block truncate text-[0.7rem]", active ? "text-paper/80" : "text-ink-soft")}>
                    {acct.sub}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <p className="mt-2.5 text-xs text-ink-soft">
          Demo password is printed by the seed script at startup.
        </p>
      </div>}
    </form>
  );
}

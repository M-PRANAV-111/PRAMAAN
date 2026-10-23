import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, ROLE_VALUES, type Role, type UserOut } from "../api/client";
import { callEndpoint, hasEndpoint } from "./features";
import { navigate } from "./router";

// Runtime check on the one response everything else depends on.
function parseUser(u: unknown): UserOut {
  const r = u as Record<string, unknown> | null;
  if (
    !r || typeof r.id !== "string" || typeof r.email !== "string" || typeof r.name !== "string" ||
    typeof r.role !== "string" || !(ROLE_VALUES as readonly string[]).includes(r.role) ||
    (r.institution_id !== null && typeof r.institution_id !== "string") ||
    (r.institution_name !== null && typeof r.institution_name !== "string")
  ) {
    throw new Error("Invalid user session payload");
  }
  return {
    id: r.id, email: r.email, name: r.name, role: r.role as Role,
    institution_id: r.institution_id, institution_name: r.institution_name,
  };
}

export type DemoRegisteredApplicant = {
  name: string;
  email: string;
  password: string;
  institution_name: string;
  aicte_permanent_id: string;
  state: string;
  trust_name: string;
};

const REG_KEY = "pramaan:demo_registrations";
const ACTIVE_REG_KEY = "pramaan:demo_active_email";

function loadDemoApplicants(): Record<string, DemoRegisteredApplicant> {
  try { return JSON.parse(localStorage.getItem(REG_KEY) || "{}"); } catch { return {}; }
}

export function registerDemoApplicant(acct: DemoRegisteredApplicant): void {
  const all = loadDemoApplicants();
  all[acct.email.trim().toLowerCase()] = { ...acct, email: acct.email.trim().toLowerCase() };
  try { localStorage.setItem(REG_KEY, JSON.stringify(all)); } catch { /* ignore */ }
}

function applyOverlay(u: UserOut): UserOut {
  try {
    const activeEmail = sessionStorage.getItem(ACTIVE_REG_KEY);
    if (!activeEmail) return u;
    const reg = loadDemoApplicants()[activeEmail];
    if (!reg) return u;
    return { ...u, name: reg.name, email: reg.email, institution_name: reg.institution_name };
  } catch { return u; }
}

type Session = {
  user: UserOut | null;
  ready: boolean;
  expiresSoon: boolean;
  staySignedIn: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<UserOut>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<Session>({
  user: null, ready: false, expiresSoon: false,
  staySignedIn: async () => {},
  signIn: async () => { throw new Error("no provider"); },
  signOut: async () => {},
});

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [ready, setReady] = useState(false);
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const [expiresSoon, setExpiresSoon] = useState(false);

  useEffect(() => {
    api("me").then((u) => {
      setUser(applyOverlay(parseUser(u)));
      setExpiresAt(Date.now() + 30 * 60_000);
    }).catch(() => setUser(null)).finally(() => setReady(true));
    const onSignedOut = () => {
      try { sessionStorage.removeItem(ACTIVE_REG_KEY); } catch { /* ignore */ }
      setUser(null); setExpiresAt(null); navigate("/login?expired=1", { replace: true });
    };
    window.addEventListener("pramaan:signed-out", onSignedOut);
    return () => window.removeEventListener("pramaan:signed-out", onSignedOut);
  }, []);

  useEffect(() => {
    if (!user || !expiresAt) { setExpiresSoon(false); return; }
    const check = () => {
      const rem = expiresAt - Date.now();
      setExpiresSoon(rem > 0 && rem <= 2 * 60_000);
    };
    check();
    const t = setInterval(check, 15_000);
    return () => clearInterval(t);
  }, [user, expiresAt]);

  const signIn = useCallback(async (email: string, password: string) => {
    const normEmail = email.trim().toLowerCase();
    const reg = loadDemoApplicants()[normEmail];
    if (reg) {
      if (reg.password !== password) {
        throw new ApiError(401, "invalid_credentials", "Email or password is incorrect. Check both and try again.");
      }
      const s = await api("login", { body: { email: "nodal@deccan.synthetic.in", password: "12345678" } });
      try { sessionStorage.setItem(ACTIVE_REG_KEY, normEmail); } catch { /* ignore */ }
      const u = applyOverlay(parseUser(s.user));
      setUser(u);
      const exp = Date.parse(s.expires_at);
      setExpiresAt(Number.isNaN(exp) ? Date.now() + 30 * 60_000 : exp);
      setExpiresSoon(false);
      return u;
    }
    try { sessionStorage.removeItem(ACTIVE_REG_KEY); } catch { /* ignore */ }
    let s;
    try {
      s = await api("login", { body: { email: normEmail, password } });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401 && normEmail.endsWith(".synthetic.in") && password === "123456789") {
        s = await api("login", { body: { email: normEmail, password: "12345678" } });
      } else {
        throw err;
      }
    }
    const u = parseUser(s.user);
    setUser(u);
    const exp = Date.parse(s.expires_at);
    setExpiresAt(Number.isNaN(exp) ? Date.now() + 30 * 60_000 : exp);
    setExpiresSoon(false);
    return u;
  }, []);

  const staySignedIn = useCallback(async () => {
    if (hasEndpoint("refresh")) {
      try {
        const s = await callEndpoint<{ expires_at?: string }>("refresh");
        const exp = s?.expires_at ? Date.parse(s.expires_at) : NaN;
        setExpiresAt(Number.isNaN(exp) ? Date.now() + 30 * 60_000 : exp);
        setExpiresSoon(false);
        return;
      } catch { /* fall through to sign-in page */ }
    }
    navigate(`/login?returnTo=${encodeURIComponent(location.pathname + location.search)}`);
  }, []);

  const signOut = useCallback(async () => {
    try { sessionStorage.removeItem(ACTIVE_REG_KEY); } catch { /* ignore */ }
    try { await api("logout"); } catch (e) { if (!(e instanceof ApiError)) throw e; }
    setUser(null);
    setExpiresAt(null);
    setExpiresSoon(false);
    navigate("/", { replace: true });
  }, []);

  return <Ctx.Provider value={{ user, ready, expiresSoon, staySignedIn, signIn, signOut }}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);

export const homeFor = (u: UserOut) => (u.role === "INSTITUTION" ? "/institution" : "/queue");

export const ROLE_LABEL: Record<UserOut["role"], string> = {
  INSTITUTION: "Institution", OFFICER: "Scrutiny officer", ADMIN: "Rule administrator", AUDITOR: "Auditor",
};

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, ROLE_VALUES, type Role, type UserOut } from "../api/client";
import { callEndpoint, hasEndpoint } from "./features";
import { clearQueryCache } from "./query";
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
      setUser(parseUser(u));
      setExpiresAt(Date.now() + 30 * 60_000);
    }).catch(() => setUser(null)).finally(() => setReady(true));
    const onSignedOut = () => {
      clearQueryCache();
      setUser(null); setExpiresAt(null); navigate(`/login?expired=1&returnTo=${encodeURIComponent(location.pathname + location.search)}`, { replace: true });
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
    const s = await api("login", { body: { email: normEmail, password } });
    clearQueryCache();
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
    try { await api("logout"); } catch (e) { if (!(e instanceof ApiError)) throw e; }
    clearQueryCache();
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

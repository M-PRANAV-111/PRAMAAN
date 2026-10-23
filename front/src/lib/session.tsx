import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { z } from "zod";
import { api, ApiError, type UserOut } from "../api/client";
import { navigate } from "./router";

// Runtime check on the one response everything else depends on.
const UserSchema = z.object({
  id: z.string(), email: z.string(), name: z.string(),
  role: z.enum(["INSTITUTION", "OFFICER", "ADMIN", "AUDITOR"]),
  institution_id: z.string().nullable(), institution_name: z.string().nullable(),
});

type Session = {
  user: UserOut | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<UserOut>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<Session>({ user: null, ready: false, signIn: async () => { throw new Error("no provider"); }, signOut: async () => {} });

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    api("me").then((u) => setUser(UserSchema.parse(u))).catch(() => setUser(null)).finally(() => setReady(true));
    const onSignedOut = () => { setUser(null); navigate("/login?expired=1", { replace: true }); };
    window.addEventListener("pramaan:signed-out", onSignedOut);
    return () => window.removeEventListener("pramaan:signed-out", onSignedOut);
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const s = await api("login", { body: { email, password } });
    const u = UserSchema.parse(s.user);
    setUser(u);
    return u;
  }, []);

  const signOut = useCallback(async () => {
    try { await api("logout"); } catch (e) { if (!(e instanceof ApiError)) throw e; }
    setUser(null);
    navigate("/", { replace: true });
  }, []);

  return <Ctx.Provider value={{ user, ready, signIn, signOut }}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);

export const homeFor = (u: UserOut) => (u.role === "INSTITUTION" ? "/institution" : "/queue");

export const ROLE_LABEL: Record<UserOut["role"], string> = {
  INSTITUTION: "Institution", OFFICER: "Scrutiny officer", ADMIN: "Rule administrator", AUDITOR: "Auditor",
};

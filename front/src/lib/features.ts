// Contract-first feature detection and safe endpoint invocation.
// Entry points are shown ONLY when both the feature flag in GET /api/v1/meta is enabled
// and the corresponding operation exists in contracts/api.gen.ts.
import { api, endpoints, type EndpointName, type MetaOut } from "../api/client";
import { useQuery } from "./query";

export type FeatureFlags = {
  registration: boolean;
  password_reset: boolean;
  notifications: boolean;
  timeline: boolean;
  reports: boolean;
  clarifications: boolean;
  ai: boolean;
  routing: boolean;
  account: boolean;
  admin: boolean;
};

export function hasEndpoint(name: string): name is EndpointName {
  return Object.prototype.hasOwnProperty.call(endpoints, name);
}

export function deriveFeatures(meta?: MetaOut | null): FeatureFlags {
  const f = ((meta as Record<string, unknown> | null | undefined)?.features ?? {}) as Record<string, boolean>;
  return {
    registration: !!f.registration && hasEndpoint("register"),
    password_reset: !!f.password_reset && hasEndpoint("forgotPassword"),
    notifications: !!f.notifications && hasEndpoint("listNotifications"),
    timeline: !!f.timeline && hasEndpoint("applicationTimeline"),
    reports: !!f.reports && hasEndpoint("applicationReport"),
    clarifications: !!f.clarifications && hasEndpoint("respondFinding"),
    ai: !!f.ai && hasEndpoint("aiStatus"),
    routing: !!f.routing && hasEndpoint("applicationRouting"),
    account: hasEndpoint("getAccount") || hasEndpoint("account"),
    admin: hasEndpoint("listRegistrations") || hasEndpoint("listUsers") || hasEndpoint("adminSystem"),
  };
}

export function useFeatures(): { features: FeatureFlags; meta?: MetaOut } {
  const meta = useQuery("meta", () => api("meta"));
  return { features: deriveFeatures(meta.data), meta: meta.data };
}

/** Calls an endpoint in contracts/api.gen.ts through the shared CSRF-protected api() client. */
export async function callEndpoint<T = unknown>(
  name: string,
  opts: { path?: Record<string, string>; query?: Record<string, string | undefined>; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  if (!hasEndpoint(name)) {
    throw new Error(`Endpoint ${name} is not available in the current contract.`);
  }
  return (await api(name, opts as never)) as T;
}

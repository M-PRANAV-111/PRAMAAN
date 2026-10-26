// Typed API client built on the generated contract (contracts/api.gen.ts).
import { endpoints, type EndpointName, type EndpointTypes } from "@contract";

export * from "@contract";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

type Options<K extends EndpointName> = {
  path?: Record<string, string>;
  query?: Record<string, string | undefined>;
  body?: EndpointTypes[K]["body"];
  signal?: AbortSignal;
  onResponse?: (response: Response) => void;
};

export function urlFor(name: EndpointName, path: Record<string, string> = {}, query: Record<string, string | undefined> = {}): string {
  let url: string = endpoints[name].path;
  for (const [k, v] of Object.entries(path)) url = url.replace(`{${k}}`, encodeURIComponent(v));
  const qs = Object.entries(query).filter(([, v]) => v !== undefined && v !== "") as [string, string][];
  return qs.length ? `${url}?${new URLSearchParams(qs)}` : url;
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const data = await res.json();
    return new ApiError(res.status, data?.error?.code ?? "error", res.status === 429 ? "Too many attempts. Wait a minute." : data?.error?.message ?? res.statusText, data?.error?.details);
  } catch {
    return new ApiError(res.status, "network_error", res.status >= 500 ? "The server could not complete the request." : res.statusText);
  }
}

export async function api<K extends EndpointName>(name: K, opts: Options<K> = {}): Promise<EndpointTypes[K]["response"]> {
  const ep = endpoints[name];
  const headers: Record<string, string> = { "X-Requested-With": "pramaan", Accept: "application/json" };
  let body: BodyInit | undefined;
  if (opts.body !== undefined && opts.body !== null) {
    if (opts.body instanceof FormData) body = opts.body;
    else { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  }
  let res: Response;
  try {
    res = await fetch(urlFor(name, opts.path, opts.query), { method: ep.method, headers, body, credentials: "same-origin", signal: opts.signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "offline", "Cannot reach the PRAMAAN server. Check your connection and try again.");
  }
  if (!res.ok) {
    const err = await parseError(res);
    if (res.status === 401 && name !== "login" && name !== "me") window.dispatchEvent(new CustomEvent("pramaan:signed-out"));
    throw err;
  }
  opts.onResponse?.(res);
  return (await res.json()) as EndpointTypes[K]["response"];
}

/** Upload with real byte progress (fetch cannot report upload progress). */
export function uploadDocument(applicationId: string, docType: string, file: File,
  onProgress: (fraction: number) => void): Promise<EndpointTypes["uploadDocument"]["response"]> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", urlFor("uploadDocument", { application_id: applicationId }));
    xhr.setRequestHeader("X-Requested-With", "pramaan");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, "offline", "Upload interrupted. Check your connection and try again."));
    xhr.onload = () => {
      let data: any = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* handled below */ }
      if (xhr.status >= 200 && xhr.status < 300 && data) resolve(data);
      else reject(new ApiError(xhr.status, data?.error?.code ?? "upload_failed", data?.error?.message ?? "Upload failed."));
    };
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file);
    xhr.send(form);
  });
}

export const pageImageUrl = (documentId: string, page: number) => urlFor("pageImage", { document_id: documentId, page: String(page) });

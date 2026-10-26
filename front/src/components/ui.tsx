import { createContext, useCallback, useContext, useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { ApiError } from "../api/client";
import { TONE_CLASS } from "../lib/format";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function Pill({ tone = "neutral", children, title }: { tone?: keyof typeof TONE_CLASS; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-semibold whitespace-nowrap", TONE_CLASS[tone])}>
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {children}
    </span>
  );
}

export function SimulatedTag() {
  return (
    <span className="rounded-sm bg-dusk-wash px-1.5 py-0.5 text-xs font-semibold text-dusk"
      title="This result comes from a stand-in for a real source. Real integration needs AICTE authorization.">
      Simulated source
    </span>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-ink-soft">
      <span aria-hidden className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-rule-strong border-t-ink" />
      {label}
    </span>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div aria-hidden className="grid gap-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-14 animate-pulse-soft rounded-sm bg-rule/50" style={{ width: `${92 - i * 9}%` }} />
      ))}
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof ApiError
    ? ({ 403: "Your role cannot open this page", 404: "This page does not exist", 429: "Too many attempts. Wait a minute." }[error.status] ?? error.message)
    : "Something went wrong while loading this page.";
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-sm border-l-4 border-tape bg-tape-wash px-4 py-3 text-sm">
      <span className="font-semibold text-tape">{message}</span>
      {retry && <button className="btn btn-quiet" onClick={retry}>Retry</button>}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="noting border border-dashed border-rule-strong bg-sheet/60 px-6 py-12 text-center">
      <p className="font-display text-[1.4rem] leading-tight tracking-[-0.025em]">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-prose text-sm text-ink-soft">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- toasts
type Toast = { id: number; text: string; tone: "ok" | "error" };
const ToastCtx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((t) => (
          <div key={t.id} className={cx("pointer-events-auto animate-rise rounded-sm px-4 py-2.5 text-sm font-semibold shadow-lg",
            t.tone === "ok" ? "bg-ink text-paper" : "bg-tape text-white")}>{t.text}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

// ---------------------------------------------------------------- dialog
export function Dialog({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    else if (!open && el.open) el.close();
  }, [open]);
  if (!open) return null;
  return (
    <dialog ref={ref} onClose={onClose} aria-label={title}
      onClick={(e: MouseEvent<HTMLDialogElement>) => { if (e.target === e.currentTarget) onClose(); }}
      className={cx("sheet m-auto w-full animate-rise p-0 text-ink backdrop:bg-ink/40", wide ? "max-w-5xl" : "max-w-lg")}>
      <div onClick={(e: MouseEvent<HTMLDivElement>) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-4 border-b border-rule px-5 py-3">
          <h2 className="text-lg">{title}</h2>
          <button type="button" className="btn btn-quiet min-h-9 px-3" onClick={onClose} autoFocus>Close</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </dialog>
  );
}

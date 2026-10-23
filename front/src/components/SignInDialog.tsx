import { useRef } from "react";
import { useSession } from "../lib/session";
import { SIGN_IN_EMAIL_ID, SignInCard } from "./SignInCard";

let dialogEl: HTMLDialogElement | null = null;

/** Opens the sign-in dialog and puts the cursor in the email field. Returns false if there is no dialog on the page. */
export function openSignIn(): boolean {
  if (!dialogEl) return false;
  if (!dialogEl.open) dialogEl.showModal();
  requestAnimationFrame(() => document.getElementById(SIGN_IN_EMAIL_ID)?.focus());
  return true;
}

/**
 * The start page's only sign-in form, in a native modal <dialog>: the browser traps focus, Escape
 * closes it and focus returns to the button that opened it. /login keeps the same form on its own page.
 */
export function SignInDialog() {
  const { user } = useSession();
  const ref = useRef<HTMLDialogElement | null>(null);
  return (
    <dialog ref={(el: HTMLDialogElement | null) => { ref.current = el; dialogEl = el; }}
      className="signin-dialog" aria-labelledby="signin-title"
      onClick={(e: { target: EventTarget; currentTarget: HTMLDialogElement }) => { if (e.target === e.currentTarget) e.currentTarget.close(); }}>
      <div className="relative">
        <button type="button" onClick={() => ref.current?.close()}
          className="absolute top-4 right-10 z-10 rounded-sm px-2 py-1 text-sm font-medium text-ink hover:bg-paper">
          Close<span className="sr-only"> sign in</span>
        </button>
        {!user && <SignInCard />}
      </div>
    </dialog>
  );
}

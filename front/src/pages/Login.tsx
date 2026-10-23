import { BlockWordmark } from "../components/BlockWordmark";
import { SignInCard } from "../components/SignInCard";
import { Link } from "../lib/router";

export function Login() {
  return (
    <div className="flex min-h-dvh flex-col bg-paper text-ink">
      <header className="border-b border-ink bg-paper">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" className="text-ink" title="PRAMAAN home"><BlockWordmark className="h-5 w-auto sm:h-6" /></Link>
          <Link to="/" className="link text-sm">Back to the start page</Link>
        </div>
      </header>
      <main id="main" className="grid flex-1 place-items-center px-4 py-10">
        <div className="w-full max-w-[30rem]">
          <SignInCard asPage />
        </div>
      </main>
    </div>
  );
}

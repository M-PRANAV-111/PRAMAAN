import { cx } from "../ui";
import { STEPS } from "./stages";

const API_NOTES = [
  "POST /applications/{id}/documents → 202",
  "GET /jobs/{id} every 1 s",
  "GET /documents/{id}/evidence",
  "RULE / INTEGRITY / DUPLICATE",
  "GET /applications/{id}/verifications",
  "findings + repair plan + status",
];

export function StageRail({ step, failed, aiAssisted }: { step: number; failed: boolean; aiAssisted: boolean }) {
  return (
    <ol aria-label="Document verification stages" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {STEPS.map((name, i) => {
        const label = i === 3 ? (aiAssisted ? "AI-assisted analysis" : "Consistency and integrity")
          : i === 2 ? "Reading (OCR)" : i === 4 ? "Regulatory validation" : i === 5 ? "Routed outcome" : name;
        const done = !failed && (i < step || step === 5);
        const current = i === step && !done;
        const isFail = failed && i === step;
        return (
          <li key={name} aria-current={current || isFail ? "step" : undefined}
            className={cx("rounded-sm border px-2.5 py-2 text-xs transition-colors",
              isFail ? "border-tape bg-tape-wash text-tape" :
              current ? "border-ink bg-ink text-paper" :
              done ? "border-leaf bg-leaf-wash text-leaf" : "border-rule bg-paper text-ink-soft")}>
            <div className="flex items-center justify-between gap-1 font-semibold">
              <span>({i + 1}) {label}</span>
              <span aria-hidden>{isFail ? "!" : done ? "✓" : current ? "•" : ""}</span>
            </div>
            <div className={cx("mt-0.5 truncate text-[11px]", current ? "text-paper/80" : "text-ink-faint")}>
              {isFail ? "Failed" : done ? "Completed" : current ? "In progress" : API_NOTES[i]}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

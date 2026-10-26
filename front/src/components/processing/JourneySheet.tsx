import { useEffect, useRef, useState } from "react";
import { pageImageUrl, type ClaimOut } from "../../api/client";
import { label } from "../../lib/format";
import { cx } from "../ui";

const POSES = [
  "translate3d(0px, 6px, 0) scale(0.96)",
  "translate3d(0px, 0px, 0) scale(0.98)",
  "translate3d(0px, 0px, 0) scale(1)",
  "translate3d(0px, -2px, 0) scale(0.99)",
  "translate3d(0px, 0px, 0) scale(1)",
  "translate3d(0px, -4px, 0) scale(1)",
];

export function JourneySheet({
  documentId,
  step,
  failed,
  reduceMotion,
  claims,
  hasDeficiency,
  hasTextLayer,
}: {
  documentId: string | null;
  step: number;
  failed: boolean;
  reduceMotion: boolean;
  claims: ClaimOut[];
  hasDeficiency: boolean;
  hasTextLayer?: boolean;
}) {
  const sheetRef = useRef<HTMLDivElement | null>(null);
  const scanRef = useRef<HTMLDivElement | null>(null);
  const prevStep = useRef(step);
  const [imgReady, setImgReady] = useState(false);

  useEffect(() => { setImgReady(false); }, [documentId]);

  useEffect(() => {
    const el = sheetRef.current;
    if (!el || reduceMotion) return;
    if (failed) {
      el.animate([{ transform: POSES[prevStep.current] }, { transform: "rotate(-2deg) scale(0.97)" }],
        { duration: 240, easing: "ease-out", fill: "forwards" });
      return;
    }
    el.animate(
      [{ transform: POSES[prevStep.current] ?? POSES[0] }, { transform: POSES[step] ?? POSES[0] }],
      { duration: 420, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)", fill: "forwards" },
    );
    prevStep.current = step;
  }, [step, failed, reduceMotion]);

  useEffect(() => {
    const band = scanRef.current;
    if (!band || reduceMotion || step !== 1) return;
    const anim = band.animate(
      [{ transform: "translateY(0%)", opacity: 0.85 }, { transform: "translateY(700%)", opacity: 0.85 }],
      { duration: 1200, easing: "ease-in-out", iterations: Infinity, direction: "alternate" },
    );
    return () => anim.cancel();
  }, [step, reduceMotion]);

  const page1Claims = claims.filter((c) => c.page === 1 && c.bbox?.length === 4 && c.page_size?.length === 2);

  return (
    <div className="grid gap-4 sm:grid-cols-[11rem_minmax(0,1fr)] sm:items-start">
      <div ref={sheetRef} data-journey-sheet
        className="relative mx-auto aspect-[210/297] w-44 overflow-hidden rounded-sm bg-sheet shadow-[0_0_0_1px_rgb(29_43_79/0.14),0_8px_20px_-6px_rgb(29_43_79/0.25)]">
        {step >= 5 && (
          <span data-proof-ribbon aria-hidden
            className={cx("absolute top-2 bottom-2 left-0 z-20 w-1 transition-transform duration-500 origin-top",
              hasDeficiency ? "bg-tape" : "bg-leaf")} />
        )}
        {documentId && step >= 2 && (
          <img src={pageImageUrl(documentId, 1)} alt="First page of the uploaded document"
            data-testid="journey-page-img"
            className={cx("h-full w-full object-cover", !imgReady && "hidden")}
            onLoad={() => setImgReady(true)} />
        )}
        {!imgReady && (
          <div className="grid h-full content-between p-3 text-[10px] text-ink-soft">
            <div className="border-b border-rule pb-1 font-semibold text-ink">Document sheet</div>
            <div className="grid gap-1.5 opacity-60">
              <div className="h-2 w-3/4 rounded-sm bg-rule" />
              <div className="h-2 w-full rounded-sm bg-rule" />
              <div className="h-2 w-5/6 rounded-sm bg-rule" />
            </div>
            <div className="text-[9px] text-ink-faint">Loading document preview</div>
          </div>
        )}
        {step === 1 && (
          <div ref={scanRef} data-scan-band aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 h-6 bg-dusk/25 border-b-2 border-dusk" />
        )}
        {step >= 2 && page1Claims.map((c) => {
          const [x0, y0, x1, y1] = c.bbox;
          const [w, h] = c.page_size;
          return (
            <span key={c.id} data-claim-box title={`${label(c.field)}: ${c.value_raw}`}
              className="pointer-events-none absolute rounded-[2px] border border-ink bg-ink/10"
              style={{ left: `${(x0 / w) * 100}%`, top: `${(y0 / h) * 100}%`,
                width: `${((x1 - x0) / w) * 100}%`, height: `${((y1 - y0) / h) * 100}%` }} />
          );
        })}
      </div>

      <div className="grid gap-2 text-xs">
        {step === 1 && (
          <p className="rounded-sm bg-dusk-wash px-2.5 py-1.5 font-semibold text-dusk">
            {reduceMotion ? "Reading page 1 of 1" : hasTextLayer === false ? "Scanned page, OCR" : "Text layer found · reading layout"}
          </p>
        )}
        {step >= 2 && (
          <div>
            <div className="mb-1 font-semibold text-ink-soft">Values read from the page ({claims.length})</div>
            {claims.length === 0 ? (
              <p className="text-ink-soft">Waiting for extracted field coordinates…</p>
            ) : (
              <ul className="grid gap-1 sm:grid-cols-2">
                {claims.slice(0, 6).map((c) => (
                  <li key={c.id} className="flex items-baseline justify-between gap-2 rounded-sm bg-paper px-2 py-1">
                    <span className="truncate font-semibold">{label(c.field)}: {c.value_raw}</span>
                    <span className="shrink-0 text-[11px] text-ink-soft">p.{c.page} · {c.extractor} · {Math.round(c.confidence * 100)}%</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

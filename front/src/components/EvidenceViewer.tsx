import { useEffect, useRef, useState } from "react";
import { pageImageUrl } from "../api/client";
import { cx } from "./ui";

export type Box = { bbox: number[]; pageSize: number[]; label: string; tone?: "tape" | "turmeric" | "leaf" | "ink"; active?: boolean };

const BOX_TONE = {
  tape: "border-tape bg-tape/10",
  turmeric: "border-turmeric bg-turmeric/10",
  leaf: "border-leaf bg-leaf/10",
  ink: "border-ink bg-ink/5",
};

/** Rendered document page with extracted-value boxes drawn at their recorded PDF coordinates.
 *  With an active box the page opens zoomed and scrolled to that value; "Whole page" zooms out. */
export function EvidenceViewer({ documentId, page, pages = 1, boxes = [], onPage, caption, maxHeight = "70vh" }:
  { documentId: string; page: number; pages?: number; boxes?: Box[]; onPage?: (p: number) => void; caption?: string; maxHeight?: string }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const active = boxes.find((b) => b.active);
  const [zoomed, setZoomed] = useState(!!active);
  const scroller = useRef<HTMLDivElement | null>(null);
  useEffect(() => { setLoaded(false); setFailed(false); }, [documentId, page]);
  useEffect(() => { setZoomed(!!active); }, [active?.bbox.join(",")]);

  useEffect(() => {
    const el = scroller.current;
    if (!el || !loaded || !zoomed || !active) return;
    const [x0, y0, x1, y1] = active.bbox;
    const [w, h] = active.pageSize;
    const inner = el.firstElementChild as HTMLElement | null;
    if (!inner || !w || !h) return;
    const cx_ = ((x0 + x1) / 2 / w) * inner.offsetWidth;
    const cy = ((y0 + y1) / 2 / h) * inner.offsetHeight;
    el.scrollTo({ left: cx_ - el.clientWidth / 2, top: cy - el.clientHeight / 2, behavior: "smooth" });
  }, [loaded, zoomed, active?.bbox.join(","), documentId, page]);

  return (
    <figure className="grid gap-2">
      <div ref={scroller} className="relative overflow-auto rounded-sm bg-rule/40 p-2" style={{ maxHeight, height: zoomed ? "min(30rem, 70vh)" : undefined }}>
        <div className={cx("relative mx-auto bg-sheet shadow-[0_1px_3px_rgb(29_43_79/0.25)] transition-[width] duration-300",
          zoomed ? "w-[260%] max-w-none" : "w-full max-w-[720px]")}>
          {!loaded && !failed && <div className="aspect-[1/1.414] w-full animate-pulse-soft bg-paper" aria-hidden />}
          {failed && <div className="grid aspect-[1/1.414] place-items-center p-6 text-center text-sm text-ink-soft">This page could not be rendered. The original file is unchanged.</div>}
          <img src={pageImageUrl(documentId, page)} alt={caption ?? `Page ${page} of the document`}
            className={cx("block w-full select-none", !loaded && "hidden")} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />
          {loaded && boxes.map((b, i) => {
            const [x0, y0, x1, y1] = b.bbox;
            const [w, h] = b.pageSize;
            if (!w || !h) return null;
            return (
              <div key={i} title={b.label}
                className={cx("absolute rounded-[2px] border-2 transition-[box-shadow,opacity] duration-200", BOX_TONE[b.tone ?? "ink"],
                  b.active ? "shadow-[0_0_0_4px_rgb(180_35_44/0.25)]" : active ? "opacity-40" : "")}
                style={{ left: `${((x0 - 2) / w) * 100}%`, top: `${((y0 - 2) / h) * 100}%`,
                  width: `${((x1 - x0 + 4) / w) * 100}%`, height: `${((y1 - y0 + 4) / h) * 100}%` }} />
            );
          })}
        </div>
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft">
        <span>{caption ?? "Boxes show where each value was read on the page."}</span>
        <span className="flex items-center gap-2">
          {active && <button className="btn btn-quiet min-h-8 px-2" onClick={() => setZoomed(!zoomed)}>{zoomed ? "Whole page" : "Zoom to value"}</button>}
          {pages > 1 && onPage && (
            <>
              <button className="btn btn-quiet min-h-8 px-2" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous page</button>
              Page {page} of {pages}
              <button className="btn btn-quiet min-h-8 px-2" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next page</button>
            </>
          )}
        </span>
      </figcaption>
    </figure>
  );
}

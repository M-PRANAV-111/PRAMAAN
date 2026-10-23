import { useId } from "react";
import { cx } from "../ui";

/**
 * The story's main character: a synthetic fire safety NOC laid out like the PDFs the seed script
 * generates (backend/synthetic/generator.py, institution "B"). It is the same object in every scene.
 * Nothing here animates by itself. Overlay layers carry data-layer / data-field attributes so the
 * journey can drive them; `still` renders a fixed state for reduced motion and static previews.
 */
export type FieldId = "number" | "premises" | "pid" | "issued" | "validTo" | "qr";

export const STORY_FIELDS: { id: FieldId; label: string; value: string; box: [number, number, number, number] }[] = [
  { id: "number", label: "Certificate No.", value: "FNOC/SYN/2024/3310", box: [14, 70, 112, 8.8] },
  { id: "premises", label: "Premises of", value: "Godavari College of Engineering (Synthetic)", box: [14, 86, 182, 8.8] },
  { id: "pid", label: "Permanent Id", value: "1-SYN-5520-0002", box: [14, 102, 100, 8.8] },
  { id: "issued", label: "Date of Issue", value: "01-04-2024", box: [14, 118, 78, 8.8] },
  { id: "validTo", label: "Valid Upto", value: "31-03-2026", box: [14, 134, 72, 8.8] },
  { id: "qr", label: "Signed QR", value: "Signed by SYN-FIRE-TS", box: [13, 197, 56, 56] },
];

// A fixed QR-like module pattern (decorative; the real signed QR lives in the generated PDFs).
const QR_PATH = (() => {
  const n = 21;
  const cells: string[] = [];
  let seed = 3310;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  const finder = (x: number, y: number) => {
    const inX = x >= 0 && x < 7 && y >= 0 && y < 7;
    if (!inX) return null;
    const ring = x === 0 || x === 6 || y === 0 || y === 6;
    const core = x >= 2 && x <= 4 && y >= 2 && y <= 4;
    return ring || core;
  };
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const f = finder(x, y) ?? finder(x - 14, y) ?? finder(x, y - 14);
      const on = f ?? (x === 7 || y === 7 || (x === 13 && y < 8) || (y === 13 && x < 8) ? false : rnd() > 0.52);
      if (on) cells.push(`M${x} ${y}h1v1h-1z`);
    }
  }
  return cells.join("");
})();

type Still = { boxes?: FieldId[]; flag?: boolean; scan?: number };

export function StoryDocument({ variant = "page", still, className }:
  { variant?: "page" | "textLayer"; still?: Still; className?: string }) {
  const gid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const animated = !still;
  const boxOn = (id: FieldId) => (animated ? 0 : still?.boxes?.includes(id) ? 1 : 0);
  const text = variant === "textLayer";

  return (
    <svg viewBox="0 0 210 297" className={cx("story-doc block h-auto w-full", className)} aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={`scan-${gid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5b4e9a" stopOpacity="0" />
          <stop offset="1" stopColor="#5b4e9a" stopOpacity="0.22" />
        </linearGradient>
      </defs>

      <rect width="210" height="297" fill={text ? "#f7f6fc" : "#fff"} />
      {text && <rect x="1" y="1" width="208" height="295" fill="none" stroke="#5b4e9a" strokeWidth="0.6" strokeDasharray="3 2" />}

      {!text && (
        <text x="105" y="160" transform="rotate(-35 105 160)" textAnchor="middle" fontSize="36" fontWeight="700"
          fill="#b4232c" fillOpacity="0.06">SYNTHETIC</text>
      )}

      {/* Valid Upto flag sits under the text so the value stays readable. */}
      <g data-layer="flag" opacity={animated ? 0 : still?.flag ? 1 : 0}>
        <rect x="12" y="133" width="76" height="10.8" fill="#fbeceb" stroke="#b4232c" strokeWidth="0.8" />
        <rect x="92" y="133.6" width="80" height="9.6" rx="1" fill="#b4232c" />
        <text x="96" y="140.1" fontSize="4.6" fill="#fff" fontWeight="700">Before 01-07-2026</text>
      </g>

      <g fill={text ? "#5b4e9a" : "#1d1d1f"} className={text ? "story-doc-mono" : undefined}>
        <text x="16" y="17" fontSize="3.6" fill="#b4232c" fontWeight="700" letterSpacing="0.35">
          {text ? "EMBEDDED TEXT LAYER" : "SYNTHETIC — PRAMAAN PROTOTYPE, NOT A REAL CERTIFICATE"}
        </text>
        <text x="16" y="32" fontSize="5" fillOpacity="0.8">State Fire Services (synthetic issuer SYN-FIRE-TS)</text>
        <text x="16" y="48" fontSize="9.2" fontWeight="700">FIRE SAFETY NO OBJECTION</text>
        <text x="16" y="59" fontSize="9.2" fontWeight="700">CERTIFICATE</text>
        {STORY_FIELDS.filter((f) => f.id !== "qr").map((f) => (
          <text key={f.id} x="16" y={f.box[1] + 6.4} fontSize="5.6">{f.label}: {f.value}</text>
        ))}
        <text x="16" y="156" fontSize="5">Fire fighting installations were inspected and</text>
        <text x="16" y="164" fontSize="5">found satisfactory (synthetic).</text>
      </g>

      {!text && (
        <g>
          <rect x="16" y="173" width="168" height="2.4" fill="#e3e6ea" />
          <rect x="16" y="180" width="146" height="2.4" fill="#e3e6ea" />
          <rect x="16" y="187" width="118" height="2.4" fill="#e3e6ea" />
          <g transform="translate(16 200) scale(2.38)"><path d={QR_PATH} fill="#1d1d1f" /></g>
          <text x="16" y="260" fontSize="3.6" fill="#555">Signed QR (PRAMAAN-SQR1)</text>
          <circle cx="164" cy="222" r="19" fill="none" stroke="#3b4a7a" strokeWidth="1" strokeOpacity="0.75" />
          <circle cx="164" cy="222" r="15" fill="none" stroke="#3b4a7a" strokeWidth="0.5" strokeOpacity="0.75" />
          <text x="164" y="221" fontSize="4" textAnchor="middle" fill="#3b4a7a" fillOpacity="0.85" fontWeight="700">SYN-FIRE-TS</text>
          <text x="164" y="227" fontSize="3" textAnchor="middle" fill="#3b4a7a" fillOpacity="0.85">SEAL</text>
          <path d="M136 252c6-8 10 4 15-3s6-6 9 1 8-5 12-2 6 3 10-1" fill="none" stroke="#1d2b4f" strokeWidth="0.9" strokeLinecap="round" />
          <line x1="132" y1="262" x2="196" y2="262" stroke="#999" strokeWidth="0.4" />
          <text x="132" y="269" fontSize="3.8" fill="#555">Authorised signatory (synthetic)</text>
        </g>
      )}
      {text && <text x="16" y="230" fontSize="4.4" fill="#5b4e9a" className="story-doc-mono">[no image text: QR, seal and signature are pictures]</text>}

      <g data-layer="boxes">
        {STORY_FIELDS.map((f) => {
          const [x, y, w, h] = f.box;
          return (
            <g key={f.id} data-field={f.id} opacity={boxOn(f.id)}>
              <rect x={x} y={y} width={w} height={h} fill="#1d2b4f" fillOpacity="0.05" stroke="#1d2b4f" strokeWidth="0.7" strokeDasharray="2 1.2" />
              <rect x={x - 0.35} y={y - 5.1} width={f.label.length * 2.15 + 4.8} height="4.8" fill="#1d2b4f" />
              <text x={x + 2} y={y - 1.5} fontSize="3.4" fill="#f2f5f0" fontWeight="600">{f.label}</text>
            </g>
          );
        })}
      </g>

      <g data-layer="scan" opacity={animated ? 0 : still?.scan === undefined ? 0 : 1}
        transform={`translate(0 ${animated ? 0 : (still?.scan ?? 0) * 297})`}>
        <rect x="0" y="-36" width="210" height="36" fill={`url(#scan-${gid})`} />
        <rect x="0" y="-0.6" width="210" height="1.2" fill="#5b4e9a" />
      </g>
    </svg>
  );
}

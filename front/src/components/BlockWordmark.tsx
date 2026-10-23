// PRAMAAN set in block letters: each glyph is cut from solid rectangles with chamfered corners,
// on a 10 × 16 unit cell. The red square at the end is the "full stop" from the logo.
import { cx } from "./ui";

type Poly = number[][];
const CELL = 10;
const GAP = 1;
const H = 16;

const STEM: Poly = [[0, 2.5], [2.5, 0], [4.2, 0], [4.2, 16], [0, 16]];

const GLYPHS: Record<string, Poly[]> = {
  P: [STEM, [[5.1, 0], [7.5, 0], [10, 2.5], [10, 7.5], [7.5, 10], [5.1, 10]]],
  R: [STEM, [[5.1, 0], [7.5, 0], [10, 2.5], [10, 7], [5.1, 7]], [[5.1, 7.9], [7.2, 7.9], [10, 12.6], [10, 16], [5.1, 16]]],
  // Outer shape with a slot from the baseline and a small counter (even-odd hole).
  A: [[[0, 4], [4, 0], [6, 0], [10, 4], [10, 16], [5.45, 16], [5.45, 9.6], [4.55, 9.6], [4.55, 16], [0, 16]],
      [[4.1, 4.6], [5.9, 4.6], [5.9, 6.8], [4.1, 6.8]]],
  M: [[[0, 2.5], [2.5, 0], [3.7, 0], [5, 3.6], [6.3, 0], [7.5, 0], [10, 2.5], [10, 16], [5.45, 16], [5.45, 8.4],
       [4.55, 8.4], [4.55, 16], [0, 16]]],
  // Rectilinear N: left and middle strokes meet at the top, middle and right meet at the baseline.
  N: [[[0, 2.5], [2.5, 0], [6.1, 0], [6.1, 11], [7, 11], [7, 0], [10, 0], [10, 13.5], [7.5, 16], [3.9, 16], [3.9, 5],
       [3, 5], [3, 16], [0, 16]]],
};

const WORD = "PRAMAAN";
const HOLES = new Set(["A:1"]); // polygons drawn as holes rather than fills

function path(poly: Poly, dx: number) {
  return "M" + poly.map(([x, y]) => `${(x + dx).toFixed(2)} ${y}`).join("L") + "Z";
}

export function BlockWordmark({ className, animate = false, title = "PRAMAAN" }:
  { className?: string; animate?: boolean; title?: string }) {
  let i = 0;
  const letters = [...WORD].map((ch, li) => {
    const dx = li * (CELL + GAP);
    const polys = GLYPHS[ch];
    const fills = polys.filter((_, pi) => !HOLES.has(`${ch}:${pi}`));
    const holes = polys.filter((_, pi) => HOLES.has(`${ch}:${pi}`));
    // Holes are folded into the first fill so even-odd rendering cuts them out.
    return fills.map((poly, pi) => {
      const d = path(poly, dx) + (pi === 0 ? holes.map((h) => path(h, dx)).join("") : "");
      const idx = i++;
      return <path key={`${li}-${pi}`} d={d} fillRule="evenodd" className={animate ? "wm-piece" : undefined}
        style={animate ? { animationDelay: `${120 + idx * 45}ms` } : undefined} />;
    });
  });
  const stopX = WORD.length * (CELL + GAP);
  const width = stopX + 3;
  return (
    <svg viewBox={`0 0 ${width} ${H}`} className={cx("block", className)} role="img" aria-label={title}
      preserveAspectRatio="xMinYMid meet">
      <defs><clipPath id={animate ? "wm-clip-anim" : undefined}><rect x="0" y="0" width={width} height={H} /></clipPath></defs>
      <g fill="currentColor" clipPath={animate ? "url(#wm-clip-anim)" : undefined}>
        {letters}
        <rect x={stopX} y={H - 3} width="3" height="3" fill="var(--color-tape)"
          className={animate ? "wm-piece" : undefined} style={animate ? { animationDelay: `${120 + i * 45 + 120}ms` } : undefined} />
      </g>
    </svg>
  );
}

import { createContext, useContext, useLayoutEffect, useRef, useSyncExternalStore, type ReactNode } from "react";
import { between, createScrollStory, ease, type Key, type Track, type Values } from "../../lib/scrollStory";
import { cx } from "../ui";
import { STORY_FIELDS, StoryDocument, type FieldId } from "./StoryDocument";

/*
 * One sticky stage, one document, many scenes.
 * The stage sits behind the scene copy and never takes pointer events. Every moving part is
 * positioned at the stage centre and driven by keyframes at story times (scene i = [i, i + 1)).
 * x is in vw; y is in percent of the document's width (--doc-w), so vertical geometry stays
 * consistent at any aspect ratio. Desktop and compact (< 1024 px) use different keyframes.
 */

export const UPLOAD_STAGES = ["Reading file", "Extracting text and layout", "Extracting fields",
  "Checking document integrity", "Verifying with sources", "Evaluating rule pack"];

const NODES: { id: string; title: string; note: string; tone: "leaf" | "dusk" | "neutral" | "turmeric"; x: number; y: number }[] = [
  { id: "qr", title: "Signed QR (tier 1)", note: "Signature valid · Authentic, expired", tone: "turmeric", x: 74, y: 24 },
  { id: "registry", title: "Issuer registry (tier 3)", note: "Not needed here · Simulated source", tone: "dusk", x: 78, y: 42 },
  { id: "digilocker", title: "DigiLocker", note: "Not connected · needs AICTE authorization", tone: "neutral", x: 78, y: 60 },
  { id: "officer", title: "Officer (manual)", note: "Last resort when no source can answer", tone: "neutral", x: 74, y: 78 },
];

type Parts = Record<string, HTMLElement | SVGElement | null>;

const k = (t: number, v: Values, e?: (x: number) => number): Key => ({ t, v, ease: e });

function poses(compact: boolean) {
  // Timing: every move takes about a third of a chapter and straddles the chapter boundary, so it is
  // already under way when the chapter's text reaches the reading line; holds in between give the
  // reader still frames. Intermediate keys (the handover arc) are passed through without stopping.
  const P = { o: 1, x: 0, y: 0, z: 0, r: 0, rx: 0, ry: 0, s: 1 };
  if (!compact) {
    return {
      doc: [
        k(0, { ...P, x: 22, y: 0, r: -6, hover: 1 }),
        k(0.55, { hover: 0 }),
        k(0.72, {}),
        k(1.15, { x: 20, y: 4, r: -2, s: 0.88 }),
        k(1.65, {}),
        k(2.1, { x: 22, y: 0, r: 0, s: 0.5 }),
        k(2.78, {}),
        k(3.05, { x: 4, y: 0, r: -3, s: 0.48 }),
        k(3.12, {}),
        k(3.36, { x: 17, y: -42, r: 7, ry: -16, s: 0.55 }),
        k(3.62, { x: 30, y: -38, r: 1, ry: 0, s: 0.5 }),
        k(3.8, { y: 46, r: 0, o: 0 }, ease.in),  // fully inside the slot and faded before it moves
        k(3.84, { x: 18, y: 0, s: 1.04, o: 0 }, ease.linear),
        k(4.04, { o: 1 }),
        k(4.9, {}),
        k(5.25, { x: 12, ry: -24, s: 1 }),
        k(5.85, {}),
        k(6.2, { x: 2, ry: 0, s: 0.75 }),
        k(6.8, {}),
        k(7.15, { x: 6, s: 0.84 }),
        k(7.8, {}),
        k(8.15, { x: 4, s: 0.94 }),
      ],
      ghosts: [
        { x: 27, y: -12, r: 9, s: 0.82 },
        { x: 13, y: 9, r: -10, s: 0.82 },
        { x: 30, y: 16, r: 15, s: 0.78 },
      ].map((g) => [
        k(0, { ...P, x: 22, r: -6, o: 0 }),
        k(0.72, {}),
        k(1.15, { ...g, o: 1 }),
        k(1.6, {}),
        k(1.95, { x: 22, y: 0, r: 0, s: 0.6, o: 0 }),
      ]),
      upload: [k(0, { ...P, x: 22, y: 14, o: 0 }), k(1.75, {}), k(2.1, { y: 0, o: 1 }), k(2.78, {}), k(3.0, { o: 0, y: -6 })],
      sender: [k(0, { ...P, x: 4, y: 10, o: 0 }), k(2.82, {}), k(3.05, { y: 0, o: 1 }), k(3.28, {}), k(3.5, { o: 0 })],
      slot: [k(0, { ...P, x: 30, y: 58, o: 0 }), k(3.12, {}), k(3.36, { o: 1 }), k(3.8, { s: 1 }), k(4.05, { s: 2.6, o: 0 }, ease.in)],
      proof: [k(0, { ...P, x: 37, o: 0 }), k(8.1, {}), k(8.45, { x: 33, o: 1 })],
    };
  }
  return {
    doc: [
      k(0, { ...P, x: 0, y: -105, r: -5, hover: 0 }),
      k(0.72, {}),
      k(1.15, { y: -110, r: -2, s: 0.88 }),
      k(1.65, {}),
      k(2.1, { y: -105, r: 0, s: 0.5 }),
      k(2.78, {}),
      k(3.05, { x: -22, r: -3, s: 0.48 }),
      k(3.12, {}),
      k(3.36, { x: 0, y: -165, r: 7, s: 0.52 }),
      k(3.62, { x: 22, y: -155, r: 1, s: 0.5 }),
      k(3.8, { y: -92, r: 0, o: 0 }, ease.in),
      k(3.84, { x: 0, y: -105, s: 1, o: 0 }, ease.linear),
      k(4.04, { o: 1 }),
      k(4.9, {}),
      k(5.25, { x: -8, ry: -20, s: 0.92 }),
      k(5.85, {}),
      k(6.2, { x: 0, ry: 0, s: 0.86 }),
      k(6.8, {}),
      k(7.15, { s: 0.9 }),
      k(7.8, {}),
      k(8.15, { s: 0.95 }),
    ],
    ghosts: [
      { x: 18, y: -125, r: 9, s: 0.72 },
      { x: -18, y: -99, r: -10, s: 0.72 },
      { x: 12, y: -85, r: 14, s: 0.68 },
    ].map((g) => [
      k(0, { ...P, y: -105, r: -5, o: 0 }),
      k(0.72, {}),
      k(1.15, { ...g, o: 1 }),
      k(1.6, {}),
      k(1.95, { x: 0, y: -105, r: 0, s: 0.6, o: 0 }),
    ]),
    upload: [k(0, { ...P, y: -91, o: 0 }), k(1.75, {}), k(2.1, { y: -105, o: 1 }), k(2.78, {}), k(3.0, { o: 0, y: -111 })],
    sender: [k(0, { ...P, x: -22, y: -95, o: 0 }), k(2.82, {}), k(3.05, { y: -105, o: 1 }), k(3.28, {}), k(3.5, { o: 0 })],
    slot: [k(0, { ...P, x: 22, y: -92, o: 0 }), k(3.12, {}), k(3.36, { o: 1 }), k(3.8, { s: 1 }), k(4.05, { s: 2.2, o: 0 }, ease.in)],
    proof: [k(0, { ...P, o: 0 })],
  };
}

const transform = (v: Values) =>
  `translate3d(${v.x}vw, calc(var(--doc-w) * ${(v.y / 100).toFixed(4)}), ${v.z}px) rotateX(${v.rx}deg) rotateY(${v.ry}deg) rotate(${v.r}deg) scale(${v.s})`;

function place(el: HTMLElement | SVGElement | null, v: Values) {
  if (!el) return;
  el.style.transform = transform(v);
  el.style.opacity = v.o.toFixed(3);
  el.style.visibility = v.o < 0.005 ? "hidden" : "visible";
}

function buildTracks(p: Parts, compact: boolean): Track[] {
  const ps = poses(compact);
  const paper = p.paper as HTMLElement;
  const scan = paper.querySelector<SVGGElement>("[data-layer=scan]");
  const flag = paper.querySelector<SVGGElement>("[data-layer=flag]");
  const boxes = STORY_FIELDS.map((f, i) => ({ el: paper.querySelector<SVGGElement>(`[data-field=${f.id}]`), at: 4.12 + i * 0.1 }));
  let stageIdx = -1;

  const tracks: Track[] = [
    {
      keys: ps.doc,
      write: (v, _t, vel) => {
        // A small lean in the direction of travel, like paper moving through air. Zero when the story is at rest.
        const lean = Math.max(-1, Math.min(1, vel / 2.5));
        place(p.doc, { ...v, r: v.r + lean * 2.2, y: v.y + Math.abs(lean) * -1.5 });
        const floatEl = p.float as HTMLElement;
        floatEl.style.setProperty("--hover", v.hover.toFixed(3));
        if (v.hover < 0.99 && floatEl.hasAttribute("data-pointing")) floatEl.removeAttribute("data-pointing");
      },
    },
    ...ps.ghosts.map((keys, i) => ({ keys, write: (v: Values) => place(p[`ghost${i}`], v) })),
    { keys: ps.upload, write: (v) => place(p.upload, v) },
    { keys: ps.sender, write: (v) => place(p.sender, v) },
    { keys: ps.slot, write: (v) => place(p.slot, v) },
    { keys: ps.proof, write: (v) => place(p.proof, v) },
    {
      // Upload progress and the real pipeline stage names.
      keys: [k(0, { q: 0 }), k(2.15, {}), k(2.75, { q: 1 }, ease.linear)],
      write: ({ q }) => {
        (p.bar as HTMLElement).style.transform = `scaleX(${q.toFixed(3)})`;
        const i = q >= 1 ? UPLOAD_STAGES.length : Math.floor(q * UPLOAD_STAGES.length);
        if (i !== stageIdx) {
          stageIdx = i;
          const label = p.stageLabel as HTMLElement;
          label.textContent = i >= UPLOAD_STAGES.length ? "Done — 1 page, 6 values read" : UPLOAD_STAGES[i];
          // Cross-fade each new stage name in; Web Animations, no reflow, no React state.
          label.animate?.([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: 150, easing: "ease-out" });
        }
      },
    },
    {
      // Document overlays: scan line, field boxes, the Valid Upto flag, the proof ribbon, the text layer.
      keys: [k(0, { u: 0 })],
      write: (_v, t) => {
        // Calibrated sweep: reaches y ≈ 74 at t=4.12 (Certificate No.), y ≈ 140 at t=4.52 (Valid Upto), y ≈ 245 at t=4.62 (Signed QR).
        const sweep = t <= 4.04 ? 0 : t < 4.52 ? 0.25 * between(t, 4.04, 4.12) + 0.23 * between(t, 4.12, 4.52) : 0.48 + 0.52 * ease.out(between(t, 4.52, 4.82));
        scan?.setAttribute("transform", `translate(0 ${(sweep * 297).toFixed(1)})`);
        scan?.setAttribute("opacity", (between(t, 4.02, 4.1) * (1 - between(t, 4.8, 4.94))).toFixed(3));
        const fade = 1 - between(t, 4.98, 5.18);
        for (const b of boxes) b.el?.setAttribute("opacity", (ease.out(between(t, b.at, b.at + 0.1)) * fade).toFixed(3));
        flag?.setAttribute("opacity", ease.out(between(t, 7.42, 7.54)).toFixed(3));
        (p.ribbon as HTMLElement).style.transform = `scaleY(${ease.inOut(between(t, 8.12, 8.5)).toFixed(3)})`;
        (p.progress as HTMLElement).style.transform = `scaleX(${Math.min(1, t / 9).toFixed(4)})`;
        const apart = ease.inOut(between(t, 5.25, 5.52)) * (1 - ease.inOut(between(t, 5.7, 5.9)));
        const layer = p.layer as HTMLElement;
        layer.style.transform = `translate3d(${(apart * (compact ? 44 : 52)).toFixed(2)}%, ${(apart * -3).toFixed(2)}%, ${(apart * 80).toFixed(1)}px) rotate(${(apart * 2).toFixed(2)}deg)`;
        layer.style.opacity = Math.min(1, apart * 1.6).toFixed(3);
        layer.style.visibility = apart < 0.005 ? "hidden" : "visible";
        // Cross-source lines draw one after another, then fade before the rules scene.
        const out = 1 - ease.inOut(between(t, 6.75, 6.92));
        (p.nodes as HTMLElement).style.opacity = (between(t, 6.12, 6.22) * out).toFixed(3);
        (p.nodes as HTMLElement).style.visibility = out * between(t, 6.12, 6.22) < 0.005 ? "hidden" : "visible";
        NODES.forEach((n, i) => {
          const d = ease.inOut(between(t, 6.2 + i * 0.1, 6.38 + i * 0.1));
          p[`clip-${n.id}`]?.setAttribute("width", (d * (n.x - 63)).toFixed(2));
          const chip = p[`node-${n.id}`] as HTMLElement | null;
          if (chip) {
            chip.style.opacity = ease.out(between(t, 6.36 + i * 0.1, 6.46 + i * 0.1)).toFixed(3);
            chip.style.transform = `translate(0, calc(-50% + ${((1 - d) * 8).toFixed(1)}px))`;
          }
        });
      },
    },
  ];
  return tracks;
}

const subscribeMq = (q: string) => (cb: () => void) => {
  const mq = window.matchMedia(q);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};
export function useMedia(q: string) {
  return useSyncExternalStore(subscribeMq(q), () => window.matchMedia(q).matches);
}

const StaticCtx = createContext(false);

/** A scene section. Index 0 is the opening screen; the others are scroll chapters.
 *  `still` is the document state shown beside the copy when motion is reduced. */
export function Scene({ index, id, tall, label, still, children }: {
  index: number; id?: string; tall?: boolean; label: string;
  still?: { boxes?: FieldId[]; flag?: boolean; scan?: number; textLayer?: boolean }; children: ReactNode;
}) {
  const isStatic = useContext(StaticCtx);
  return (
    <section data-scene={index} id={id ?? `scene-${index}`} aria-label={label}
      className={cx("journey-scene", index === 0 ? "journey-scene-open" : tall ? "journey-scene-tall" : "journey-scene-std")}>
      <div className={index === 0 ? "journey-open" : "journey-copy"}>{children}</div>
      {isStatic && (
        <div className="journey-still">
          <div className="journey-paper"><StoryDocument still={still ?? {}} /></div>
          {still?.textLayer && <div className="journey-paper"><StoryDocument variant="textLayer" still={{}} /></div>}
        </div>
      )}
    </section>
  );
}

/** A line in the scene copy that lights up when the story reaches `at`. */
export function Mark({ at, tone, children, className }: { at: number; tone?: "tape"; children: ReactNode; className?: string }) {
  return <li data-at={at} data-tone={tone} className={cx("journey-mark", className)}>{children}</li>;
}

export function DocumentJourney({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement | null>(null);
  const reduce = useMedia("(prefers-reduced-motion: reduce)");
  const compact = useMedia("(max-width: 1023px)");

  // Layout effect: the first frame already shows the document in its opening pose.
  useLayoutEffect(() => {
    const el = root.current;
    if (!el || reduce) return;
    const parts: Parts = {};
    el.querySelectorAll<HTMLElement>("[data-part]").forEach((n) => { parts[n.dataset.part!] = n; });
    const story = createScrollStory({
      scenes: [...el.querySelectorAll<HTMLElement>("[data-scene]")],
      marks: [...el.querySelectorAll<HTMLElement>("[data-at]")],
      tracks: buildTracks(parts, compact),
      smooth: 0.26,
      onSettle: (done) => el.toggleAttribute("data-settled", done),
      onScene: (i) => {
        el.setAttribute("data-active-scene", String(i));
        (parts.numeral as HTMLElement).textContent = i === 0 ? "" : `(${i})`;
      },
    });

    // Pointer parallax on the opening screen only (desktop, fine pointer). Writes CSS variables, no state.
    let raf = 0;
    const float = parts.float as HTMLElement;
    const onMove = (e: PointerEvent) => {
      if (compact || e.pointerType !== "mouse" || story.time() > 0.05) return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        float.setAttribute("data-pointing", "");
        float.style.setProperty("--px", ((e.clientX / window.innerWidth) * 2 - 1).toFixed(3));
        float.style.setProperty("--py", ((e.clientY / window.innerHeight) * 2 - 1).toFixed(3));
      });
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      story.destroy();
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
    };
  }, [reduce, compact]);

  if (reduce) {
    // Same narrative, no movement: every scene shows a still of the document in that scene's state.
    return (
      <StaticCtx.Provider value={true}>
        <div className="journey journey-static"><div className="journey-scenes">{children}</div></div>
      </StaticCtx.Provider>
    );
  }

  return (
    <div ref={root} className="journey" data-active-scene="0">
      <div className="journey-stage" aria-hidden="true">
        <span data-part="numeral" className="journey-numeral" />
        <span data-part="progress" className="journey-progress" />
        {[0, 1, 2].map((i) => (
          <div key={i} data-part={`ghost${i}`} className="journey-part journey-doc journey-ghost">
            <span className="journey-ghost-tag">Pending</span>
          </div>
        ))}

        <div data-part="upload" className="journey-part journey-upload">
          <div className="journey-upload-head"><strong>Fire safety NOC</strong><span>Required</span></div>
          <div className="journey-upload-foot">
            <div className="journey-upload-file">Fire_NOC.pdf · 13 KB · 1 page</div>
            <div data-part="stageLabel" className="journey-upload-stage">Reading file</div>
            <div className="journey-upload-track"><span data-part="bar" className="journey-upload-bar" /></div>
          </div>
        </div>

        <div data-part="sender" className="journey-part journey-sender">
          <span>From the institution</span>
          <strong>Nodal officer, Godavari College of Engineering (Synthetic)</strong>
        </div>

        <div data-part="doc" className="journey-part journey-doc">
          <div data-part="float" className="journey-float">
            <div data-part="paper" className="journey-paper"><StoryDocument /></div>
            <div data-part="layer" className="journey-layer"><StoryDocument variant="textLayer" /></div>
            <span data-part="ribbon" className="journey-ribbon" />
          </div>
        </div>

        <div data-part="slot" className="journey-part journey-slot">
          <span className="journey-slot-mouth" />
          <strong>PRAMAAN intake</strong>
          <span>Type checked by content · SHA-256 recorded · stored privately</span>
        </div>

        <div data-part="nodes" className="journey-nodes">
          {/* Lines are revealed left to right by growing a clip rectangle (dash tricks break with non-scaling strokes). */}
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
            <defs>
              {NODES.map((n) => (
                <clipPath key={n.id} id={`journey-clip-${n.id}`}>
                  <rect data-part={`clip-${n.id}`} x="63" y="0" width="0" height="100" />
                </clipPath>
              ))}
            </defs>
            {NODES.map((n) => (
              <path key={n.id} clipPath={`url(#journey-clip-${n.id})`} className="journey-line"
                d={`M64 50 C ${(64 + n.x) / 2} 50, ${(64 + n.x) / 2} ${n.y}, ${n.x - 1} ${n.y}`} />
            ))}
          </svg>
          {NODES.map((n) => (
            <div key={n.id} data-part={`node-${n.id}`} className={cx("journey-node", `journey-node-${n.tone}`)}
              style={{ left: `${n.x}%`, top: `${n.y}%` }}>
              <strong>{n.title}</strong><span>{n.note}</span>
            </div>
          ))}
        </div>

        <div data-part="proof" className="journey-part journey-proof">
          <span className="journey-proof-pill">Deficiency · advisory</span>
          <strong className="journey-proof-title">Fire safety NOC valid at the start of the academic year</strong>
          <ol>
            <li><b>1. Rule applied</b> FIRE.VALID · pack v2026.1 · clause not yet verified</li>
            <li><b>2. Evidence read</b> Valid Upto 31-03-2026 · page 1, box shown</li>
            <li><b>3. What the check found</b> 31-03-2026 is before 01-07-2026</li>
            <li><b>4. Source check</b> Signed QR: Authentic, expired</li>
            <li><b>5. Official decision</b> Waiting for an officer</li>
          </ol>
        </div>
      </div>

      <div className="journey-scenes">{children}</div>
    </div>
  );
}

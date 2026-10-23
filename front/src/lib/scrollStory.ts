/**
 * Scroll-scrubbed story timeline, no dependencies (about 2 KB minified).
 *
 * Story time `t` runs from 0 to N across N scene sections; scene i covers [i, i + 1).
 * A track is a list of keyframes at story times plus a writer that puts the interpolated
 * values straight onto the DOM. There is no React state per frame.
 *
 * Flow:
 * - Inertial scrub. The scroll position sets a *target* time; the shown time glides toward it
 *   with frame-rate-independent exponential smoothing (time constant `smooth`, default 0.22 s).
 *   A mouse-wheel notch becomes a short glide instead of a jump. When scrolling stops the shown
 *   time lands exactly on the target, so every scroll position still has exactly one frame and
 *   scrolling back restores it. Native scrolling is untouched.
 * - Continuous motion through keyframes. Values follow a monotone cubic curve (Fritsch–Carlson),
 *   so movement keeps its speed through intermediate keyframes, never overshoots, and comes to
 *   rest wherever a value holds. A key with an explicit `ease` uses that easing for the segment
 *   that ends on it, starting and ending at rest.
 * - Writers also receive the story velocity (story time per second) for small physical touches.
 */
export type Values = Record<string, number>;
export type Ease = (x: number) => number;
export type Key = { t: number; v: Values; ease?: Ease };
export type Track = { keys: Key[]; write: (v: Values, t: number, velocity: number) => void };
export type Story = { refresh(): void; destroy(): void; time(): number };

export const ease = {
  linear: (x: number) => x,
  inOut: (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2),
  out: (x: number) => 1 - (1 - x) ** 3,
  in: (x: number) => x ** 3,
};

type Prepared = { keys: Key[]; slopes: Record<string, number[]> };

/** Sort keyframes and carry values forward, so each key lists only what changes.
 *  The first key of a track must define every value the track uses. */
export function normalise(keys: Key[]): Key[] {
  const sorted = [...keys].sort((a, b) => a.t - b.t);
  let carry: Values = {};
  return sorted.map((k) => {
    carry = { ...carry, ...k.v };
    return { ...k, v: carry };
  });
}

/** Fritsch–Carlson slopes: smooth, monotone between keys, flat at holds and turning points. */
function prepare(raw: Key[]): Prepared {
  const keys = normalise(raw);
  const n = keys.length;
  const slopes: Record<string, number[]> = {};
  for (const ch of Object.keys(keys[n - 1].v)) {
    const m = new Array<number>(n).fill(0);
    const d: number[] = [];
    for (let i = 0; i < n - 1; i++) {
      const h = keys[i + 1].t - keys[i].t;
      d.push(h > 0 ? (keys[i + 1].v[ch] - keys[i].v[ch]) / h : 0);
    }
    for (let i = 1; i < n - 1; i++) {
      if (d[i - 1] * d[i] <= 0) continue;
      const h0 = keys[i].t - keys[i - 1].t;
      const h1 = keys[i + 1].t - keys[i].t;
      const w1 = 2 * h1 + h0;
      const w2 = h1 + 2 * h0;
      m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i]);
    }
    // Explicitly eased segments start and end at rest; match that on both sides.
    for (let i = 1; i < n; i++) if (keys[i].ease) { m[i - 1] = 0; m[i] = 0; }
    slopes[ch] = m;
  }
  return { keys, slopes };
}

/** Value of a prepared track at story time t. */
function sampleAt({ keys, slopes }: Prepared, t: number): Values {
  const last = keys.length - 1;
  if (t <= keys[0].t) return keys[0].v;
  if (t >= keys[last].t) return keys[last].v;
  let i = 0;
  while (t > keys[i + 1].t) i++;
  const a = keys[i];
  const b = keys[i + 1];
  const h = b.t - a.t;
  const out: Values = {};
  if (h <= 0) return b.v;
  const s = (t - a.t) / h;
  if (b.ease) {
    const p = b.ease(s);
    for (const k in b.v) out[k] = a.v[k] + (b.v[k] - a.v[k]) * p;
    return out;
  }
  const s2 = s * s;
  const s3 = s2 * s;
  const h00 = 2 * s3 - 3 * s2 + 1;
  const h10 = s3 - 2 * s2 + s;
  const h01 = -2 * s3 + 3 * s2;
  const h11 = s3 - s2;
  for (const k in b.v) {
    const m = slopes[k];
    out[k] = h00 * a.v[k] + h10 * h * m[i] + h01 * b.v[k] + h11 * h * m[i + 1];
  }
  return out;
}

/** Kept for callers that sample a plain key list. */
export function sample(keys: Key[], t: number): Values {
  return sampleAt(prepare(keys), t);
}

/** 0 → 1 as t moves from `from` to `to`, clamped. Handy inside writers. */
export const between = (t: number, from: number, to: number) => Math.min(1, Math.max(0, (t - from) / (to - from)));

export function createScrollStory(opts: {
  /** The scene sections, in order. They must be stacked with no gaps between them. */
  scenes: HTMLElement[];
  tracks: Track[];
  /** Elements with data-at="4.3" get the attribute data-reached once t passes 4.3 (and lose it on the way back). */
  marks?: HTMLElement[];
  /** The reading line as a fraction of the viewport height. Default 0.6. */
  anchor?: number;
  /** Glide time constant in seconds (0 = follow the scroll position exactly). Default 0.22. */
  smooth?: number;
  /** Jumps larger than this many chapters (anchor links, Home/End, restored scroll) snap instead of gliding. Default 1.5. */
  snapOver?: number;
  /** Called when the scene index under the reading line changes (not every frame). */
  onScene?: (index: number) => void;
  /** Called with true when the shown time has landed on the target, false when it starts moving. */
  onSettle?: (settled: boolean) => void;
}): Story {
  const tracks = opts.tracks.map((tr) => ({ write: tr.write, prepared: prepare(tr.keys) }));
  const marks = (opts.marks ?? []).map((el) => ({ el, at: Number(el.dataset.at), on: false }));
  const anchor = opts.anchor ?? 0.6;
  const smooth = opts.smooth ?? 0.22;
  const snapOver = opts.snapOver ?? 1.5;
  const n = opts.scenes.length;
  let starts: number[] = [];
  let frame = 0;
  let shown = Number.NaN;
  let drawn = Number.NaN;
  let lastTs = 0;
  let velocity = 0;
  let scene = -1;
  let settled: boolean | null = null;
  let alive = true;
  let measuredVh = 0;
  let lastWidth = 0;

  function measure() {
    const y = window.scrollY;
    const vh = window.innerHeight;
    measuredVh = vh;
    lastWidth = window.innerWidth;
    const line = vh * anchor;
    starts = opts.scenes.map((s) => s.getBoundingClientRect().top + y);
    const end = starts[n - 1] + opts.scenes[n - 1].offsetHeight;
    // The story ends exactly when the sticky stage lets go (container bottom reaches the viewport bottom).
    starts.push(Math.max(end - (vh - line), starts[n - 1] + 1));
    // Scene 0 begins at the reading line on page load, so the first screen shows t = 0.
    starts[0] = Math.min(starts[0] + line, starts[1] - 1);
  }

  function timeAt(y: number) {
    const line = y + (measuredVh || window.innerHeight) * anchor;
    if (line <= starts[0]) return 0;
    for (let i = 0; i < n; i++) {
      if (line < starts[i + 1]) return i + (line - starts[i]) / (starts[i + 1] - starts[i]);
    }
    return n;
  }

  function setSettled(v: boolean) {
    if (v !== settled) {
      settled = v;
      opts.onSettle?.(v);
    }
  }

  function draw(t: number) {
    for (const tr of tracks) tr.write(sampleAt(tr.prepared, t), t, velocity);
    for (const m of marks) {
      const on = t >= m.at;
      if (on !== m.on) {
        m.on = on;
        m.el.toggleAttribute("data-reached", on);
      }
    }
    const s = Math.min(n - 1, Math.floor(t));
    if (s !== scene) {
      scene = s;
      opts.onScene?.(s);
    }
    drawn = t;
  }

  function render(ts: number) {
    frame = 0;
    if (!alive) return;
    const target = timeAt(window.scrollY);
    const dt = lastTs && ts - lastTs < 100 ? (ts - lastTs) / 1000 : 1 / 60;
    lastTs = ts;
    const prev = shown;
    if (Number.isNaN(shown) || smooth <= 0 || Math.abs(target - shown) > snapOver) {
      shown = target;
    } else {
      shown += (target - shown) * (1 - Math.exp(-dt / smooth));
      if (Math.abs(target - shown) < 0.0004) shown = target;
    }
    velocity = Number.isNaN(prev) || shown === target && prev === target ? 0 : (shown - prev) / dt;
    if (shown !== drawn) draw(shown);
    if (shown !== target) {
      setSettled(false);
      frame = requestAnimationFrame(render);
    } else {
      if (velocity !== 0) { velocity = 0; draw(shown); } // final frame at rest: velocity-based touches return to zero
      setSettled(true);
      lastTs = 0;
    }
  }

  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(render);
  };
  const refresh = () => {
    if (!alive) return;
    measure();
    drawn = Number.NaN;
    schedule();
  };

  const onResize = () => {
    if (window.innerWidth !== lastWidth || Math.abs(window.innerHeight - measuredVh) > 120) refresh();
    else schedule();
  };

  const ro = new ResizeObserver(refresh);
  opts.scenes.forEach((s) => ro.observe(s));
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("touchmove", schedule, { passive: true });
  window.addEventListener("resize", onResize, { passive: true });
  window.addEventListener("orientationchange", refresh);
  document.fonts?.ready.then(refresh).catch(() => {});
  measure();
  render(performance.now());

  return {
    refresh,
    time: () => shown,
    destroy() {
      alive = false;
      cancelAnimationFrame(frame);
      ro.disconnect();
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("touchmove", schedule);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", refresh);
    },
  };
}

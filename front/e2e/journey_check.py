"""Checks the scroll-driven document journey on the start page.

Usage: python e2e/journey_check.py <base_url> <outdir>
Runs against any server that serves the built web client (no sign-in needed).
Prints PASS/FAIL per check and writes screenshots of every scene at desktop and phone sizes.
"""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

base, out = sys.argv[1].rstrip("/"), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
results, errors = [], []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


STATE_JS = """() => {
  const q = (s) => document.querySelector(s);
  const doc = q('[data-part=doc]');
  return {
    t: Number(q('.journey')?.getAttribute('data-active-scene')),
    doc: doc ? doc.style.transform + '|' + doc.style.opacity : null,
    reached: document.querySelectorAll('[data-reached]').length,
    scroll: Math.round(scrollY),
  };
}"""

# Scroll positions as fractions of the journey container, sampled forward then backward.
FRACTIONS = [0, 0.08, 0.17, 0.27, 0.36, 0.45, 0.55, 0.64, 0.73, 0.82, 0.92, 0.99]


def journey_bounds(pg):
    return pg.evaluate("""() => { const j = document.querySelector('.journey');
      const r = j.getBoundingClientRect(); return { top: r.top + scrollY, height: j.offsetHeight, vh: innerHeight }; }""")


def go(pg, y):
    """Scroll, then wait until the story has glided to rest (the engine sets data-settled)."""
    pg.evaluate(f"window.scrollTo(0, {y})")
    pg.wait_for_timeout(120)
    pg.evaluate("""() => new Promise(r => { const t0 = performance.now();
      const tick = () => { const j = document.querySelector('.journey');
        if (!j || j.hasAttribute('data-settled') || performance.now() - t0 > 3000) r(); else requestAnimationFrame(tick); };
      requestAnimationFrame(() => requestAnimationFrame(tick)); })""")


with sync_playwright() as p:
    b = p.chromium.launch()
    for label, vp, scale in [("desktop", {"width": 1440, "height": 900}, 1), ("laptop", {"width": 1280, "height": 720}, 1),
                             ("phone", {"width": 390, "height": 844}, 2)]:
        ctx = b.new_context(viewport=vp, device_scale_factor=scale)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{label}: {e}"))
        pg.on("console", lambda m: m.type == "error" and "401" not in m.text and errors.append(f"{label}: {m.text}"))
        pg.goto(base + "/")
        pg.wait_for_timeout(1500)
        jb = journey_bounds(pg)
        span = jb["height"] - jb["vh"]
        ys = [round(jb["top"] + f * span) for f in FRACTIONS]

        first = pg.evaluate(STATE_JS)
        check(f"{label}: document visible on the first screen", first["doc"] and float(first["doc"].split("|")[1]) > 0.99, first["doc"])
        check(f"{label}: Sign in visible on the first screen",
              pg.get_by_role("banner").get_by_role("link", name="Sign in", exact=True).is_visible())

        forward = []
        for i, y in enumerate(ys):
            go(pg, y)
            forward.append(pg.evaluate(STATE_JS))
            pg.screenshot(path=out / f"{label}-{i:02d}.png")
        backward = []
        for y in reversed(ys):
            go(pg, y)
            backward.append(pg.evaluate(STATE_JS))
        backward.reverse()
        same = all(f["doc"] == bk["doc"] and f["reached"] == bk["reached"] for f, bk in zip(forward, backward))
        check(f"{label}: scrolling back restores every sampled state exactly", same,
              json.dumps([(f["doc"], bk["doc"]) for f, bk in zip(forward, backward) if f["doc"] != bk["doc"]][:2]))
        scenes = [f["t"] for f in forward]
        check(f"{label}: scenes advance in order 0 → 8", scenes == sorted(scenes) and scenes[0] == 0 and scenes[-1] == 8, scenes)
        check(f"{label}: no horizontal scroll", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))

        # After the journey the stage lets go and the page scrolls normally.
        go(pg, jb["top"] + jb["height"] + 200)
        stage_top = pg.evaluate("document.querySelector('.journey-stage').getBoundingClientRect().bottom")
        check(f"{label}: stage releases after the last scene", stage_top < jb["vh"], stage_top)

        # The stage never blocks clicks: the element under the screen centre is never inside it.
        go(pg, ys[5])
        hit = pg.evaluate("""() => { const e = document.elementFromPoint(innerWidth * 0.7, innerHeight * 0.5);
          return e ? !!e.closest('.journey-stage') : false; }""")
        check(f"{label}: stage does not take pointer events", not hit)

        # Resize mid-story keeps the scene and leaves no overflow.
        if label == "desktop":
            go(pg, ys[6])
            before = pg.evaluate(STATE_JS)["t"]
            pg.set_viewport_size({"width": 1100, "height": 800})
            pg.wait_for_timeout(400)
            after = pg.evaluate(STATE_JS)["t"]
            check("desktop: resize keeps the story near the same scene", abs(after - before) <= 1, (before, after))
            check("desktop: no horizontal scroll after resize", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            pg.set_viewport_size(vp)

        # Pace and presence: a medium-length page and a document that fills its side of the stage.
        size = pg.evaluate("""() => ({ screens: document.documentElement.scrollHeight / innerHeight,
          story: document.querySelector('.journey').offsetHeight / innerHeight,
          docW: getComputedStyle(document.querySelector('.journey')).getPropertyValue('--doc-w'),
          docPx: document.querySelector('[data-part=doc] .journey-paper').offsetWidth })""")
        limit = 11 if label != "phone" else 14
        check(f"{label}: whole page at most {limit} screens tall", size["screens"] <= limit, size)
        # Big enough: at least 30% of the width (50% on phones) or, when the height limits it, 60% of the height.
        min_w = 0.30 if label != "phone" else 0.50
        big = size["docPx"] >= min_w * vp["width"] - 1 or size["docPx"] * 1.4143 >= 0.60 * vp["height"]
        check(f"{label}: document fills its side of the stage", big, size)

        # Sign-in dialog from the header: opens, focuses email, Escape closes and returns focus.
        go(pg, 0)
        btn = pg.get_by_role("banner").get_by_role("link", name="Sign in", exact=True)
        btn.click()
        pg.wait_for_timeout(250)
        check(f"{label}: header Sign in opens the dialog", pg.evaluate("document.querySelector('dialog').open"))
        check(f"{label}: dialog focuses the email field", pg.evaluate("document.activeElement.id") == "signin-email")
        pg.screenshot(path=out / f"{label}-dialog.png")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(150)
        check(f"{label}: Escape closes the dialog", not pg.evaluate("document.querySelector('dialog').open"))
        check(f"{label}: focus returns to the Sign in button",
              pg.evaluate("document.activeElement.textContent.trim()") == "Sign in")
        ctx.close()

    # Reduced motion: no sticky stage, every scene shows a still document, marks shown as reached.
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    pg = ctx.new_page()
    pg.goto(base + "/")
    pg.wait_for_timeout(1000)
    check("reduced motion: no animated stage", pg.locator(".journey-stage").count() == 0)
    check("reduced motion: a still document in every scene", pg.locator(".journey-still").count() == 9)
    pg.screenshot(path=out / "reduced-motion.png", full_page=True)
    ctx.close()

    # Flow under a mouse wheel (desktop): one 100 px notch every 70 ms. The document must glide on
    # almost every frame instead of jumping once per notch. Frames where it is invisible are ignored.
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.goto(base + "/")
    pg.wait_for_timeout(1500)
    pg.mouse.move(400, 450)
    pg.evaluate("""() => { window.__rec = []; const d = document.querySelector('[data-part=doc]');
      const stage = document.querySelector('.journey-stage');
      const loop = () => { const r = d.getBoundingClientRect(); const s = stage.getBoundingClientRect();
        window.__rec.push([r.left - s.left + r.width / 2, r.top - s.top + r.height / 2, r.width, Number(getComputedStyle(d).opacity)]);
        if (window.__rec.length < 5000) requestAnimationFrame(loop); }; requestAnimationFrame(loop); }""")
    for _ in range(70):
        pg.mouse.wheel(0, 100)
        pg.wait_for_timeout(70)
    pg.wait_for_timeout(900)
    rec = pg.evaluate("window.__rec")
    steps = [((c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2) ** 0.5 + abs(c[2] - a[2])
             for a, c in zip(rec, rec[1:]) if min(a[3], c[3]) >= 0.05]
    moving = [x for x in steps if x > 0.05]
    stops = sum(1 for a, c in zip(steps, steps[1:]) if a <= 0.05 < c)
    flow = {"frames": len(steps), "moving": len(moving), "stop_starts": stops,
            "p95_px": round(sorted(moving)[int(len(moving) * 0.95)], 1) if moving else 0}
    check("flow: the document moves on most frames while the wheel turns (no per-notch jumps)", len(moving) >= 0.8 * len(steps), flow)
    check("flow: at most 8 stop-start stutters across the whole story", stops <= 8, flow)
    check("flow: 95% of frames move the document less than 45 px", flow["p95_px"] < 45, flow)
    ctx.close()

    # Frame cost while scrolling through the whole journey (desktop).
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.goto(base + "/")
    pg.wait_for_timeout(1200)
    stats = pg.evaluate("""async () => {
      const long = []; new PerformanceObserver(l => long.push(...l.getEntries().map(e => e.duration))).observe({ type: 'longtask', buffered: false });
      const j = document.querySelector('.journey'); const end = j.offsetTop + j.offsetHeight;
      const frames = []; let last = performance.now();
      for (let y = 0; y < end; y += 40) { window.scrollTo(0, y);
        await new Promise(r => requestAnimationFrame(r)); const now = performance.now(); frames.push(now - last); last = now; }
      frames.sort((a, b) => a - b);
      return { frames: frames.length, p95: frames[Math.floor(frames.length * 0.95)], longTasks: long.length, worstLong: Math.max(0, ...long) };
    }""")
    check("scroll frames: p95 frame time under 34 ms (headless, software rendering)", stats["p95"] < 34, stats)
    check("scroll frames: no long task over 100 ms", stats["worstLong"] < 100, stats)
    ctx.close()
    b.close()

for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if not ok and detail != "" else ""))
print("page errors:", errors or "none")
print(f"{sum(ok for _, ok, _ in results)} of {len(results)} checks passed")

"""Walks every route as each role at 1440x900 and 390x844 and asserts no unhandled page errors, no unexpected console errors, and no horizontal overflow.

Usage: python e2e/inventory_check.py <base_url> <password> <outdir>
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

base, pw, out = sys.argv[1].rstrip("/"), sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
results, errors = [], []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def login(page, email):
    page.goto(base + "/login")
    page.wait_for_timeout(400)
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password", exact=True).fill(pw)
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    page.wait_for_timeout(500)


ROLE_ROUTES = [
    ("public", None, ["/", "/login", "/help"]),
    ("institution", "nodal@godavari.synthetic.in", ["/institution", "/help"]),
    ("officer", "officer@aicte.synthetic.in", ["/queue", "/rules", "/audit", "/benchmark", "/help"]),
    ("admin", "admin@aicte.synthetic.in", ["/queue", "/rules", "/audit", "/benchmark", "/help"]),
    ("auditor", "auditor@aicte.synthetic.in", ["/audit", "/rules", "/benchmark", "/help"]),
]

with sync_playwright() as p:
    b = p.chromium.launch()
    for vp_name, vp in [("desktop", {"width": 1440, "height": 900}), ("phone", {"width": 390, "height": 844})]:
        for role_name, email, routes in ROLE_ROUTES:
            ctx = b.new_context(viewport=vp, device_scale_factor=2 if vp_name == "phone" else 1)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e, r=role_name, v=vp_name: errors.append(f"{v}/{r}: pageerror: {e}"))
            pg.on("console", lambda m, r=role_name, v=vp_name: m.type == "error" and "401" not in m.text and errors.append(f"{v}/{r}: console: {m.text}"))

            if email:
                login(pg, email)

            for route in routes:
                pg.goto(base + route)
                pg.wait_for_timeout(700)
                no_overflow = pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
                has_h1 = pg.locator("h1").count() >= 1
                slug = route.strip("/") or "landing"
                pg.screenshot(path=out / f"inv-{vp_name}-{role_name}-{slug}.png")
                check(f"{vp_name} {role_name} {route}: no horizontal overflow", no_overflow)
                check(f"{vp_name} {role_name} {route}: has h1 heading", has_h1)

            if role_name in ("institution", "officer"):
                # Also visit the first application workspace and its tabs
                pg.goto(base + ("/institution" if role_name == "institution" else "/queue"))
                pg.wait_for_timeout(600)
                first_app = pg.locator("a[href^='/applications/']").first
                if first_app.count() > 0:
                    first_app.click()
                    pg.wait_for_timeout(800)
                    for tab_label in ["Findings", "Documents", "What to fix", "Activity"]:
                        tab_btn = pg.get_by_role("tab", name=tab_label).first
                        if tab_btn.count() > 0:
                            tab_btn.click()
                            pg.wait_for_timeout(500)
                            no_ov = pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
                            check(f"{vp_name} {role_name} workspace/{tab_label}: no horizontal overflow", no_ov)
            ctx.close()
    b.close()

check("zero unhandled page or unexpected console errors across all routes", len(errors) == 0, "; ".join(errors[:5]))

for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if not ok and detail else ""))
print("errors:", errors or "none")
passed = sum(ok for _, ok, _ in results)
print(f"{passed} of {len(results)} checks passed")
if passed < len(results):
    sys.exit(1)

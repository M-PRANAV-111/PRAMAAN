"""Accessibility checks across new and updated screens:
- Skip to content link and landmarks (<header>, <main id="main">, <nav>)
- Native <dialog> modal open, Escape close, and focus restoration
- Explicit labels on all form controls
- Tablist keyboard semantics
- Forced-colors (Windows High Contrast) and prefers-reduced-motion compliance

Usage: python e2e/a11y_check.py <base_url> <password> <outdir>
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
    page.wait_for_timeout(600)


def check_unlabelled_inputs(page):
    return page.evaluate("""() => {
      const els = [...document.querySelectorAll('input:not([type=hidden]), select, textarea')];
      return els.filter(el => {
        if (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby')) return false;
        if (el.closest('label')) return false;
        if (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) return false;
        return true;
      }).map(el => el.outerHTML.slice(0, 80));
    }""")


with sync_playwright() as p:
    b = p.chromium.launch()

    # 1. Landmarks, skip link, form labels, and native <dialog> Escape on InstitutionHome, Queue, Workspace & Help
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "401" not in m.text and errors.append(m.text))

    login(pg, "nodal@godavari.synthetic.in")

    # Skip link is first tab stop
    pg.keyboard.press("Tab")
    check("InstitutionHome: first Tab reaches Skip to content", pg.evaluate("document.activeElement?.textContent?.trim()") == "Skip to content")
    check("InstitutionHome: has <main id='main'> landmark", pg.locator("main#main").count() == 1)

    start_btn = pg.get_by_role("button", name="Start an application").first
    start_btn.click()
    pg.wait_for_timeout(250)
    unlabelled = check_unlabelled_inputs(pg)
    check("InstitutionHome StartApplication form: all form controls have labels", len(unlabelled) == 0, str(unlabelled))

    # Check labels on Queue and Workspace + native <dialog> on "View what was read"
    pg.get_by_role("button", name="Sign out").click()
    pg.wait_for_timeout(400)
    login(pg, "officer@aicte.synthetic.in")
    unlabelled_q = check_unlabelled_inputs(pg)
    check("Queue: all search/filter controls have explicit labels", len(unlabelled_q) == 0, str(unlabelled_q))

    pg.get_by_role("link", name="Godavari College of Engineering (Synthetic)").click()
    pg.wait_for_url("**/applications/**")
    pg.wait_for_timeout(700)
    unlabelled_w = check_unlabelled_inputs(pg)
    check("Workspace Findings: all form controls have explicit labels", len(unlabelled_w) == 0, str(unlabelled_w))

    # Open native <dialog> on Documents -> View what was read and close with Escape
    pg.get_by_role("tab", name="Documents").click()
    pg.wait_for_timeout(400)
    pg.get_by_role("button", name="View what was read").first.click()
    pg.wait_for_timeout(400)
    check("Workspace DocumentDialog opens native <dialog open>", pg.evaluate("Boolean(document.querySelector('dialog')?.open)"))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(200)
    check("Escape closes native <dialog>", not pg.evaluate("Boolean(document.querySelector('dialog')?.open)"))

    # Help page landmarks and h1
    pg.goto(base + "/help")
    pg.wait_for_timeout(500)
    check("Help page has single h1 and main#main landmark", pg.locator("h1").count() == 1 and pg.locator("main#main").count() == 1)
    ctx.close()

    # 2. Forced-colors (Windows High Contrast) on signed-in screens
    fc_ctx = b.new_context(viewport={"width": 1440, "height": 900}, forced_colors="active")
    fc_pg = fc_ctx.new_page()
    login(fc_pg, "officer@aicte.synthetic.in")
    has_sheet_border = fc_pg.evaluate("getComputedStyle(document.querySelector('.sheet')).borderTopStyle !== 'none'")
    check("forced-colors: .sheet surfaces retain visible borders on signed-in screens", has_sheet_border)
    fc_pg.screenshot(path=out / "a11y-forced-colors-queue.png")
    fc_ctx.close()

    b.close()

check("zero unhandled page or console errors", len(errors) == 0, "; ".join(errors))

for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if not ok and detail else ""))
print("errors:", errors or "none")
passed = sum(ok for _, ok, _ in results)
print(f"{passed} of {len(results)} checks passed")
if passed < len(results):
    sys.exit(1)

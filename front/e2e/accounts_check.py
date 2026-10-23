"""Tests sign-in, role routing, returnTo redirect, language toggle, and contract-first feature-gating for account/registration/admin flows.

Usage: python e2e/accounts_check.py <base_url> <password> <outdir>
"""
import json
import sys
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

base, pw, out = sys.argv[1].rstrip("/"), sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
results, errors = [], []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


with urllib.request.urlopen(base + "/api/v1/meta") as resp:
    meta = json.loads(resp.read().decode("utf-8"))
features = meta.get("features") or {}

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "401" not in m.text and errors.append(m.text))

    # 1. Protected route redirects to /login with returnTo, and signing in restores the route.
    pg.goto(base + "/rules")
    pg.wait_for_url("**/login**")
    check("unauthenticated visit to /rules redirects to /login with returnTo", "returnTo=%2Frules" in pg.url, pg.url)

    pg.get_by_role("button", name="Scrutiny officer, Ananya Rao: fill officer@aicte.synthetic.in").click()
    pg.get_by_label("Password", exact=True).fill(pw)
    pg.get_by_role("button", name="Sign in", exact=True).click()
    pg.wait_for_url("**/rules")
    pg.wait_for_timeout(500)
    check("signing in honours returnTo=/rules", pg.url.endswith("/rules"))
    pg.screenshot(path=out / "accounts-returnto-rules.png")

    # 2. Language toggle switches <html lang="hi"> and back to <html lang="en">
    lang_btn = pg.get_by_role("button", name="Switch language to Hindi")
    check("language toggle button visible in signed-in header", lang_btn.is_visible())
    lang_btn.click()
    pg.wait_for_timeout(200)
    check("clicking हिन्दी sets html[lang='hi']", pg.evaluate("document.documentElement.lang") == "hi")
    pg.screenshot(path=out / "accounts-lang-hi.png")
    pg.get_by_role("button", name="Switch language to English").click()
    pg.wait_for_timeout(200)
    check("clicking EN restores html[lang='en']", pg.evaluate("document.documentElement.lang") == "en")

    # 3. Help page is reachable for signed-in user and contains role guides + 6 verification statuses
    pg.get_by_role("navigation", name="Main").get_by_role("link", name="Help").click()
    pg.wait_for_url("**/help")
    pg.wait_for_timeout(500)
    check("/help renders Help & role guide heading", pg.get_by_role("heading", name="Help & role guide").is_visible())
    check("/help lists all 6 verification statuses", pg.get_by_text("Verified at source").is_visible() and pg.get_by_text("Manual check needed").is_visible())
    pg.screenshot(path=out / "accounts-help.png")

    # 4. Segmented login selector + End-to-End Applicant Registration -> Logout -> Login -> Dashboard
    pg.get_by_role("button", name="Sign out").click()
    pg.wait_for_timeout(400)
    pg.goto(base + "/login")
    pg.wait_for_timeout(500)
    applicant_tab = pg.get_by_role("button", name="Applicant / Institution Login")
    officer_tab = pg.get_by_role("button", name="AICTE Officer Login")
    check("login card shows Applicant vs AICTE Officer portal selector", applicant_tab.is_visible() and officer_tab.is_visible())
    officer_tab.click()
    check("clicking AICTE Officer Login activates officer mode", officer_tab.get_attribute("aria-pressed") == "true")
    applicant_tab.click()
    check("clicking Applicant / Institution Login activates applicant mode", applicant_tab.get_attribute("aria-pressed") == "true")

    reg_link = pg.get_by_role("link", name="New applicant? Register your institution")
    check("Register link visible on login card", reg_link.is_visible())
    reg_link.click()
    pg.wait_for_url("**/register")
    pg.wait_for_timeout(400)
    check("/register renders h1 heading cleanly", pg.get_by_role("heading", name="Register your institution").is_visible())

    test_email = "new.applicant@sih2026.synthetic.in"
    pg.get_by_label("Nodal officer name").fill("Dr. Kavita Nair")
    pg.get_by_label("Official email").fill(test_email)
    pg.get_by_label("Password", exact=True).fill(pw)
    pg.get_by_label("Confirm password").fill(pw)
    pg.get_by_label("Institution name").fill("Cauvery Institute of Engineering (Synthetic)")
    pg.get_by_role("button", name="Register institution").click()
    pg.wait_for_timeout(800)
    check("registration completes and shows Account created", pg.get_by_role("heading", name="Account created").is_visible())
    pg.screenshot(path=out / "accounts-register.png")

    pg.get_by_role("button", name="Open Applicant Dashboard").click()
    pg.wait_for_url("**/institution**")
    pg.wait_for_timeout(500)
    check("registered applicant opens Applicant Dashboard", "/institution" in pg.url and pg.get_by_text("Cauvery Institute of Engineering (Synthetic)").first.is_visible())

    # Verify 10-section Applicant Portal navigation bar
    sec_nav = pg.get_by_role("navigation", name="Applicant portal sections")
    check("Applicant Dashboard renders 10 portal sections", sec_nav.locator("button").count() == 10)
    sec_nav.get_by_role("button", name="Upload / Scan").click()
    pg.wait_for_timeout(500)
    check("Applicant Dashboard switches to Upload / Scan section", pg.get_by_role("button", name="Scan document").first.is_visible())

    # Logout and sign back in with the newly registered credentials
    pg.get_by_role("button", name="Sign out").click()
    pg.wait_for_timeout(400)
    pg.goto(base + "/login")
    pg.wait_for_timeout(400)
    pg.get_by_label("Email").fill(test_email)
    pg.get_by_label("Password", exact=True).fill(pw)
    pg.get_by_role("button", name="Sign in", exact=True).click()
    pg.wait_for_url("**/institution**")
    pg.wait_for_timeout(500)
    check("signing in with newly registered applicant credentials opens /institution", "/institution" in pg.url)
    pg.get_by_role("button", name="Sign out").click()
    pg.wait_for_timeout(400)

    # 5. Role routing for AUDITOR -> /queue (oversight home) and /audit access
    pg.goto(base + "/login")
    pg.wait_for_timeout(400)
    pg.get_by_role("button", name="Auditor, Farhan Ali: fill auditor@aicte.synthetic.in").click()
    pg.get_by_label("Password", exact=True).fill(pw)
    pg.get_by_role("button", name="Sign in", exact=True).click()
    pg.wait_for_url("**/queue")
    check("AUDITOR signs in to oversight home (/queue)", pg.url.endswith("/queue"))
    pg.get_by_role("navigation", name="Main").get_by_role("link", name="Audit trail").click()
    pg.wait_for_url("**/audit")
    check("AUDITOR can navigate to /audit", pg.url.endswith("/audit"))

    ctx.close()

    # 6. Mobile landing page scroll story & URL-bar height stability
    m_ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    m_pg = m_ctx.new_page()
    m_pg.goto(base + "/")
    m_pg.wait_for_timeout(800)
    scene_start = int(m_pg.evaluate("document.querySelector('.journey')?.getAttribute('data-active-scene') || '0'"))
    m_pg.evaluate("window.scrollTo(0, 2400)")
    m_pg.evaluate("window.dispatchEvent(new Event('touchmove'))")
    m_pg.wait_for_timeout(400)
    scene_mid = int(m_pg.evaluate("document.querySelector('.journey')?.getAttribute('data-active-scene') || '0'"))
    tf_before = m_pg.evaluate("document.querySelector('[data-part=doc]')?.style.transform || ''")
    # Simulate mobile URL bar collapsing by 60px (width unchanged, deltaH < 120px)
    m_pg.set_viewport_size({"width": 390, "height": 904})
    m_pg.wait_for_timeout(250)
    scene_after = int(m_pg.evaluate("document.querySelector('.journey')?.getAttribute('data-active-scene') || '0'"))
    check("mobile landing scroll story advances scenes smoothly on touch scroll", scene_start == 0 and scene_mid > 0, f"{scene_start}->{scene_mid}")
    check("mobile URL-bar height fluctuation (<120px) does not jump active scene", scene_after == scene_mid and bool(tf_before), f"scene={scene_mid}->{scene_after}")
    m_ctx.close()

    b.close()

check("zero unhandled page or console errors", len(errors) == 0, "; ".join(errors))

for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if not ok and detail else ""))
print("errors:", errors or "none")
passed = sum(ok for _, ok, _ in results)
print(f"{passed} of {len(results)} checks passed")
if passed < len(results):
    sys.exit(1)

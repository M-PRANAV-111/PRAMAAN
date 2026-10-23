"""Sign-in accessibility and flow checks plus screenshots. Usage: python e2e/signin_check.py <base_url> <password> <outdir> (seeded server)"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base, pw, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
results, errors = [], []


def check(name, cond):
    results.append((name, bool(cond)))


def active_id(page):
    return page.evaluate("document.activeElement && document.activeElement.id")


with sync_playwright() as p:
    b = p.chromium.launch()
    c = b.new_context(viewport={"width": 1440, "height": 900})
    pg = c.new_page()
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.on("pageerror", lambda e: errors.append(str(e)))

    pg.goto(base + "/")
    pg.wait_for_timeout(1500)
    pg.screenshot(path=out / "landing-fold.png")
    header_btn = pg.get_by_role("banner").get_by_role("link", name="Sign in", exact=True)
    check("header Sign in visible on the first screen at 1440x900", header_btn.is_visible())

    # Keyboard: first Tab reaches the skip links; "Skip to sign in" opens the dialog with the cursor in the email field.
    pg.keyboard.press("Tab")
    check("first tab stop is Skip to content", pg.evaluate("document.activeElement.textContent") == "Skip to content")
    pg.keyboard.press("Tab")
    check("second tab stop is Skip to sign in", pg.evaluate("document.activeElement.textContent").strip() == "Skip to sign in")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(300)
    check("skip link opens the dialog and focuses email", pg.evaluate("document.querySelector('dialog').open") and active_id(pg) == "signin-email")
    check("demo chips listed in the dialog (9)", pg.locator("dialog li button").count() == 9)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)

    # Header button from deep in the story
    pg.evaluate("window.scrollTo(0, 3000)")
    pg.wait_for_timeout(200)
    header_btn.click()
    pg.wait_for_timeout(400)
    check("header Sign in opens the dialog and focuses email", pg.evaluate("document.querySelector('dialog').open") and active_id(pg) == "signin-email")
    check("URL unchanged after header Sign in", pg.url.rstrip("/") == base.rstrip("/"))

    # Empty submit
    pg.get_by_role("button", name="Sign in", exact=True).click()
    check("empty submit shows email error", pg.get_by_text("Enter your email address.").is_visible())
    check("email marked invalid", pg.get_by_label("Email").get_attribute("aria-invalid") == "true")
    check("focus returns to email", active_id(pg) == "signin-email")
    check("error is in the field's description",
          "signin-email-error" in (pg.get_by_label("Email").get_attribute("aria-describedby") or ""))

    # Chip picks fill email and focus password
    pg.get_by_role("button", name="Scrutiny officer, Ananya Rao: fill officer@aicte.synthetic.in").click()
    check("chip fills email", pg.get_by_label("Email").input_value() == "officer@aicte.synthetic.in")
    check("chip focuses password", active_id(pg) == "signin-password")
    check("chip shows pressed", pg.get_by_role("button", name="Scrutiny officer, Ananya Rao: fill officer@aicte.synthetic.in").get_attribute("aria-pressed") == "true")

    # Show / hide password
    pg.get_by_label("Password", exact=True).fill("abc")
    pg.get_by_role("button", name="Show password").click()
    check("show password reveals text", pg.get_by_label("Password", exact=True).get_attribute("type") == "text")
    pg.get_by_role("button", name="Hide password").click()
    check("hide password masks again", pg.get_by_label("Password", exact=True).get_attribute("type") == "password")

    # Caps Lock hint
    # Headless keyboards do not toggle Caps Lock, so send the key event a browser sends when it is on.
    pg.get_by_label("Password", exact=True).focus()
    pg.evaluate("""document.getElementById('signin-password').dispatchEvent(
        new KeyboardEvent('keyup', {key: 'A', bubbles: true, modifierCapsLock: true}))""")
    pg.wait_for_timeout(150)
    check("Caps Lock hint shown and tied to the password field", "Caps Lock is on." in pg.locator("#signin-caps").inner_text()
          and "signin-caps" in (pg.get_by_label("Password", exact=True).get_attribute("aria-describedby") or ""))
    pg.evaluate("""document.getElementById('signin-password').dispatchEvent(
        new KeyboardEvent('keyup', {key: 'a', bubbles: true, modifierCapsLock: false}))""")
    pg.wait_for_timeout(100)
    check("Caps Lock hint clears", pg.locator("#signin-caps").inner_text() == "")

    # Wrong password
    pg.get_by_label("Password", exact=True).fill("wrong-password")
    pg.get_by_role("button", name="Sign in", exact=True).click()
    alert = pg.get_by_role("alert")
    expect(alert).to_contain_text("incorrect")
    check("wrong password announced in alert", "Check both" in alert.inner_text())
    check("wrong password clears and focuses password", active_id(pg) == "signin-password"
          and pg.get_by_label("Password", exact=True).input_value() == "")
    pg.screenshot(path=out / "landing-error.png")

    # Real sign-in through the landing card
    pg.get_by_label("Password", exact=True).fill(pw)
    pg.keyboard.press("Enter")
    pg.wait_for_url("**/queue")
    pg.wait_for_timeout(800)
    check("Enter key signs in and opens the queue", pg.url.endswith("/queue"))
    pg.screenshot(path=out / "queue.png")
    pg.get_by_role("link", name="Godavari College of Engineering (Synthetic)").click()
    pg.wait_for_timeout(1400)
    pg.screenshot(path=out / "workspace.png")
    pg.goto(base + "/")
    pg.wait_for_timeout(800)
    check("signed-in start page offers the workspace in the header", pg.get_by_role("banner").get_by_role("link", name="Open your workspace").is_visible())
    pg.screenshot(path=out / "landing-signed-in.png")
    pg.get_by_role("banner").get_by_role("link", name="Open your workspace").click()
    pg.wait_for_url("**/queue")
    pg.get_by_role("button", name="Sign out").click()
    pg.wait_for_timeout(500)

    # /login page
    pg.goto(base + "/login?expired=1")
    pg.wait_for_timeout(800)
    check("login page shows session notice", pg.get_by_role("alert").inner_text().startswith("Your session ended"))
    check("login page heading is h1", pg.locator("h1#signin-title").count() == 1)
    pg.screenshot(path=out / "login.png")
    pg.get_by_role("button", name="Deccan Institute of Technology: fill nodal@deccan.synthetic.in").click()
    pg.get_by_label("Password", exact=True).fill(pw)
    pg.get_by_role("button", name="Sign in", exact=True).click()
    pg.wait_for_url("**/institution")
    check("institution chip signs in to institution home", pg.url.endswith("/institution"))
    pg.wait_for_timeout(700)
    pg.screenshot(path=out / "institution.png")

    # Mobile
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
    m.goto(base + "/")
    m.wait_for_timeout(1500)
    m.screenshot(path=out / "m-landing-fold.png")
    m.screenshot(path=out / "m-landing.png", full_page=True)
    check("no horizontal scroll at 390px", m.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    check("header Sign in visible on mobile", m.get_by_role("banner").get_by_role("link", name="Sign in", exact=True).is_visible())
    m.goto(base + "/login")
    m.wait_for_timeout(800)
    m.screenshot(path=out / "m-login.png", full_page=True)

    # Forced colors (Windows High Contrast): dialog and document retain visible borders
    fc = b.new_context(viewport={"width": 1440, "height": 900}, forced_colors="active").new_page()
    fc.goto(base + "/")
    fc.wait_for_timeout(800)
    fc.get_by_role("banner").get_by_role("link", name="Sign in", exact=True).click()
    fc.wait_for_timeout(200)
    check("forced-colors: dialog and document have visible borders",
          fc.evaluate("getComputedStyle(document.querySelector('dialog.signin-dialog')).borderTopWidth === '1px' && getComputedStyle(document.querySelector('.journey-paper')).borderTopWidth === '1px'"))
    b.close()

w = max(len(n) for n, _ in results)
for n, ok in results:
    print(f"{'PASS' if ok else 'FAIL'}  {n}")
print("console/page errors:", [e for e in errors if "401" not in e] or "none (apart from expected 401s)")
print("all 401s:", sum("401" in e for e in errors))

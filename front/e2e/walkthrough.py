"""Browser walkthrough of the main flows with screenshots. Usage: python e2e/walkthrough.py <base_url> <password> <outdir>"""
import sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base, password, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
demo = Path(__import__('os').environ.get('PRAMAAN_DEMO_DIR', str(Path(__file__).resolve().parents[2] / "backend/var/demo_files")))
out.mkdir(parents=True, exist_ok=True)
errors = []

def login(page, email):
    page.goto(base + "/login")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(lambda u: "/login" not in u)

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(base + "/")
    page.wait_for_timeout(1400)
    page.screenshot(path=out / "01-landing.png", full_page=True)

    login(page, "officer@aicte.synthetic.in")
    expect(page.get_by_role("heading", name="Scrutiny queue")).to_be_visible()
    page.wait_for_timeout(400)
    page.screenshot(path=out / "02-queue.png", full_page=True)

    page.get_by_role("link", name="Godavari College of Engineering (Synthetic)").click()
    expect(page.get_by_role("tab", name="Findings (7)")).to_be_visible()
    page.get_by_role("button", name="Integrity indicator").first.click()
    page.wait_for_timeout(1200)
    page.screenshot(path=out / "03-finding-overlay.png", full_page=True)

    page.get_by_role("button", name="Intake is the same in the affidavit").click()
    page.wait_for_timeout(1000)
    page.screenshot(path=out / "04-finding-consistency.png", full_page=False)

    page.get_by_role("radio", name="Ask the institution").check()
    page.get_by_label("Reason (recorded with your name)").fill("Affidavit says 300; AICTE records and the summary say 240. Please clarify.")
    page.get_by_role("button", name="Record decision").click()
    expect(page.get_by_text("Decision recorded in the audit trail")).to_be_visible()

    page.get_by_role("tab", name="Documents").click()
    page.get_by_role("button", name="View what was read").nth(3).click()
    page.wait_for_timeout(1200)
    page.screenshot(path=out / "05-evidence-dialog.png", full_page=False)
    page.get_by_role("button", name="Close").click()

    page.get_by_role("tab", name="What to fix").click()
    page.wait_for_timeout(500)
    page.screenshot(path=out / "06-repair-plan-officer.png", full_page=True)

    page.goto(base + "/audit")
    page.get_by_role("button", name="Verify the chain").click()
    expect(page.get_by_text("Chain intact.")).to_be_visible()
    page.screenshot(path=out / "07-audit.png", full_page=False)

    page.goto(base + "/rules")
    page.wait_for_timeout(500)
    page.screenshot(path=out / "08-rules.png", full_page=False)
    page.goto(base + "/benchmark")
    page.wait_for_timeout(600)
    page.screenshot(path=out / "09-benchmark.png", full_page=True)
    page.get_by_role("button", name="Sign out").click()

    # Institution: create, upload, see findings and plan, fix, submit.
    login(page, "nodal@deccan.synthetic.in")
    page.get_by_role("button", name="Start an application").first.click()
    page.get_by_role("button", name="Create application").click()
    page.wait_for_url("**/applications/**")
    files = {"eoa_letter": "D_EoA_2025-26.pdf", "affidavit": "D_Affidavit_2026-27.pdf", "fire_noc": "D_Fire_NOC_EXPIRED.pdf",
             "building_stability": "D_Structural_Stability.pdf", "faculty_summary": "D_Faculty_Summary_WRONG_INTAKE.pdf",
             "infra_photo": "D_Lab_Photo.png"}
    for doc_type, name in files.items():
        page.set_input_files(f"#up-{doc_type}", str(demo / name))
        page.wait_for_timeout(300)
        if doc_type == "fire_noc":
            page.screenshot(path=out / "10-upload-progress.png", full_page=False)
        expect(page.locator(f"#up-{doc_type}").locator("xpath=..").get_by_text("Replace file")).to_be_visible(timeout=60000)
    page.wait_for_timeout(800)
    page.screenshot(path=out / "11-institution-documents.png", full_page=True)
    page.get_by_role("tab", name="What to fix").click()
    page.wait_for_timeout(700)
    page.screenshot(path=out / "12-institution-plan.png", full_page=True)
    page.get_by_role("tab", name="Documents").click()
    page.set_input_files("#up-fire_noc", str(demo / "D_Fire_NOC_RENEWED.pdf"))
    page.wait_for_timeout(500)
    expect(page.get_by_text("Fire safety NOC checked")).to_be_visible(timeout=60000)
    page.get_by_role("tab", name="Activity").click()
    page.wait_for_timeout(600)
    page.screenshot(path=out / "13-institution-activity.png", full_page=True)
    page.get_by_role("button", name="Submit to AICTE").first.click()
    page.get_by_role("dialog").get_by_role("button", name="Submit to AICTE").click()
    expect(page.get_by_text("Submitted to AICTE").first).to_be_visible()

    mob = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    mp = mob.new_page()
    mp.goto(base + "/")
    mp.wait_for_timeout(1400)
    mp.screenshot(path=out / "14-mobile-landing.png", full_page=True)
    browser.close()

print("console errors:", errors)

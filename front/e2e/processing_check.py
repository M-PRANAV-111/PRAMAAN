"""Tests the in-app document verification processing journey (Section 3 & Section 4).

Uploads a document into an institution application, asserts that the 6-stage ProcessingJourney state machine
renders, shows the stage rail, real page image, extracted claim boxes, and routed outcome card (never using
approve/reject/forged wording), and verifies reduced-motion static rendering.

Usage: python e2e/processing_check.py <base_url> <password> <outdir>
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base, pw, out = sys.argv[1].rstrip("/"), sys.argv[2], Path(sys.argv[3])
demo = Path(__import__('os').environ.get('PRAMAAN_DEMO_DIR', str(Path(__file__).resolve().parents[2] / "backend/var/demo_files")))
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


with sync_playwright() as p:
    b = p.chromium.launch()

    # 1. Standard motion context: upload a document and verify ProcessingJourney stages, claim boxes, and outcome card
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "401" not in m.text and errors.append(m.text))

    login(pg, "nodal@krishna.synthetic.in")
    app_link = pg.locator("a[href^='/applications/']").first
    if app_link.count() > 0:
        app_link.click()
    else:
        pg.get_by_role("button", name="Start an application").first.click()
        pg.get_by_role("button", name="Create application").click()
    pg.wait_for_url("**/applications/**")
    pg.wait_for_timeout(700)

    pg.get_by_role("tab", name="Documents").click()
    pg.wait_for_timeout(400)

    # Upload renewed Fire NOC to trigger the processing journey
    pg.set_input_files("#up-fire_noc", str(demo / "D_Fire_NOC_RENEWED.pdf"))
    journey = pg.get_by_role("region", name="Document verification journey")
    expect(journey).to_be_visible(timeout=15000)
    check("processing-journey region appears on upload", journey.is_visible())

    rail = pg.get_by_role("list", name="Document verification stages")
    check("stage-rail renders 6 ordered steps", rail.locator("li").count() == 6)
    pg.screenshot(path=out / "processing-active.png")

    # Wait for job completion and outcome card
    outcome = pg.locator("[data-outcome-card]")
    expect(outcome).to_be_visible(timeout=60000)
    pg.wait_for_timeout(800)
    check("outcome-card appears when job finishes", outcome.is_visible())

    page_img = pg.get_by_test_id("journey-page-img")
    check("journey sheet renders real first page image", page_img.count() == 1 and page_img.is_visible())

    claim_boxes = pg.locator("[data-claim-box]").count()
    check("journey sheet overlays real extracted claim bounding boxes", claim_boxes >= 1, f"boxes={claim_boxes}")

    outcome_text = outcome.inner_text()
    forbidden = [w for w in ("approved", "rejected", "forged", "fake") if w in outcome_text.lower()]
    check("outcome card uses routing language and never says approved/rejected/forged", len(forbidden) == 0, outcome_text)
    pg.screenshot(path=out / "processing-done.png")

    # Targeted re-validation banner shown when replacing an existing file
    pg.set_input_files("#up-fire_noc", str(demo / "D_Fire_NOC_RENEWED.pdf"))
    pg.wait_for_timeout(400)
    recheck_note = pg.get_by_text("Only the rules that read this document will run again.")
    check("replacing a file shows targeted re-validation notice", recheck_note.is_visible())
    expect(pg.locator("[data-outcome-card]")).to_be_visible(timeout=60000)

    # Camera Document Scanner flow: Scan document -> Capture page -> Rotate -> Submit scan -> ProcessingJourney
    scan_btn = pg.get_by_role("button", name="Scan document").first
    check("Scan document button is visible on checklist slots", scan_btn.is_visible())
    scan_btn.click()
    pg.wait_for_timeout(400)
    capture_btn = pg.get_by_role("button", name="Capture page")
    check("CameraScanner dialog opens with Capture page control", capture_btn.is_visible())
    capture_btn.click()
    pg.wait_for_timeout(300)
    check("capturing a page renders scanner preview image", pg.get_by_test_id("scanner-preview-img").is_visible())
    pg.get_by_role("button", name="Rotate 90° (0°)").click()
    pg.wait_for_timeout(200)
    pg.get_by_role("button", name="Submit scan (1 page)").click()
    expect(pg.get_by_role("region", name="Document verification journey")).to_be_visible(timeout=15000)
    expect(pg.locator("[data-outcome-card]")).to_be_visible(timeout=60000)
    check("submitting a camera-scanned document completes AI verification journey", pg.locator("[data-outcome-card]").is_visible())
    ctx.close()

    # 2. Reduced motion context: static step list without travelling sheet animation
    rm_ctx = b.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    rm_pg = rm_ctx.new_page()
    login(rm_pg, "nodal@krishna.synthetic.in")
    rm_pg.locator("a[href^='/applications/']").first.click()
    rm_pg.wait_for_url("**/applications/**")
    rm_pg.wait_for_timeout(600)
    rm_pg.get_by_role("tab", name="Documents").click()
    rm_pg.set_input_files("#up-affidavit", str(demo / "D_Affidavit_2026-27.pdf"))
    static_journey = rm_pg.get_by_role("region", name="Document verification journey")
    expect(static_journey).to_be_visible(timeout=15000)
    check("prefers-reduced-motion renders static processing journey without animated sheet",
          static_journey.is_visible() and rm_pg.locator("[data-journey-sheet]").count() == 0)
    expect(rm_pg.locator("[data-outcome-card]")).to_be_visible(timeout=60000)
    rm_pg.screenshot(path=out / "processing-reduced-motion.png")
    rm_ctx.close()

    b.close()

check("zero unhandled page or console errors", len(errors) == 0, "; ".join(errors))

for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if not ok and detail else ""))
print("errors:", errors or "none")
passed = sum(ok for _, ok, _ in results)
print(f"{passed} of {len(results)} checks passed")
if passed < len(results):
    sys.exit(1)

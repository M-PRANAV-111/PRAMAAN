"""Tests the institution summary row, readiness progress bar, 'Next step' line, category checklist preview,
queue URL-persisted filters/sorting, 'No open findings' clean case note, side-by-side comparison on
cross-document findings, 8-question ProofChain anatomy, and application activity timeline.

Usage: python e2e/tracking_check.py <base_url> <password> <outdir>
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


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "401" not in m.text and errors.append(m.text))

    # 1. Institution dashboard: summary row, readiness progress bar, next step line, and category checklist preview
    login(pg, "nodal@godavari.synthetic.in")
    summary_row = pg.get_by_role("region", name="Application summary")
    check("institution home renders 4-metric summary row", summary_row.is_visible() and summary_row.locator("> div").count() == 4)

    next_step = pg.get_by_text("Next step:", exact=False).first
    check("institution application card shows Next step line", next_step.is_visible())

    readiness = pg.get_by_role("progressbar", name="Required documents uploaded").first
    check("institution application card shows readiness progressbar", readiness.is_visible())

    pg.get_by_role("button", name="Start an application").first.click()
    pg.wait_for_timeout(300)
    preview = pg.get_by_text("Checklist preview (6 items):", exact=False)
    check("new application form shows category checklist preview (6 items)", preview.is_visible())
    pg.screenshot(path=out / "tracking-institution-start.png")

    # 2. Workspace: activity timeline & Before you upload guidance
    pg.locator("a[href^='/applications/']").first.click()
    pg.wait_for_url("**/applications/**")
    pg.wait_for_timeout(700)
    pg.get_by_role("tab", name="Documents").click()
    pg.wait_for_timeout(400)
    pg.get_by_role("button", name="Before you upload").first.click()
    pg.wait_for_timeout(200)
    check("Before you upload expands common flag guidance", pg.get_by_text("Common reasons this document is flagged:").is_visible())

    pg.get_by_role("tab", name="Activity").click()
    pg.wait_for_timeout(500)
    timeline = pg.locator("h2:has-text('Application timeline') + ol")
    check("Activity tab renders ordered application timeline", timeline.is_visible() and timeline.locator("li").count() >= 2)
    pg.screenshot(path=out / "tracking-timeline.png")

    pg.get_by_role("button", name="Sign out").click()
    pg.wait_for_timeout(400)

    # 3. Officer queue: URL-persisted search, status filter, sortable columns, and 'No open findings' on clean case
    login(pg, "officer@aicte.synthetic.in")
    check("scrutiny queue shows 'No open findings' on clean cases", pg.get_by_text("No open findings").first.is_visible())

    search_input = pg.get_by_label("Search by institution name or Permanent ID")
    search_input.fill("Godavari")
    pg.wait_for_timeout(300)
    check("queue search persists ?q=Godavari in URL", "q=Godavari" in pg.url, pg.url)
    check("queue search filters rows to Godavari", pg.locator("tbody tr").count() == 1)

    search_input.fill("")
    pg.wait_for_timeout(200)
    status_grp = pg.get_by_role("group", name="Filter by status")
    status_grp.get_by_role("button", name="Ready for scrutiny", exact=False).click()
    pg.wait_for_timeout(300)
    check("queue status filter persists ?status=READY_FOR_SCRUTINY in URL", "status=READY_FOR_SCRUTINY" in pg.url, pg.url)
    status_grp.get_by_role("button", name="All (", exact=False).click()
    pg.wait_for_timeout(200)

    pg.get_by_role("button", name="Institution").click()
    pg.wait_for_timeout(200)
    check("queue column sort persists ?sort=institution in URL", "sort=institution" in pg.url, pg.url)
    pg.screenshot(path=out / "tracking-queue.png")

    # 4. Workspace Findings: 8-question ProofChain anatomy and side-by-side comparison for cross-doc findings
    pg.get_by_role("link", name="Godavari College of Engineering (Synthetic)").click()
    pg.wait_for_url("**/applications/**")
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Intake is the same in the affidavit").click()
    pg.wait_for_timeout(600)
    check("Finding header shows What would clear this", pg.get_by_text("What would clear this:", exact=False).first.is_visible())
    check("Finding header shows Resubmission needed", pg.get_by_text("Resubmission needed:", exact=False).first.is_visible())

    sbs_btn = pg.get_by_role("button", name="Compare both documents side by side")
    check("cross-document finding offers side-by-side comparison toggle", sbs_btn.is_visible())
    sbs_btn.click()
    pg.wait_for_timeout(600)
    check("side-by-side mode renders two EvidenceViewer figures", pg.locator("article figure").count() == 2)
    pg.screenshot(path=out / "tracking-side-by-side.png")

    ctx.close()
    b.close()

check("zero unhandled page or console errors", len(errors) == 0, "; ".join(errors))

for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if not ok and detail else ""))
print("errors:", errors or "none")
passed = sum(ok for _, ok, _ in results)
print(f"{passed} of {len(results)} checks passed")
if passed < len(results):
    sys.exit(1)

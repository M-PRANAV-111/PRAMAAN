"""Page length and document size. Usage: python e2e/measure_page.py <base_url>"""
import sys
from playwright.sync_api import sync_playwright

base = sys.argv[1].rstrip("/")
with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h in [(1440, 900), (1280, 720), (1024, 768), (390, 844), (360, 740)]:
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto(base + "/")
        pg.wait_for_timeout(1200)
        r = pg.evaluate("""() => ({ page: document.documentElement.scrollHeight / innerHeight,
          story: document.querySelector('.journey').offsetHeight / innerHeight,
          doc: document.querySelector('[data-part=doc] .journey-paper').offsetWidth })""")
        print(f"{w}x{h}: whole page {r['page']:.1f} screens, story {r['story']:.1f} screens, document {r['doc']} px wide")
        pg.close()
    b.close()

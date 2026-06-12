from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path("_verify"); OUT.mkdir(exist_ok=True)
SAMPLE = str(Path("sample_data/sample_dated.csv").resolve())
BASE = "http://localhost:8000"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width":1200,"height":1100}, device_scale_factor=2).new_page()
    pg.goto(BASE+"/login", wait_until="networkidle")
    pg.fill("input[name=username]","acme"); pg.fill("input[name=password]","acmepass123")
    pg.press("input[name=password]","Enter"); pg.wait_for_load_state("networkidle")
    pg.set_input_files("#file", SAMPLE); pg.click("#submit")
    pg.wait_for_url("**/runs/**", timeout=20000)
    pg.wait_for_selector("text=Emissions over time", timeout=45000)
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(OUT/"report_dated.png"), full_page=True)
    print("shot: report_dated"); b.close()
print("done")

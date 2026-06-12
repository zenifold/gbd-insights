from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path("_verify"); OUT.mkdir(exist_ok=True)
SAMPLE = str(Path.home()/"Downloads"/"riverside_usd_procurement_2026.csv")
BASE="http://localhost:8000"
with sync_playwright() as p:
    b=p.chromium.launch()
    pg=b.new_context(viewport={"width":1200,"height":1100}, device_scale_factor=2).new_page()
    pg.goto(BASE+"/login", wait_until="networkidle")
    pg.fill("input[name=username]","acme"); pg.fill("input[name=password]","acmepass123")
    pg.click("button:has-text('Sign in')")
    try:
        pg.wait_for_selector("text=Upload procurement data", timeout=8000)
    except Exception:
        print("LOGIN_FAILED"); b.close(); raise SystemExit
    pg.set_input_files("#file", SAMPLE); pg.click("#submit")
    pg.wait_for_url("**/runs/**", timeout=20000)
    pg.wait_for_selector("text=Putting it in perspective", timeout=60000)
    pg.wait_for_timeout(600)
    pg.screenshot(path=str(OUT/"report_full.png"), full_page=True)
    print("ok"); b.close()

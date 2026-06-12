from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path("_verify"); OUT.mkdir(exist_ok=True)
BASE="http://localhost:8000"
with sync_playwright() as p:
    b=p.chromium.launch()
    pg=b.new_context(viewport={"width":1200,"height":900}, device_scale_factor=2).new_page()
    pg.goto(BASE+"/login", wait_until="networkidle")
    pg.fill("input[name=username]","acme"); pg.fill("input[name=password]","acmepass123")
    pg.click("button:has-text('Sign in')")
    pg.wait_for_selector("text=Upload procurement data", timeout=15000)
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(OUT/"upload_now.png"), full_page=True)
    print("ok"); b.close()

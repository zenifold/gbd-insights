"""Screenshot the live upload page (proves the served page is styled)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("_verify")
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(
        http_credentials={"username": "analyst", "password": "changeme"},
        viewport={"width": 1100, "height": 1500},
    )
    page = ctx.new_page()
    page.goto("http://localhost:8000/", wait_until="networkidle")
    page.screenshot(path=str(OUT / "ui_upload_live.png"), full_page=True)
    browser.close()
print("saved _verify/ui_upload_live.png")

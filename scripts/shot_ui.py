"""Screenshot the redesigned UI + the new admin upload flow (free-text client + tags)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("_verify")
OUT.mkdir(exist_ok=True)
SAMPLE = str(Path("sample_data/sample.csv").resolve())
BASE = "http://localhost:8000"

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_context(viewport={"width": 1150, "height": 1500}).new_page()

    # 1. Login page (redesigned)
    page.goto(BASE + "/login", wait_until="networkidle")
    page.screenshot(path=str(OUT / "ui2_login.png"), full_page=True)

    # 2. Sign in as GBD admin -> upload page with free-text client + tags
    page.fill("input[name=username]", "gbdadmin")
    page.fill("input[name=password]", "gbdpass123")
    page.press("input[name=password]", "Enter")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(OUT / "ui2_admin_upload.png"), full_page=True)

    # 3. Upload for a brand-new client with a tag
    page.fill("#client-name", "Memorial Hospital")
    page.check('input[name="tags"][value="healthcare"]')
    page.set_input_files("#file", SAMPLE)
    page.click("#submit")
    page.wait_for_url("**/runs/**", timeout=20000)
    page.wait_for_selector("a:has-text('Download report bundle')", timeout=45000)
    page.screenshot(path=str(OUT / "ui2_status.png"), full_page=True)

    # 4. Dashboard (tags shown + tag filter)
    page.goto(BASE + "/dashboard", wait_until="networkidle")
    assert "Memorial Hospital" in page.content()
    assert "Healthcare" in page.content()
    page.screenshot(path=str(OUT / "ui2_dashboard.png"), full_page=True)

    browser.close()
print("UI CHECK PASSED")

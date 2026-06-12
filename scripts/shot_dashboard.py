"""Create a run, then screenshot the admin dashboard + a run detail page."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("_verify")
OUT.mkdir(exist_ok=True)
SAMPLE = str(Path("sample_data/sample.csv").resolve())

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(
        http_credentials={"username": "analyst", "password": "changeme"},
        viewport={"width": 1100, "height": 1400},
    )
    page = ctx.new_page()

    # Create a completed run so the dashboard has fresh data.
    page.goto("http://localhost:8000/", wait_until="networkidle")
    page.select_option("#client", index=1)
    page.set_input_files("#file", SAMPLE)
    page.click("#submit")
    page.wait_for_url("**/runs/**", timeout=20000)
    page.wait_for_selector(".alert-success", timeout=45000)

    page.goto("http://localhost:8000/dashboard", wait_until="networkidle")
    page.screenshot(path=str(OUT / "ui_dashboard.png"), full_page=True)
    print("saved ui_dashboard.png")

    href = page.get_attribute("a[href*='/dashboard/runs/']", "href")
    page.goto("http://localhost:8000" + href, wait_until="networkidle")
    page.screenshot(path=str(OUT / "ui_run_detail.png"), full_page=True)
    print("saved ui_run_detail.png")

    browser.close()

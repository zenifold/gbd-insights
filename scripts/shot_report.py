"""Upload a file end-to-end and capture the new in-app report + progress UI."""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("_verify"); OUT.mkdir(exist_ok=True)
SAMPLE = str(Path("sample_data/sample.csv").resolve())
BASE = "http://localhost:8000"


def set_dark(page, dark):
    cur = page.evaluate("document.documentElement.getAttribute('data-theme')")
    if cur != ("gbd-dark" if dark else "gbd"):
        page.click("#theme-toggle"); page.wait_for_timeout(250)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1200, "height": 1000}, device_scale_factor=2).new_page()

    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill("input[name=username]", "acme")
    page.fill("input[name=password]", "acmepass123")
    page.press("input[name=password]", "Enter")
    page.wait_for_load_state("networkidle")

    # Upload the sample file
    page.set_input_files("#file", SAMPLE)
    page.click("#submit")

    # Wait for the report (DONE state renders the KPI tiles + category bars)
    page.wait_for_url("**/runs/**", timeout=20000)
    page.wait_for_selector("text=Emissions by category", timeout=45000)
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "report_light.png"), full_page=True)
    print("shot: report_light")

    set_dark(page, True)
    page.screenshot(path=str(OUT / "report_dark.png"), full_page=True)
    print("shot: report_dark")

    browser.close()
print("done")

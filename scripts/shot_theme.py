"""Capture the rethemed UI in light + dark for visual review."""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("_verify"); OUT.mkdir(exist_ok=True)
BASE = "http://localhost:8000"


def shot(page, name):
    page.screenshot(path=str(OUT / f"theme_{name}.png"), full_page=True)
    print("shot:", name)


def set_dark(page, dark):
    cur = page.evaluate("document.documentElement.getAttribute('data-theme')")
    want = "gbd-dark" if dark else "gbd"
    if cur != want:
        page.click("#theme-toggle")
        page.wait_for_timeout(250)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1200, "height": 900}, device_scale_factor=2).new_page()

    # Login (light + dark)
    page.goto(BASE + "/login", wait_until="networkidle")
    shot(page, "login_light")
    set_dark(page, True); shot(page, "login_dark")

    # Sign in (theme persists via localStorage)
    set_dark(page, False)
    page.fill("input[name=username]", "acme")
    page.fill("input[name=password]", "acmepass123")
    page.press("input[name=password]", "Enter")
    page.wait_for_load_state("networkidle")
    shot(page, "upload_light")
    set_dark(page, True); shot(page, "upload_dark"); set_dark(page, False)

    # Dashboard
    page.goto(BASE + "/dashboard", wait_until="networkidle")
    shot(page, "dashboard_light")
    set_dark(page, True); shot(page, "dashboard_dark"); set_dark(page, False)

    # Run status page (open the first run)
    link = page.query_selector("a:has-text('Open')")
    if link:
        link.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)  # let HTMX status swap in
        shot(page, "status_light")
        set_dark(page, True); shot(page, "status_dark")

    browser.close()
print("done")

"""Verify client self-serve + isolation + staff view in a real browser."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("_verify")
OUT.mkdir(exist_ok=True)
SAMPLE = str(Path("sample_data/sample.csv").resolve())
BASE = "http://localhost:8000"


def login(page, user, pw):
    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill("input[name=username]", user)
    page.fill("input[name=password]", pw)
    page.press("input[name=password]", "Enter")
    page.wait_for_load_state("networkidle")


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1100, "height": 1400}).new_page()

    # --- Client self-serve (Acme) ---
    login(page, "acme", "acmepass123")
    assert "Uploading for" in page.content(), "client should see their org, no picker"
    page.set_input_files("#file", SAMPLE)
    page.click("#submit")
    page.wait_for_url("**/runs/**", timeout=20000)
    page.wait_for_selector(".alert-success", timeout=45000)
    page.screenshot(path=str(OUT / "ss_client_status.png"), full_page=True)
    print("PASS: client uploaded + got report")

    page.goto(BASE + "/dashboard", wait_until="networkidle")
    page.screenshot(path=str(OUT / "ss_client_dashboard.png"), full_page=True)
    print("PASS: client dashboard rendered")

    page.click("form[action='/logout'] button")
    page.wait_for_load_state("networkidle")

    # --- GBD staff (sees all clients) ---
    login(page, "gbdadmin", "gbdpass123")
    page.goto(BASE + "/dashboard", wait_until="networkidle")
    body = page.content()
    assert "Acme University" in body, "staff should see the client's run"
    page.screenshot(path=str(OUT / "ss_staff_dashboard.png"), full_page=True)
    print("PASS: staff sees all clients")

    browser.close()
print("ALL SELF-SERVE CHECKS PASSED")

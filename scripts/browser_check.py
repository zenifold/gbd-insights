"""
Headless end-to-end UI check (not part of the app).

Drives the real browser flow against a running dev server: logs in via Basic
Auth, uploads the sample file through the page's JavaScript (create-run ->
direct PUT -> finalize), waits for HTMX polling to report completion, and
asserts the result metrics render. Saves screenshots to _verify/.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = Path("_verify")
OUT.mkdir(exist_ok=True)
SAMPLE = str(Path("sample_data/sample.csv").resolve())


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            http_credentials={"username": "analyst", "password": "changeme"},
            viewport={"width": 1100, "height": 1500},
        )
        page = ctx.new_page()

        page.goto(BASE + "/", wait_until="networkidle")
        assert "Upload procurement data" in page.content()
        assert "How should my file be formatted?" in page.content()
        page.screenshot(path=str(OUT / "ui_upload.png"), full_page=True)
        print("PASS: upload page + format guide rendered")

        page.select_option("#client", index=1)
        page.set_input_files("#file", SAMPLE)
        page.click("#submit")

        page.wait_for_url("**/runs/**", timeout=20000)
        page.wait_for_selector(".alert-success", timeout=45000)
        body = page.content()
        for needle in ["Total emissions", "Beef", "Download report bundle"]:
            assert needle in body, f"missing on status page: {needle!r}"
        page.screenshot(path=str(OUT / "ui_status_done.png"), full_page=True)
        print("PASS: JS upload -> worker -> status metrics + caveats rendered")

        browser.close()
    print("ALL BROWSER CHECKS PASSED")


if __name__ == "__main__":
    main()

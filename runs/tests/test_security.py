from urllib.parse import urlsplit

from runs.validation import validate_upload


def test_rejects_xlsx_zip_bomb(tmp_path, settings):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["product", "spend"])
    ws.append(["Beef", 100])
    path = tmp_path / "b.xlsx"
    wb.save(path)

    settings.MAX_XLSX_UNCOMPRESSED_BYTES = 10  # any real xlsx exceeds this
    result = validate_upload(path, "b.xlsx", path.stat().st_size)
    assert not result.ok
    assert result.error_code == "xlsx_too_large_uncompressed"


def test_storage_upload_enforces_size_cap(staff_client, demo_client, settings):
    settings.MAX_UPLOAD_BYTES = 5
    resp = staff_client.post(
        "/runs",
        {"client_id": str(demo_client.id), "filename": "s.csv", "content_type": "text/csv"},
    )
    target = urlsplit(resp.json()["upload"]["url"])
    resp = staff_client.put(
        f"{target.path}?{target.query}",
        data=b"this body is way more than five bytes",
        content_type="text/csv",
    )
    assert resp.status_code == 413

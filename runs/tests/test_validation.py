from pathlib import Path

from runs.validation import validate_upload

SAMPLE = Path(__file__).resolve().parents[2] / "sample_data" / "sample.csv"


def test_accepts_valid_csv():
    result = validate_upload(SAMPLE, "sample.csv", SAMPLE.stat().st_size)
    assert result.ok
    assert result.error_code == ""


def test_accepts_synonym_columns(tmp_path):
    f = tmp_path / "syn.csv"
    f.write_text("supplier,item,amount\nSysco,Cheddar Cheese,500\n")
    result = validate_upload(f, "syn.csv", f.stat().st_size)
    assert result.ok


def test_rejects_bad_extension(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("product,spend\nBeef,100\n")
    result = validate_upload(f, "data.txt", f.stat().st_size)
    assert not result.ok
    assert result.error_code == "bad_extension"
    assert ".txt" in result.message


def test_rejects_too_large(settings):
    settings.MAX_UPLOAD_BYTES = 10
    result = validate_upload(SAMPLE, "sample.csv", SAMPLE.stat().st_size)
    assert not result.ok
    assert result.error_code == "too_large"
    assert "limit" in result.message.lower()


def test_rejects_missing_product(tmp_path):
    f = tmp_path / "noprod.csv"
    f.write_text("vendor,spend\nUS Foods,100\n")
    result = validate_upload(f, "noprod.csv", f.stat().st_size)
    assert not result.ok
    assert result.error_code == "missing_product"


def test_rejects_missing_value_column(tmp_path):
    f = tmp_path / "noval.csv"
    f.write_text("vendor,product\nUS Foods,Beef\n")
    result = validate_upload(f, "noval.csv", f.stat().st_size)
    assert not result.ok
    assert result.error_code == "missing_value_column"


def test_rejects_empty_file(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("product,spend\n")  # header only, no data rows
    result = validate_upload(f, "empty.csv", f.stat().st_size)
    assert not result.ok
    assert result.error_code == "empty"


def test_rejects_no_header(tmp_path):
    f = tmp_path / "blank.csv"
    f.write_text("")
    result = validate_upload(f, "blank.csv", f.stat().st_size)
    assert not result.ok
    assert result.error_code == "no_header"


def test_accepts_valid_xlsx(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["vendor", "product", "spend"])
    ws.append(["US Foods", "Beef", 100])
    path = tmp_path / "data.xlsx"
    wb.save(path)
    result = validate_upload(path, "data.xlsx", path.stat().st_size)
    assert result.ok

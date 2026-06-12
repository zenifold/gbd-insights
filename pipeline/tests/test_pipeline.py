import zipfile
from pathlib import Path

from pipeline import run_pipeline

SAMPLE = Path(__file__).resolve().parents[2] / "sample_data" / "sample.csv"


def test_produces_bundle_and_summary(tmp_path):
    result = run_pipeline(SAMPLE, tmp_path)

    assert result.artifact_path.name == "report_bundle.zip"
    assert result.artifact_path.exists()
    assert result.summary["line_items"] == 8
    assert result.summary["uncategorized_items"] == 0
    assert result.summary["top_category"] == "Beef"
    assert result.summary["total_emissions_kgco2e"] > 0

    with zipfile.ZipFile(result.artifact_path) as zf:
        names = set(zf.namelist())
        pdf = zf.read("report.pdf")
    assert {
        "report.pdf",
        "line_items_categorized.csv",
        "aggregates_by_category.csv",
        "summary.json",
        "manifest.json",
    } <= names
    assert pdf.startswith(b"%PDF")


def test_outputs_are_reproducible(tmp_path):
    a = run_pipeline(SAMPLE, tmp_path / "a")
    b = run_pipeline(SAMPLE, tmp_path / "b")

    for f in [
        "line_items_categorized.csv",
        "aggregates_by_category.csv",
        "summary.json",
        "manifest.json",
    ]:
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes(), f

    # Same input + config -> byte-identical bundle.
    assert a.artifact_path.read_bytes() == b.artifact_path.read_bytes()


def test_ingests_xlsx(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["vendor", "product", "spend", "quantity", "unit"])
    ws.append(["US Foods", "Ground Beef", 1000, 100, "lb"])
    path = tmp_path / "in.xlsx"
    wb.save(path)

    result = run_pipeline(path, tmp_path / "out")
    assert result.summary["line_items"] == 1
    assert result.summary["top_category"] == "Beef"


def test_handles_synonym_columns(tmp_path):
    # 'item' and 'amount' instead of 'product'/'spend'.
    src = tmp_path / "syn.csv"
    src.write_text("supplier,item,amount\nSysco,Cheddar Cheese,500\n")
    result = run_pipeline(src, tmp_path / "out")
    assert result.summary["line_items"] == 1
    assert result.summary["top_category"] == "Cheese"

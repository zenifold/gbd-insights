import zipfile

from pipeline import run_pipeline


def test_csv_injection_is_neutralized(tmp_path):
    src = tmp_path / "evil.csv"
    src.write_text(
        'product,spend\n'
        '=HYPERLINK("http://evil"),100\n'
        '@SUM(1+1),50\n'
        '+1234,25\n'
    )
    result = run_pipeline(src, tmp_path / "out")

    with zipfile.ZipFile(result.artifact_path) as zf:
        content = zf.read("line_items_categorized.csv").decode()

    # Formula-triggering product cells are prefixed with a quote so a spreadsheet
    # app won't execute them on open.
    assert "'=HYPERLINK" in content
    assert "'@SUM" in content
    assert "'+1234" in content

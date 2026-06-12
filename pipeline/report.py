"""
Step 6 — Report.

Write the reproducible output set into ``workdir`` and bundle it into a single
deterministic ZIP that GBD can drop into their workflows:

  report.pdf                  human-readable report (tables + charts)
  line_items_categorized.csv  full auditable ETL output (one row per line item)
  aggregates_by_category.csv  emissions/spend per category
  aggregates_by_period.csv    emissions/spend per period (if a date column exists)
  top_products.csv            top emitting products
  summary.json                machine-readable headline digest
  data_quality.json           rows dropped/flagged, detected columns, warnings
  manifest.json               provenance: input hash, factor version, output hashes

Reproducibility: identical input + config -> byte-identical data files (and, with
reportlab's invariant mode + fixed zip timestamps, a byte-identical bundle).
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd
from reportlab import rl_config

# Deterministic PDFs: fixed document id + timestamps.
rl_config.invariant = 1

from reportlab.graphics.charts.barcharts import VerticalBarChart  # noqa: E402
from reportlab.graphics.shapes import Drawing, String  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import LETTER  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .aggregate import Aggregates
from .clean import CleanResult
from .config import PIPELINE_VERSION, factor_version, factors

DATA_FILES = [
    "line_items_categorized.csv",
    "aggregates_by_category.csv",
    "aggregates_by_period.csv",
    "top_products.csv",
    "summary.json",
    "data_quality.json",
]
BUNDLE_ORDER = DATA_FILES + ["manifest.json", "report.pdf"]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Cells beginning with these can be interpreted as formulas by Excel/Sheets when
# the exported CSV is opened — a code-execution / data-exfiltration vector (CSV
# injection). Product/vendor text comes from untrusted uploads, so we neutralize
# it by prefixing a single quote (OWASP guidance).
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")


def _escape_csv_cell(value):
    if isinstance(value, str) and value[:1] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


def _sanitize_csv(df: pd.DataFrame) -> pd.DataFrame:
    from pandas.api.types import is_object_dtype, is_string_dtype

    out = df.copy()
    for col in out.columns:
        # Text columns only (object or pandas StringDtype); never numeric data.
        if is_string_dtype(out[col]) or is_object_dtype(out[col]):
            out[col] = out[col].map(_escape_csv_cell)
    return out


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    safe = _sanitize_csv(df)
    path.write_text(safe.to_csv(index=False, lineterminator="\n", float_format="%.4f"),
                    encoding="utf-8")


def _write_json(obj, path: Path) -> None:
    path.write_text(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _records(df: pd.DataFrame, round_cols: dict[str, int]) -> list[dict]:
    out = df.copy()
    for col, n in round_cols.items():
        if col in out.columns:
            out[col] = out[col].astype(float).round(n)
    return json.loads(out.to_json(orient="records"))


def _money(x) -> str:
    try:
        return f"${float(x):,.0f}"
    except (TypeError, ValueError):
        return "-"


def _num(x, n=0) -> str:
    try:
        return f"{float(x):,.{n}f}"
    except (TypeError, ValueError):
        return "-"


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def _emissions_bar_chart(by_category: pd.DataFrame, max_bars: int = 8) -> Drawing:
    top = by_category.head(max_bars)
    labels = list(top["category_label"])
    values = [float(v) for v in top["emissions_kgco2e"]]

    d = Drawing(460, 200)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.height, chart.width = 30, 20, 150, 410
    chart.data = [values] if values else [[0]]
    chart.categoryAxis.categoryNames = labels or [""]
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.dy = -8
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = colors.HexColor("#2f855a")
    d.add(chart)
    d.add(String(30, 188, "Emissions by category (kg CO₂e)", fontSize=9,
                 fillColor=colors.HexColor("#333333")))
    return d


def _table(header: list[str], rows: list[list[str]], col_widths=None) -> Table:
    data = [header] + rows
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f855a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f4")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ])
    )
    return t


def _build_pdf(path: Path, agg: Aggregates, clean: CleanResult) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(path), pagesize=LETTER, title="GBD Foodservice Insights",
        author="Greener by Default", leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
    )
    story = []
    t = agg.totals

    story.append(Paragraph("Greener by Default", styles["Title"]))
    story.append(Paragraph("Foodservice Procurement Insights", styles["Heading2"]))
    story.append(Spacer(1, 10))

    # Headline metrics.
    metrics = _table(
        ["Metric", "Value"],
        [
            ["Total emissions", f"{_num(t['total_emissions_kgco2e'])} kg CO₂e "
                                 f"({_num(t['total_emissions_tonnes'], 2)} t)"],
            ["Total spend", _money(t["total_spend_usd"])],
            ["Emissions intensity", f"{_num(t['emissions_intensity_kgco2e_per_usd'], 3)} kg CO₂e / $"],
            ["Line items analyzed", _num(t["line_items"])],
            ["Top category", f"{t['top_category']} ({_num(t['top_category_share_pct'],1)}% of emissions)"],
            ["Uncategorized items", _num(t["uncategorized_items"])],
        ],
        col_widths=[2.2 * inch, 3.8 * inch],
    )
    story.append(metrics)
    story.append(Spacer(1, 16))

    # Chart.
    if not agg.by_category.empty:
        story.append(_emissions_bar_chart(agg.by_category))
        story.append(Spacer(1, 10))

    # By-category table.
    story.append(Paragraph("Emissions by category", styles["Heading3"]))
    rows = [
        [r["category_label"], _num(r["line_items"]), _money(r["spend"]),
         _num(r["emissions_kgco2e"])]
        for _, r in agg.by_category.iterrows()
    ]
    story.append(_table(["Category", "Items", "Spend", "kg CO₂e"], rows,
                        col_widths=[2.4 * inch, 0.9 * inch, 1.3 * inch, 1.4 * inch]))
    story.append(Spacer(1, 14))

    # Top products.
    story.append(Paragraph("Top emitting products", styles["Heading3"]))
    rows = [
        [str(r["product"])[:48], str(r["category_label"]), _num(r["emissions_kgco2e"])]
        for _, r in agg.top_products.iterrows()
    ]
    story.append(_table(["Product", "Category", "kg CO₂e"], rows,
                        col_widths=[3.2 * inch, 1.5 * inch, 1.3 * inch]))
    story.append(Spacer(1, 14))

    # Period table.
    if not agg.by_period.empty:
        story.append(Paragraph("Emissions by period", styles["Heading3"]))
        rows = [
            [str(r["period"]), _money(r["spend"]), _num(r["emissions_kgco2e"])]
            for _, r in agg.by_period.iterrows()
        ]
        story.append(_table(["Period", "Spend", "kg CO₂e"], rows,
                            col_widths=[2.0 * inch, 1.5 * inch, 1.4 * inch]))
        story.append(Spacer(1, 14))

    # Caveats & methodology.
    story.append(Paragraph("Caveats & methodology", styles["Heading3"]))
    notes = list(clean.quality.get("warnings", []))
    notes.append(
        "Emission factors are PLACEHOLDERS (factor set "
        f"'{factor_version()}'): per-kg midpoints from Poore &amp; Nemecek (2018) and "
        "rough spend-based fallbacks. Replace with GBD's validated factors before "
        "external use."
    )
    notes.append(
        "Each line item is mapped to one category by keyword rules; where mass could "
        "be derived from quantity x unit it is used, otherwise emissions fall back to "
        "a spend-based factor."
    )
    for n in notes:
        story.append(Paragraph(f"• {n}", styles["BodyText"]))

    doc.build(story)


# --------------------------------------------------------------------------
# Orchestration of outputs
# --------------------------------------------------------------------------
def build_report(
    workdir: Path,
    line_items: pd.DataFrame,
    agg: Aggregates,
    clean: CleanResult,
    *,
    input_path: Path,
    input_sha256: str,
    top_n: int,
) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)

    li_cols = ["date", "period", "vendor", "product", "category", "category_label",
               "quantity", "unit", "mass_kg", "spend", "emissions_kgco2e", "emissions_method"]
    _write_csv(line_items[li_cols], workdir / "line_items_categorized.csv")
    _write_csv(agg.by_category, workdir / "aggregates_by_category.csv")
    _write_csv(agg.by_period, workdir / "aggregates_by_period.csv")
    _write_csv(agg.top_products, workdir / "top_products.csv")

    summary = {
        "totals": agg.totals,
        "by_category": _records(agg.by_category, {"spend": 2, "mass_kg": 2, "emissions_kgco2e": 2}),
        "by_period": _records(agg.by_period, {"spend": 2, "emissions_kgco2e": 2}),
        "top_products": _records(agg.top_products, {"spend": 2, "emissions_kgco2e": 2}),
        "factor_version": factor_version(),
        "pipeline_version": PIPELINE_VERSION,
        "factor_disclaimer": factors().get("_comment", ""),
    }
    _write_json(summary, workdir / "summary.json")
    _write_json(clean.quality, workdir / "data_quality.json")

    _build_pdf(workdir / "report.pdf", agg, clean)

    # Manifest with per-output hashes for provenance / reproducibility checks.
    output_hashes = {}
    for name in DATA_FILES + ["report.pdf"]:
        output_hashes[name] = _sha256_bytes((workdir / name).read_bytes())
    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "factor_version": factor_version(),
        "input_filename": input_path.name,
        "input_sha256": input_sha256,
        "rows_in": clean.quality["rows_in"],
        "rows_used": clean.quality["rows_used"],
        "params": {"top_n": top_n},
        "output_sha256": output_hashes,
    }
    _write_json(manifest, workdir / "manifest.json")

    # Deterministic ZIP (sorted entries, fixed timestamps).
    bundle = workdir / "report_bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in BUNDLE_ORDER:
            info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, (workdir / name).read_bytes())
    return bundle

"""
Orchestrates the full ETL: ingest -> clean -> categorize -> emissions ->
aggregate -> report. Pure and deterministic given the same input + config.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Callable

import pandas as pd

from .aggregate import Aggregates, aggregate
from .categorize import categorize
from .clean import clean as clean_step
from .config import factor_source, factor_version
from .emissions import apply_emissions
from .ingest import ingest
from .interface import PipelineResult
from .report import build_report

# Stage label + cumulative percent-complete at the *end* of that stage. Tuned so
# the bar advances steadily; the heavier stages (emissions, report) get more room.
ProgressFn = Callable[[int, str], None]


def _round(x, n=2):
    try:
        f = float(x)
        return round(f, n) if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _category_records(agg: Aggregates, total_emissions: float) -> list[dict]:
    rows = []
    for _, r in agg.by_category.iterrows():
        em = _round(r["emissions_kgco2e"])
        rows.append(
            {
                "label": str(r["category_label"]),
                "line_items": int(r["line_items"]),
                "spend_usd": _round(r["spend"]),
                "mass_kg": _round(r["mass_kg"]),
                "emissions_kgco2e": em,
                "share_pct": _round(em / total_emissions * 100, 1) if total_emissions > 0 else 0.0,
            }
        )
    return rows


def _product_records(agg: Aggregates, total_emissions: float) -> list[dict]:
    rows = []
    for _, r in agg.top_products.iterrows():
        em = _round(r["emissions_kgco2e"])
        rows.append(
            {
                "product": str(r["product"]),
                "category": str(r["category_label"]),
                "spend_usd": _round(r["spend"]),
                "emissions_kgco2e": em,
                "share_pct": _round(em / total_emissions * 100, 1) if total_emissions > 0 else 0.0,
            }
        )
    return rows


def _period_records(agg: Aggregates) -> list[dict]:
    if agg.by_period.empty:
        return []
    peak = float(agg.by_period["emissions_kgco2e"].max()) or 0.0
    rows = []
    for _, r in agg.by_period.iterrows():
        em = _round(r["emissions_kgco2e"])
        rows.append(
            {
                "period": str(r["period"]),
                "line_items": int(r["line_items"]),
                "spend_usd": _round(r["spend"]),
                "emissions_kgco2e": em,
                "share_pct": _round(em / peak * 100, 1) if peak > 0 else 0.0,
            }
        )
    return rows


def run_pipeline(
    input_path, workdir, *, top_n: int = 10, on_progress: ProgressFn | None = None
) -> PipelineResult:
    """
    Run the full analysis. ``on_progress(percent, message)`` is invoked after each
    stage when supplied; it has no effect on the (deterministic) output bundle.
    """
    input_path = Path(input_path)
    workdir = Path(workdir)

    def progress(pct: int, msg: str) -> None:
        if on_progress is not None:
            on_progress(pct, msg)

    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()

    progress(8, "Reading file")
    ingested = ingest(input_path)

    progress(22, "Cleaning & validating rows")
    cleaned = clean_step(ingested)

    progress(40, "Categorizing products")
    df = categorize(cleaned.df)

    progress(60, "Calculating emissions")
    df = apply_emissions(df)

    progress(76, "Aggregating results")
    agg = aggregate(df, top_n=top_n)

    progress(88, "Building report bundle")
    bundle = build_report(
        workdir, df, agg, cleaned,
        input_path=input_path, input_sha256=input_sha256, top_n=top_n,
    )

    summary = dict(agg.totals)
    summary["source_file"] = input_path.name
    summary["factor_version"] = factor_version()
    summary["factor_source"] = factor_source()
    # Breakdowns for the in-app report view (JSON-safe records).
    total_em = float(agg.totals.get("total_emissions_kgco2e", 0.0))
    summary["by_category"] = _category_records(agg, total_em)
    summary["top_products"] = _product_records(agg, total_em)
    summary["by_period"] = _period_records(agg)

    progress(100, "Complete")
    return PipelineResult(
        artifact_path=bundle, summary=summary, warnings=list(cleaned.quality["warnings"])
    )

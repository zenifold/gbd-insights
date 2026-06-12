"""
Orchestrates the full ETL: ingest -> clean -> categorize -> emissions ->
aggregate -> report. Pure and deterministic given the same input + config.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .aggregate import aggregate
from .categorize import categorize
from .clean import clean as clean_step
from .emissions import apply_emissions
from .ingest import ingest
from .interface import PipelineResult
from .report import build_report


def run_pipeline(input_path, workdir, *, top_n: int = 10) -> PipelineResult:
    input_path = Path(input_path)
    workdir = Path(workdir)
    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()

    ingested = ingest(input_path)
    cleaned = clean_step(ingested)
    df = categorize(cleaned.df)
    df = apply_emissions(df)
    agg = aggregate(df, top_n=top_n)

    bundle = build_report(
        workdir, df, agg, cleaned,
        input_path=input_path, input_sha256=input_sha256, top_n=top_n,
    )

    summary = dict(agg.totals)
    summary["source_file"] = input_path.name
    return PipelineResult(
        artifact_path=bundle, summary=summary, warnings=list(cleaned.quality["warnings"])
    )

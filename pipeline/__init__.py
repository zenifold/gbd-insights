"""
The food-procurement analysis pipeline (real ETL).

The worker depends only on :func:`run_pipeline` and :class:`PipelineResult`.
Pipeline stages live in their own modules (ingest, clean, categorize, emissions,
aggregate, report); the science is data-driven via :mod:`pipeline.config`
(``pipeline/data/*.json``) so GBD can update the taxonomy and emission factors
without touching code.
"""
from .interface import PipelineResult
from .pipeline import run_pipeline

__all__ = ["run_pipeline", "PipelineResult"]

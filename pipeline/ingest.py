"""
Step 1 — Ingest.

Read a CSV or XLSX procurement file into a normalized DataFrame with canonical
column names, mapping common header synonyms so GBD's varied source files work
without hand-editing. Returns the frame plus the detected mapping and any
unmapped columns (surfaced later in the data-quality report).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# Canonical columns, in priority order (a source header is claimed by the first
# canonical that lists it as a synonym).
CANONICAL = ["date", "vendor", "product", "category", "quantity", "unit", "spend"]

SYNONYMS = {
    "product": ["product", "item", "description", "product_description", "item_description",
                "line_item", "material", "name", "product_name"],
    "spend": ["spend", "amount", "cost", "total", "total_cost", "total_spend", "price",
              "extended_price", "ext_price", "dollars", "usd", "net_amount"],
    "quantity": ["quantity", "qty", "units", "count", "cases", "pack_qty"],
    "unit": ["unit", "uom", "unit_of_measure", "measure", "pack_size", "size"],
    "vendor": ["vendor", "supplier", "distributor", "manufacturer", "mfg"],
    "date": ["date", "order_date", "invoice_date", "period", "month", "week",
             "purchase_date", "transaction_date"],
    "category": ["category", "gbd_category", "food_category", "commodity"],
}


@dataclass
class IngestResult:
    df: pd.DataFrame
    mapping: dict = field(default_factory=dict)       # canonical -> original header
    unmapped_columns: list = field(default_factory=list)


def _read(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if ext == ".xlsx":
        return pd.read_excel(path, dtype=str, engine="openpyxl")
    raise ValueError(f"Unsupported file type: {ext}")


def detect_columns(headers) -> dict[str, str]:
    """Map source headers to canonical columns via synonyms (first claim wins)."""
    norm = {col: str(col).strip().lower().replace(" ", "_") for col in headers}
    mapping: dict[str, str] = {}
    claimed: set[str] = set()
    for canonical in CANONICAL:
        for original, key in norm.items():
            if original in claimed:
                continue
            if key in SYNONYMS.get(canonical, []) or key == canonical:
                mapping[canonical] = original
                claimed.add(original)
                break
    return mapping


def ingest(path: Path) -> IngestResult:
    raw = _read(path)
    mapping = detect_columns(raw.columns)
    claimed = set(mapping.values())

    out = pd.DataFrame()
    for canonical in CANONICAL:
        if canonical in mapping:
            out[canonical] = raw[mapping[canonical]].astype(str)
        else:
            out[canonical] = pd.Series([None] * len(raw), dtype="object")

    unmapped = [str(c) for c in raw.columns if c not in claimed]
    return IngestResult(df=out, mapping=mapping, unmapped_columns=unmapped)

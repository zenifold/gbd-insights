"""
Step 2 — Clean & validate.

Coerce money/quantity to numbers, normalize units, derive a mass in kg where
possible, parse a reporting period from any date column, drop unusable rows, and
emit a data-quality report. Deterministic: no randomness, stable row order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import units as units_map
from .config import volume_units as volume_units_map
from .ingest import IngestResult


@dataclass
class CleanResult:
    df: pd.DataFrame
    quality: dict = field(default_factory=dict)


def _to_number(value) -> float:
    if value is None:
        return np.nan
    text = str(value).strip().replace(",", "").replace("$", "").replace("USD", "").strip()
    if text.lower() in ("", "-", "none", "nan", "null", "na"):
        return np.nan
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        number = float(text)
    except ValueError:
        return np.nan
    return -number if negative else number


def _norm_unit(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def clean(ingested: IngestResult) -> CleanResult:
    df = ingested.df.copy()
    rows_in = len(df)
    umap = units_map()
    vmap = volume_units_map()

    df["product"] = df["product"].map(lambda v: (str(v).strip() if v is not None else ""))
    df["vendor"] = df["vendor"].map(lambda v: (str(v).strip() if v is not None else ""))
    df["spend"] = df["spend"].map(_to_number)
    df["quantity"] = df["quantity"].map(_to_number)
    df["unit"] = df["unit"].map(_norm_unit)

    # Reporting period from any date column.
    parsed_date = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    has_period = bool(parsed_date.notna().any())
    df["period"] = parsed_date.dt.strftime("%Y-%m") if has_period else None

    # Mass in kg where unit is a known mass unit.
    def _mass(row):
        q, u = row["quantity"], row["unit"]
        if pd.notna(q) and u in umap:
            return q * umap[u]
        return np.nan

    df["mass_kg"] = df.apply(_mass, axis=1)

    # Volume in liters where unit is a known volume unit (converted to mass via a
    # per-category density downstream in the emissions step).
    def _volume(row):
        q, u = row["quantity"], row["unit"]
        if pd.notna(q) and u in vmap:
            return q * vmap[u]
        return np.nan

    df["volume_l"] = df.apply(_volume, axis=1)

    # Drop rows with no product description (unusable).
    missing_product = df["product"].str.len() == 0
    dropped = int(missing_product.sum())
    df = df.loc[~missing_product].reset_index(drop=True)

    unquantified = int(
        (df["spend"].isna() & df["mass_kg"].isna() & df["volume_l"].isna()).sum()
    )
    unknown_units = sorted(
        {u for u in df["unit"].dropna().unique() if u not in umap and u not in vmap}
    )

    warnings: list[str] = []
    if dropped:
        warnings.append(f"{dropped} row(s) had no product description and were skipped.")
    if unquantified:
        warnings.append(
            f"{unquantified} row(s) had neither spend nor a recognized mass and could not be quantified."
        )
    if "product" not in ingested.mapping:
        warnings.append("No product/description column was detected — results may be unreliable.")
    if "spend" not in ingested.mapping and "quantity" not in ingested.mapping:
        warnings.append("No spend or quantity column was detected — emissions cannot be computed.")
    if not has_period:
        warnings.append("No usable date column was found; the report covers a single combined period.")

    quality = {
        "rows_in": rows_in,
        "rows_used": int(len(df)),
        "rows_dropped": dropped,
        "dropped_reasons": {"missing_product": dropped},
        "unquantified_rows": unquantified,
        "columns_detected": dict(ingested.mapping),
        "unmapped_columns": list(ingested.unmapped_columns),
        "has_period": has_period,
        "unknown_units": unknown_units,
        "warnings": warnings,
    }
    return CleanResult(df=df, quality=quality)

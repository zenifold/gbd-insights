"""
Step 4 — Emissions.

Compute kg CO2e per line item. Preferred method is mass-based
(mass_kg x co2e_per_kg); when mass can't be derived, fall back to spend-based
(spend x co2e_per_usd). The method used is recorded per row for transparency.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import factors as load_factors


def apply_emissions(df: pd.DataFrame) -> pd.DataFrame:
    factors = load_factors()
    cat_factors = factors["categories"]
    default_per_usd = factors.get("default_co2e_per_usd", 0.5)

    def _row(row):
        cat = row["category"]
        f = cat_factors.get(cat, {})
        per_kg = f.get("co2e_per_kg")
        per_usd = f.get("co2e_per_usd", default_per_usd)
        mass, spend = row["mass_kg"], row["spend"]

        if pd.notna(mass) and per_kg is not None:
            return pd.Series([mass * per_kg, "mass"])
        if pd.notna(spend) and per_usd is not None:
            return pd.Series([spend * per_usd, "spend"])
        return pd.Series([np.nan, "none"])

    out = df.copy()
    out[["emissions_kgco2e", "emissions_method"]] = out.apply(_row, axis=1)
    return out

"""
Step 4 — Emissions.

Compute kg CO2e per line item. Method preference, most to least reliable:
  1. mass-based   (mass_kg x co2e_per_kg)              -> confidence "high"
  2. volume-based (volume_l x density x co2e_per_kg)   -> confidence "medium"
  3. spend-based  (spend x co2e_per_usd)               -> confidence "low"
The method + confidence used is recorded per row for transparency, and a
volume-derived mass is written back into mass_kg so totals stay consistent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import densities as load_densities
from .config import factors as load_factors

_CONFIDENCE = {"mass": "high", "volume": "medium", "spend": "low", "none": "none"}


def apply_emissions(df: pd.DataFrame) -> pd.DataFrame:
    factors = load_factors()
    cat_factors = factors["categories"]
    default_per_usd = factors.get("default_co2e_per_usd", 0.5)
    densities = load_densities()
    default_density = densities.get("_default", 1.0)

    def _row(row):
        cat = row["category"]
        f = cat_factors.get(cat, {})
        per_kg = f.get("co2e_per_kg")
        per_usd = f.get("co2e_per_usd", default_per_usd)
        mass = row.get("mass_kg")
        volume = row.get("volume_l")
        spend = row.get("spend")

        if pd.notna(mass) and per_kg is not None:
            return pd.Series([mass * per_kg, "mass", mass])
        if pd.notna(volume) and per_kg is not None:
            mass_est = volume * densities.get(cat, default_density)
            return pd.Series([mass_est * per_kg, "volume", mass_est])
        if pd.notna(spend) and per_usd is not None:
            return pd.Series([spend * per_usd, "spend", mass])
        return pd.Series([np.nan, "none", mass])

    out = df.copy()
    out[["emissions_kgco2e", "emissions_method", "mass_kg"]] = out.apply(_row, axis=1)
    out["emissions_kgco2e"] = pd.to_numeric(out["emissions_kgco2e"], errors="coerce")
    out["mass_kg"] = pd.to_numeric(out["mass_kg"], errors="coerce")
    out["confidence"] = out["emissions_method"].map(_CONFIDENCE)
    return out

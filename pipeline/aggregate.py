"""
Step 5 — Aggregate.

Roll the per-line-item emissions up by category and by time period, find the top
contributing products, and compute headline totals. All ordering is
deterministic (emissions desc, then name asc) for reproducible output.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Aggregates:
    by_category: pd.DataFrame
    by_period: pd.DataFrame
    top_products: pd.DataFrame
    totals: dict


def _round(x, n=2):
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return 0.0


def aggregate(df: pd.DataFrame, top_n: int = 10) -> Aggregates:
    by_category = (
        df.groupby(["category", "category_label"], dropna=False)
        .agg(
            line_items=("product", "size"),
            spend=("spend", "sum"),
            mass_kg=("mass_kg", "sum"),
            emissions_kgco2e=("emissions_kgco2e", "sum"),
        )
        .reset_index()
        .sort_values(["emissions_kgco2e", "category"], ascending=[False, True])
        .reset_index(drop=True)
    )

    if bool(df["period"].notna().any()):
        by_period = (
            df.dropna(subset=["period"])
            .groupby("period")
            .agg(
                line_items=("product", "size"),
                spend=("spend", "sum"),
                emissions_kgco2e=("emissions_kgco2e", "sum"),
            )
            .reset_index()
            .sort_values("period")
            .reset_index(drop=True)
        )
    else:
        by_period = pd.DataFrame(columns=["period", "line_items", "spend", "emissions_kgco2e"])

    top_products = (
        df.groupby(["product", "category_label"], dropna=False)
        .agg(
            spend=("spend", "sum"),
            emissions_kgco2e=("emissions_kgco2e", "sum"),
        )
        .reset_index()
        .sort_values(["emissions_kgco2e", "product"], ascending=[False, True])
        .head(top_n)
        .reset_index(drop=True)
    )

    total_emissions = float(df["emissions_kgco2e"].sum())
    total_spend = float(df["spend"].sum())
    total_mass = float(df["mass_kg"].sum())
    n_items = int(len(df))
    n_uncat = int((df["category"] == "uncategorized").sum())

    top_cat_name, top_cat_share = "", 0.0
    if not by_category.empty and total_emissions > 0:
        top_cat_name = by_category.iloc[0]["category_label"]
        top_cat_share = by_category.iloc[0]["emissions_kgco2e"] / total_emissions * 100

    totals = {
        "total_emissions_kgco2e": _round(total_emissions),
        "total_emissions_tonnes": _round(total_emissions / 1000, 3),
        "total_spend_usd": _round(total_spend),
        "total_mass_kg": _round(total_mass),
        "line_items": n_items,
        "uncategorized_items": n_uncat,
        "emissions_intensity_kgco2e_per_usd": _round(total_emissions / total_spend, 4)
        if total_spend > 0
        else 0.0,
        "top_category": top_cat_name,
        "top_category_share_pct": _round(top_cat_share, 1),
        "method_breakdown": {
            k: int(v) for k, v in df["emissions_method"].value_counts().sort_index().items()
        },
    }
    return Aggregates(by_category, by_period, top_products, totals)

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


# Real-world equivalency factors (US EPA Greenhouse Gas Equivalencies, 2023):
#   per passenger vehicle / year      4.60 t CO2e
#   per gallon of gasoline burned     0.008887 t CO2e
#   per tree seedling grown 10 years  0.060 t CO2e (sequestration)
#   per home's electricity / year     5.505 t CO2e
_EQ_CAR_YEAR_T = 4.60
_EQ_GASOLINE_GAL_T = 0.008887
_EQ_TREE_10YR_T = 0.060
_EQ_HOME_ELEC_YEAR_T = 5.505


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

    # --- Data quality: how much of the footprint rests on measured weight vs. a
    # rougher spend-based estimate, and how much of the catalog was categorized.
    method = df.get("emissions_method")
    if method is not None:
        em = df["emissions_kgco2e"].fillna(0.0)
        weight_em = float(em[method.isin(["mass", "volume"])].sum())
        spend_em = float(em[method == "spend"].sum())
    else:
        weight_em = spend_em = 0.0
    weight_frac = weight_em / total_emissions if total_emissions > 0 else 0.0
    cat_frac = (n_items - n_uncat) / n_items if n_items else 0.0
    conf_col = df.get("confidence")
    by_confidence = (
        {k: int(v) for k, v in conf_col.value_counts().sort_index().items()}
        if conf_col is not None
        else {}
    )
    data_quality = {
        "score": int(round((0.7 * weight_frac + 0.3 * cat_frac) * 100)),
        "weight_based_pct": _round(weight_frac * 100, 1),
        "spend_based_pct": _round(spend_em / total_emissions * 100, 1) if total_emissions > 0 else 0.0,
        "categorized_pct": _round(cat_frac * 100, 1),
        "by_confidence": by_confidence,
    }

    # --- Relatable equivalencies for the headline footprint.
    t = total_emissions / 1000.0
    equivalencies = {
        "cars_off_road_year": _round(t / _EQ_CAR_YEAR_T, 1),
        "gasoline_gallons": int(round(t / _EQ_GASOLINE_GAL_T)),
        "tree_seedlings_10yr": int(round(t / _EQ_TREE_10YR_T)),
        "homes_electricity_year": _round(t / _EQ_HOME_ELEC_YEAR_T, 1),
    }

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
        "emissions_intensity_kgco2e_per_kg_food": _round(total_emissions / total_mass, 2)
        if total_mass > 0
        else 0.0,
        "top_category": top_cat_name,
        "top_category_share_pct": _round(top_cat_share, 1),
        "method_breakdown": {
            k: int(v) for k, v in df["emissions_method"].value_counts().sort_index().items()
        },
        "data_quality": data_quality,
        "equivalencies": equivalencies,
    }
    return Aggregates(by_category, by_period, top_products, totals)

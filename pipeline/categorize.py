"""
Step 3 — Categorize.

Deterministic, rule-based mapping of each line item to exactly one GBD category
(first matching keyword wins, in the configured order). Reproducible by design —
no LLM call in this layer. An explicit, valid ``category`` column in the source
file overrides the inference.
"""
from __future__ import annotations

import pandas as pd

from .config import categories as load_categories


def categorize_product(product: str, taxonomy: dict | None = None) -> str:
    taxonomy = taxonomy or load_categories()
    text = (product or "").lower()
    for category in taxonomy["order"]:
        for keyword in taxonomy["categories"][category]["keywords"]:
            if keyword in text:
                return category
    return "uncategorized"


def categorize(df: pd.DataFrame) -> pd.DataFrame:
    taxonomy = load_categories()
    valid = set(taxonomy["categories"].keys())

    def _assign(row):
        override = row.get("category")
        if isinstance(override, str) and override.strip().lower() in valid:
            return override.strip().lower()
        return categorize_product(row["product"], taxonomy)

    out = df.copy()
    out["category"] = out.apply(_assign, axis=1)
    out["category_label"] = out["category"].map(
        lambda c: taxonomy["categories"][c]["label"]
    )
    return out

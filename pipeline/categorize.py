"""
Step 3 — Categorize.

Deterministic, rule-based mapping of each line item to exactly one GBD category
(first matching keyword wins, in the configured order). Reproducible by design —
no LLM call in this layer. An explicit, valid ``category`` column in the source
file overrides the inference.

Matching is *token-aware*, not raw substring, to avoid classic false positives
("graham" → ham/pork, "eggplant" → egg, "coconut" → nut). A single-word keyword
matches a word that equals it, its simple plural, or (for keywords ≥5 chars) a
word that starts with it ("tomato" → "tomatoes"). Multi-word keywords match as a
whole phrase ("almond milk" → plant-based, not dairy).
"""
from __future__ import annotations

import re

import pandas as pd

from .config import categories as load_categories

_NON_WORD = re.compile(r"[^a-z0-9]+")
_PREFIX_MIN = 5  # only keywords this long match by prefix (so "bean"→"beans" but not "seedless")


def _normalize(product: str) -> str:
    return _NON_WORD.sub(" ", (product or "").lower()).strip()


def _keyword_matches(keyword: str, norm: str, tokens: list[str]) -> bool:
    if " " in keyword:  # phrase: match with surrounding word boundaries
        return f" {keyword} " in f" {norm} "
    for t in tokens:
        if t == keyword or t == keyword + "s":
            return True
        if len(keyword) >= _PREFIX_MIN and t.startswith(keyword):
            return True
    return False


def categorize_product(product: str, taxonomy: dict | None = None) -> str:
    taxonomy = taxonomy or load_categories()
    norm = _normalize(product)
    if not norm:
        return "uncategorized"
    tokens = norm.split()
    for category in taxonomy["order"]:
        for keyword in taxonomy["categories"][category]["keywords"]:
            if _keyword_matches(keyword.lower(), norm, tokens):
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

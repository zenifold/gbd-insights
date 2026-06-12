import math

import pandas as pd
import pytest

from pipeline.emissions import apply_emissions


def test_mass_preferred_spend_fallback_and_none():
    df = pd.DataFrame(
        [
            {"category": "beef", "mass_kg": 10.0, "spend": 100.0},       # mass-based
            {"category": "legumes", "mass_kg": math.nan, "spend": 50.0},  # spend fallback
            {"category": "uncategorized", "mass_kg": math.nan, "spend": math.nan},  # none
        ]
    )
    out = apply_emissions(df)

    assert out.loc[0, "emissions_method"] == "mass"
    assert out.loc[0, "emissions_kgco2e"] == pytest.approx(600.0)  # 10 kg * 60

    assert out.loc[1, "emissions_method"] == "spend"
    assert out.loc[1, "emissions_kgco2e"] == pytest.approx(15.0)  # $50 * 0.3

    assert out.loc[2, "emissions_method"] == "none"
    assert math.isnan(out.loc[2, "emissions_kgco2e"])

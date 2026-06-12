import pytest

from pipeline.categorize import categorize_product


@pytest.mark.parametrize(
    "product,expected",
    [
        ("Ground Beef 80/20", "beef"),
        ("Chicken Breast Boneless", "poultry"),
        ("Black Beans Canned", "legumes"),
        ("Tofu Firm", "tofu_soy"),
        ("Cheddar Cheese Block", "cheese"),
        ("Brown Rice 25lb", "grains"),
        ("Mixed Greens", "vegetables"),
        ("Whole Milk", "dairy"),
        ("Atlantic Salmon Fillet", "seafood"),
        ("Mystery Widget", "uncategorized"),
        ("", "uncategorized"),
    ],
)
def test_categorize_product(product, expected):
    assert categorize_product(product) == expected

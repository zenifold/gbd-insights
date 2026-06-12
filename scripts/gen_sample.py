import csv, random, os
from datetime import date, timedelta

random.seed(42)

# (product, category-ish, unit, low_price_per_unit, high_price_per_unit, qty_low, qty_high)
# units: lb/oz/kg -> weight-based; case/each/gal/dozen/can/block -> spend-based fallback
CATALOG = [
    # Beef
    ("Ground Beef 80/20", "lb", 3.8, 5.2, 80, 400),
    ("Beef Brisket", "lb", 4.5, 7.0, 40, 180),
    ("Beef Steak Strips", "lb", 6.0, 9.5, 30, 120),
    ("Hamburger Patties 4oz", "case", 38, 62, 4, 30),
    # Pork
    ("Pork Loin Boneless", "lb", 2.8, 4.2, 60, 220),
    ("Bacon Sliced", "lb", 4.0, 6.5, 30, 140),
    ("Breakfast Sausage Links", "case", 28, 44, 5, 28),
    ("Sliced Ham Deli", "lb", 3.2, 5.0, 40, 150),
    # Poultry
    ("Chicken Breast Boneless", "lb", 2.4, 3.8, 100, 450),
    ("Chicken Thighs", "lb", 1.8, 2.9, 60, 260),
    ("Whole Turkey Frozen", "lb", 1.6, 2.6, 80, 300),
    ("Chicken Tenders Breaded", "case", 34, 56, 4, 26),
    # Seafood
    ("Atlantic Salmon Fillet", "lb", 7.5, 12.0, 25, 110),
    ("Tilapia Fillet Frozen", "lb", 3.5, 5.5, 30, 130),
    ("Canned Tuna Chunk", "case", 26, 40, 3, 22),
    ("Cod Fillet", "lb", 6.0, 9.0, 20, 90),
    # Eggs
    ("Large Eggs Grade A", "dozen", 2.2, 3.6, 30, 200),
    ("Liquid Egg Whites", "case", 30, 48, 2, 16),
    # Cheese
    ("Cheddar Cheese Block", "lb", 3.0, 4.8, 50, 220),
    ("Mozzarella Shredded", "lb", 2.8, 4.2, 60, 260),
    ("Parmesan Grated", "lb", 5.5, 8.5, 15, 70),
    # Dairy
    ("Whole Milk", "gal", 3.0, 4.5, 40, 240),
    ("Greek Yogurt Plain", "case", 22, 36, 4, 28),
    ("Butter Unsalted", "lb", 3.4, 5.2, 25, 120),
    ("Heavy Cream", "gal", 6.0, 9.0, 8, 40),
    # Tofu & soy
    ("Tofu Firm", "block", 1.4, 2.4, 60, 300),
    ("Tempeh", "case", 24, 38, 2, 14),
    ("Edamame Frozen", "lb", 2.0, 3.4, 30, 140),
    # Legumes
    ("Black Beans Canned", "case", 16, 26, 5, 34),
    ("Chickpeas Dried", "lb", 1.0, 1.8, 40, 200),
    ("Red Lentils", "lb", 1.2, 2.2, 30, 160),
    ("Hummus Tubs", "case", 28, 42, 2, 16),
    # Nuts & seeds
    ("Almonds Sliced", "lb", 6.0, 9.5, 10, 60),
    ("Peanut Butter", "case", 30, 46, 2, 14),
    ("Sunflower Seeds", "lb", 2.5, 4.0, 15, 70),
    # Grains
    ("Long Grain White Rice", "lb", 0.7, 1.3, 100, 500),
    ("Whole Wheat Bread Loaves", "case", 20, 32, 6, 40),
    ("Penne Pasta", "lb", 1.0, 1.8, 60, 280),
    ("Flour Tortillas", "case", 18, 30, 5, 34),
    ("Rolled Oats", "lb", 0.9, 1.6, 40, 180),
    ("Quinoa", "lb", 2.8, 4.5, 15, 80),
    # Vegetables
    ("Mixed Salad Greens", "lb", 2.0, 3.6, 50, 260),
    ("Roma Tomatoes", "lb", 1.2, 2.4, 60, 280),
    ("Russet Potatoes", "lb", 0.5, 1.1, 120, 600),
    ("Yellow Onions", "lb", 0.6, 1.3, 80, 360),
    ("Broccoli Florets", "lb", 1.6, 2.8, 40, 200),
    ("Baby Carrots", "case", 18, 28, 4, 26),
    ("Bell Peppers", "lb", 1.8, 3.2, 30, 160),
    ("Baby Spinach", "lb", 2.4, 4.0, 25, 130),
    # Fruits
    ("Bananas", "lb", 0.5, 0.9, 100, 500),
    ("Gala Apples", "lb", 1.0, 1.8, 80, 360),
    ("Orange Juice Concentrate", "case", 24, 38, 3, 22),
    ("Mixed Berries Frozen", "lb", 3.0, 5.0, 20, 110),
    ("Cantaloupe Melon", "each", 1.5, 3.0, 30, 160),
    # Oils
    ("Canola Oil", "case", 30, 48, 2, 16),
    ("Olive Oil Extra Virgin", "case", 55, 85, 1, 10),
    # Beverages
    ("Apple Juice Boxes", "case", 20, 32, 5, 36),
    ("Brewed Coffee Grounds", "lb", 5.0, 8.0, 10, 60),
    ("Bottled Water", "case", 8, 16, 10, 60),
    # Prepared
    ("Marinara Sauce", "case", 22, 36, 3, 22),
    ("Vegetable Soup Base", "case", 26, 40, 2, 16),
    ("Cheese Pizza Frozen", "case", 40, 64, 2, 18),
    # A few that won't categorize cleanly
    ("Assorted Condiment Packets", "case", 14, 24, 3, 20),
    ("Paper Food Trays", "case", 26, 40, 2, 14),
]

VENDORS = ["US Foods", "Sysco", "Gordon Food Service", "Performance Foodservice",
           "Local Harvest Co-op", "Baldor Specialty Foods", "Restaurant Depot"]

START = date(2026, 1, 1)
DAYS = 180  # Jan–Jun 2026

rows = []
for _ in range(300):
    name, unit, plo, phi, qlo, qhi = random.choice(CATALOG)
    qty = random.randint(qlo, qhi)
    unit_price = round(random.uniform(plo, phi), 2)
    spend = round(qty * unit_price, 2)
    d = START + timedelta(days=random.randint(0, DAYS - 1))
    rows.append({
        "product": name,
        "vendor": random.choice(VENDORS),
        "spend": f"{spend:.2f}",
        "quantity": qty,
        "unit": unit,
        "date": d.isoformat(),
    })

rows.sort(key=lambda r: r["date"])

out = os.path.join(os.path.expanduser("~"), "Downloads", "riverside_usd_procurement_2026.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["product", "vendor", "spend", "quantity", "unit", "date"])
    w.writeheader()
    w.writerows(rows)

print("Wrote", len(rows), "rows ->", out)

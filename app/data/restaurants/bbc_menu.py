"""Borivali Biryani Centre's menu, copied from the printed menu photos (the black menu's prices), and the pairing
rules that say what goes with what. `python -m app.data.restaurants.bbc_menu` writes the skeleton the dish stories are
added to (borivali-biryani-centre.json is the finished file the seed script reads).

A dish is (name, price or {size: price}, veg). Dishes the printed menu sells in "Veg / Egg / Chicken / Prawns" columns
are separate dishes here, so every dish has one honest veg flag.
"""
import json
import sys
from pathlib import Path

V, N = True, False  # vegetarian, non-vegetarian

BIRYANI_SIZES = ("Small", "Big", "Large")


def sizes(small=None, big=None, large=None) -> dict:
    return {k: p for k, p in zip(BIRYANI_SIZES, (small, big, large)) if p}


def columns(base: str, veg=None, egg=None, chicken=None, prawns=None) -> list:
    """One dish per price column of the printed Rice & Noodles and Soups tables."""
    out = []
    for label, price, is_veg in (("Veg", veg, V), ("Egg", egg, N), ("Chicken", chicken, N), ("Prawns", prawns, N)):
        if price:
            out.append((f"{label} {base}", price, is_veg))
    return out


CATEGORIES = [
    "Aromatic Veg Biryani", "Signature Non Veg Biryani", "Snacks", "Soups", "Naan / Roti", "Sides",
    "Tandoor Veg Starters", "Tandoor Non Veg Starters", "Chinese Veg Starters", "Chinese Non Veg Starters",
    "Koliwada", "Veg Mughlai Handi / Tawa", "Non Veg Mughlai Handi / Tawa", "Oriental Gravies", "Rice & Noodles",
    "Dessert & Cooler",
]

MENU: dict[str, list] = {
    "Aromatic Veg Biryani": [
        ("Veg Dum Biryani", sizes(245, 345, 1155), V),
        ("Paneer Tikka Biryani", sizes(None, 400, 1385), V),
        ("Paneer Kalimirch Biryani", 400, V),
        ("Paneer Biryani", 400, V),
        ("Chote Aloo Mushroom Biryani", 400, V),
        ("Soya Chaap Tikka Biryani", 380, V),
        ("Veg Cheese Tawa Rice", 410, V),
        ("Dal Khichdi", 270, V),
        ("Dal Khichdi Tadka", 290, V),
        ("Palak Khichdi", 290, V),
        ("Steam Rice", 165, V),
        ("Jeera Rice", 185, V),
        ("Biryani Rice", 165, V),
        ("Veg Pulav", 275, V),
        ("Paneer Mutter Pulav", 295, V),
    ],
    "Signature Non Veg Biryani": [
        ("Chicken Dum Biryani", sizes(275, 365, 1240), N),
        ("Chicken Tikka Biryani", sizes(315, 410, 1460), N),
        ("Afghani Leg Biryani", 410, N),
        ("Chicken Tawa Rice", 420, N),
        ("Chicken Seekh Kebab Biryani", 420, N),
        ("Mutton Dum Biryani", sizes(350, 430, 1575), N),
        ("Mutton Tawa Rice", 440, N),
        ("Mutton Seekh Kebab Biryani", 440, N),
        ("Kheema Aloo Biryani", 420, N),
        ("Prawns Kalimirch Biryani", 410, N),
        ("Prawns Biryani", 410, N),
        ("Rawas Biryani", 400, N),
        ("Prawns Tawa Rice", 410, N),
        ("Anda Biryani", 360, N),
        ("Anda Tawa Rice", 360, N),
        ("Kepsa Rice", 1575, N),
    ],
    "Snacks": [
        ("Chicken Cutlet", 90, N),
        ("Kheema Pav", 340, N),
        ("Omlette Pav", 215, N),
        ("Burjee Pav", 225, N),
        ("Brain Burjee Pav", 340, N),
        ("Add Cheese", 70, V),
        ("Extra Butter Pav", 30, V),
    ],
    "Soups": [
        ("Tulsi Tomato Soup", 225, V),
        ("Paya Soup", 255, N),
        ("Plain Paya Soup", 235, N),
        *columns("Pepper Spinach Soup", 225, None, 265, 290),
        *columns("Manchow Soup", 225, None, 270, 270),
        *columns("Hot N Sour Soup", 225, None, 270, 270),
        *columns("Sweetcorn Soup", 225, None, 270, 270),
        *columns("Clear Noodle Soup", 225, None, 270, 270),
    ],
    "Naan / Roti": [
        ("Roti", {"Plain": 53, "Butter": 64}, V),
        ("Naan", {"Plain": 70, "Butter": 85}, V),
        ("Lacha Paratha", {"Plain": 75, "Butter": 85}, V),
        ("Garlic Naan", {"Plain": 95, "Butter": 115}, V),
        ("Kulcha", {"Plain": 60, "Butter": 70}, V),
        ("Cheese Naan", {"Plain": 160, "Butter": 170}, V),
        ("Cheese Garlic Naan", {"Plain": 180, "Butter": 190}, V),
        ("Stuffed Cheese Garlic Naan", {"Plain": 195, "Butter": 235}, V),
    ],
    "Sides": [
        ("Veg Raita", 110, V),
        ("Pineapple Raita", 140, V),
        ("Boondi Raita", 140, V),
        ("Masala Papad", 60, V),
        ("Papad Churi", 160, V),
        ("Papad", {"Roasted": 40, "Fry": 40}, V),
        ("Green Salad", 140, V),
    ],
    "Tandoor Veg Starters": [
        ("Paneer Tikka Dry", 375, V),
        ("Paneer Tulsi Tikka", 395, V),
        ("Paneer Zafrani Tikka", 430, V),
        ("Paneer Nizami Tikka", 430, V),
        ("Paneer Kathi Roll", 480, V),
        ("Mushroom Nizami Tikka", 405, V),
        ("Aloo Nizami Tikka", 365, V),
        ("Tandoori Aloo", 300, V),
        ("Mushroom Tikka", 405, V),
        ("Soya Chaap Tikka", 375, V),
        ("Soya Chaap Afghani Malai Tikka", 375, V),
    ],
    "Tandoor Non Veg Starters": [
        ("Tandoori Lollypop", 340, N),
        ("Tandoori Chicken", {"Half": 340, "Full": 680}, N),
        ("Chicken Tikka Dry", 430, N),
        ("Chicken Seekh Kebab", 405, N),
        ("Chicken Kathi Roll", 480, N),
        ("Jehangir Kebab", 415, N),
        ("Murgh Nizami Tikka", 430, N),
        ("Chicken Cheese Banjara Kebab", 500, N),
        ("Tangri Kebab", 415, N),
        ("Noorani Kebab", 490, N),
        ("Reshmi Kebab", 435, N),
        ("Mutton Seekh Kebab", 480, N),
        ("Prawns Kalimirch Tikka", 435, N),
        ("Ravas Tulsi Tikka", 460, N),
        ("Ravas Tikka", 440, N),
        ("Chicken Malai Kalimirch Tikka", 430, N),
    ],
    "Chinese Veg Starters": [
        ("Paneer Butter Pepper Garlic", 365, V),
        ("Paneer Chilli Dry", 365, V),
        ("Kung Pao Paneer", 365, V),
        ("Paneer Plum Chilli", 365, V),
        ("Paneer Dragon Chilli", 365, V),
        ("Pepper Paneer", 365, V),
        ("Black Bean Paneer", 365, V),
        ("Paneer Soya Basil", 365, V),
        ("Sichuan Paneer", 365, V),
        ("Veg Manchurian Dry", 290, V),
        ("Veg Crispy", 375, V),
        ("Mushroom Chilli", 340, V),
        ("Stir Fried Exotic Veggies", 340, V),
        ("Honey Chilli Potato", 350, V),
        ("Cigar Rolls", 310, V),
        ("Potato Veggies", 270, V),
        ("Water Chestnut Corn Paneer in Sauce", 430, V),
        ("Broccoli Babycorn Paneer in Sauce", 430, V),
        ("Java Lotus Stem Corn and Paneer in Sauce", 430, V),
        ("Pepper Babycorn Mushroom", 430, V),
    ],
    "Chinese Non Veg Starters": [
        ("Chicken Lollipop Oil Fried", 345, N),
        ("Chicken Lollipop Sichuan Dry", 430, N),
        ("Chicken Dragon Chilli", 420, N),
        ("Lollipop Plum Chilli", 430, N),
        ("Apple Chicken", 430, N),
        ("Drums of Heaven", 430, N),
        ("Chicken Chilli", 415, N),
        ("Kung Pao Chicken", 415, N),
        ("Chicken Manchurian Dry", 400, N),
        ("Pepper Chicken", 400, N),
        ("Black Bean Chicken", 400, N),
        ("Chicken Plum Chilli", 400, N),
        ("Chicken Soy Basil", 400, N),
        ("BBQ Wings", 400, N),
        ("Chicken Crispy", 430, N),
        ("Sichuan Chicken", 400, N),
        ("Fish Chilli", 430, N),
        ("Prawns Chilli", 430, N),
        ("Kung Pao Fish", 420, N),
        ("Kung Pao Prawns", 430, N),
        ("Fish Plum Chilli", 430, N),
        ("Prawns Plum Chilli", 430, N),
        ("Sichuan Fish", 430, N),
        ("Sichuan Prawns", 430, N),
        ("Prawns Dragon Chilli", 430, N),
        ("Prawns Soy Basil", 430, N),
        ("Fish Soy Basil", 430, N),
        ("Black Bean Fish", 430, N),
        ("Pataya Fish", 430, N),
        ("Prawns Butter Pepper Garlic", 430, N),
        ("Brain Butter Pepper Garlic", 600, N),
        ("Egg Chilli", 360, N),
    ],
    "Koliwada": [
        ("Prawns Koliwada", 480, N),
        ("Chicken Koliwada", 405, N),
        ("Rawas Koliwada", 480, N),
        ("Paneer Koliwada", 320, V),
    ],
    "Veg Mughlai Handi / Tawa": [
        ("Paneer Angara", 405, V),
        ("Paneer Do Pyaza", 405, V),
        ("Paneer Kolhapuri", 405, V),
        ("Butter Paneer", 405, V),
        ("Paneer Tikka Masala", 405, V),
        ("Palak Paneer", 405, V),
        ("Paneer Karhai", 405, V),
        ("Paneer Makhani", 405, V),
        ("Paneer Tawa Khurchan", 415, V),
        ("Paneer Motiwala", 405, V),
        ("Paneer Pasanda", 415, V),
        ("Paneer Mutter", 405, V),
        ("Aloo Mutter", 365, V),
        ("Aloo Gobi", 365, V),
        ("Aloo Methi", 365, V),
        ("Veg Karhai", 385, V),
        ("Veg Makhani", 385, V),
        ("Veg Tawa Masala", 385, V),
        ("Veg Kolhapuri", 385, V),
        ("Veg Lahori", 385, V),
        ("Sabji Kheema Masala", 385, V),
        ("Diwani Handi", 385, V),
        ("Malai Kofta", 405, V),
        ("Methi Mutter Malai", 405, V),
        ("Paneer Bhurjee", 420, V),
        ("Spicy Malai Kofta", 415, V),
        ("Babycorn Mushroom Tawa Masala", 385, V),
        ("Dal Fry", 265, V),
        ("Dal Tadka", 300, V),
        ("Dal Makhni", 300, V),
        ("Chole Masala", 340, V),
        ("Chole Karhai", 340, V),
        ("Babycorn Mushroom Shabnam Masala", 395, V),
    ],
    "Non Veg Mughlai Handi / Tawa": [
        ("White Butter Chicken", 440, N),
        ("Chicken Kheema Masala", 420, N),
        ("Butter Chicken", 440, N),
        ("Spicy Butter Chicken", 440, N),
        ("Chicken Tikka Masala", 440, N),
        ("Chicken Handi", {"Half": 665, "Full": 1330}, N),
        ("Chicken Mughlai Leg Curry", 440, N),
        ("Afghani Chicken", 440, N),
        ("Chicken Masala", 405, N),
        ("Chicken Kolhapuri", 405, N),
        ("Chicken Karhai", 405, N),
        ("Bhuna Chicken", 460, N),
        ("Methi Murgh Malai", 430, N),
        ("Palak Chicken", 430, N),
        ("Lahori Chicken", 430, N),
        ("Murgh Mussallam", {"Half": 725, "Full": 1450}, N),
        ("White Chicken", 420, N),
        ("White Mutton", 490, N),
        ("Mutton Rogan Josh", 490, N),
        ("Karhai Mutton", 490, N),
        ("Mutton Handi", {"Half": 750, "Full": 1500}, N),
        ("Bhuna Mutton", 565, N),
        ("Chicken Angara", 460, N),
        ("Methi Chicken", 405, N),
        ("Dal Gosht", 480, N),
        ("Mutton Masala", 490, N),
        ("Methi Mutton Malai", 500, N),
        ("Lahori Mutton", 500, N),
        ("Mutton Kheema Gotala", 500, N),
        ("Mutton Kheema Masala", 500, N),
        ("Methi Mutton", 500, N),
        ("Mutton Kolhapuri", 490, N),
        ("Prawns Masala", 440, N),
        ("Prawns Tawa Masala", 440, N),
        ("Prawns Karhai", 440, N),
        ("Brain Masala", 600, N),
        ("Ravas Masala", 470, N),
        ("Paya Masala", 450, N),
        ("Anda Masala", 365, N),
        ("Half Fry Anda Masala", 365, N),
        ("Anda Curry", 355, N),
    ],
    "Oriental Gravies": [
        ("Exotic Veg in Sauce", 370, V),
        ("Paneer in Sauce", 395, V),
        ("Mushroom and Bamboo Shoot in Sauce", 375, V),
        ("Veg Manchurian Gravy", 320, V),
        ("American Chopsuey Veg", 340, V),
        ("Exotic Thai Curry Veg", 380, V),
        ("Chicken in Sauce", 395, N),
        ("Prawns in Sauce", 395, N),
        ("Fish in Sauce", 395, N),
        ("Lamb in Sauce", 480, N),
        ("Lollipop in Sauce", 495, N),
        ("American Chopsuey Chicken", 420, N),
        ("Thai Curry Chicken", 410, N),
        ("Thai Curry Prawns", 410, N),
        ("Thai Curry Fish", 410, N),
    ],
    "Rice & Noodles": [
        *columns("Fried Rice", 300, 310, 330, 345),
        *columns("Sichuan Rice", 310, 330, 345, 355),
        *columns("Burnt Chilli Garlic Rice", 310, 330, 345, 355),
        *columns("Mushroom Fried Rice", 310, 330, 345, 355),
        *columns("Exotic Pot Rice", 430, 440, 450, 460),
        *columns("Chopper Rice", 500, None, 515, 525),
        *columns("Hakka Noodles", 300, 310, 330, 345),
        *columns("Sichuan Noodles", 310, 330, 345, 355),
        *columns("Spicy Basil Noodles", 310, 330, 345, 355),
        *columns("Burnt Chilli Garlic Noodles", 310, 330, 345, 355),
        *columns("Mushroom Noodles", 310, 330, 345, 355),
        *columns("Malaysian Noodles", 320, 340, 365, 380),
        *columns("Triple Rice", 420, 440, 460, 480),
        *columns("Thai Fried Rice", 320, 330, 350, 360),
        ("Lamb Pot Rice", 470, N),
        ("Fish Pot Rice", 440, N),
    ],
    "Dessert & Cooler": [
        ("Caramel Pudding", 105, V),
        ("Gulab Jamun", 130, V),
        ("Bottled Water", 30, V),
        ("Cold Drinks", 60, V),
        ("Chaas", 100, V),
        ("Lassi", 120, V),
        ("Fresh Lime Water", 80, V),
        ("Fresh Lime Soda", 110, V),
        ("Chatpata Lime Water", 90, V),
        ("Chatpata Lime Soda", 120, V),
        ("Mojito", {"Mint": 150, "Pineapple": 150, "Kalakhatta": 150, "Strawberry": 150}, V),
        ("Ice Tea", {"Lemon": 140, "Peach": 140}, V),
        ("Watermelon Juice", 140, V),
        ("Blue Mist", 140, V),
    ],
}

# ------------------------------------------------------------------------------------------------- roles & pairings

SIDE_CATEGORIES = {"Naan / Roti", "Sides", "Rice & Noodles"}
SIDE_NAMES = {"Steam Rice", "Jeera Rice", "Biryani Rice", "Add Cheese", "Extra Butter Pav"}
DRINK_DESSERT = {"Caramel Pudding": "dessert", "Gulab Jamun": "dessert"}


def order_role(category: str, name: str) -> str:
    if category == "Dessert & Cooler":
        return DRINK_DESSERT.get(name, "drink")
    if category in SIDE_CATEGORIES or name in SIDE_NAMES:
        return "side"
    return "food"


COOL = ["Chaas", "Lassi"]
FIZZ = ["Fresh Lime Soda", "Cold Drinks"]
RAITAS = ["Boondi Raita", "Veg Raita", "Pineapple Raita"]


def pairs_for(category: str, name: str) -> list[str]:
    """What the waiter suggests alongside a dish, best first. Breads and raitas are `side`s, so they come before
    the drinks; names must be dishes on this menu (checked by `check`)."""
    n = name.lower()
    if category in ("Dessert & Cooler", "Sides", "Naan / Roti"):
        return []
    if name in ("Steam Rice", "Jeera Rice", "Biryani Rice", "Add Cheese", "Extra Butter Pav"):
        return []
    if category == "Aromatic Veg Biryani":
        if "khichdi" in n:
            return ["Papad", "Veg Raita", "Chaas"]
        if "tawa rice" in n:
            return ["Veg Raita", "Green Salad", "Fresh Lime Soda"]
        if "pulav" in n:
            return ["Boondi Raita", "Veg Raita", "Masala Papad", *COOL]
        return [*RAITAS, "Masala Papad", *COOL]
    if category == "Signature Non Veg Biryani":
        if "tawa rice" in n or "kepsa" in n:
            return ["Veg Raita", "Green Salad", *FIZZ]
        return ["Veg Raita", "Pineapple Raita", "Boondi Raita", "Green Salad", *COOL]
    if category == "Snacks":
        if name == "Chicken Cutlet":
            return ["Green Salad", *FIZZ]
        return ["Extra Butter Pav", "Add Cheese", *FIZZ]
    if category == "Soups":
        pick = ["Veg Manchurian Dry", "Honey Chilli Potato"] if n.startswith(("veg", "tulsi")) else ["Chicken Manchurian Dry", "Chicken Chilli"]
        return pick
    if category in ("Tandoor Veg Starters", "Tandoor Non Veg Starters"):
        if "roll" in n:
            return ["Green Salad", *FIZZ]
        return ["Roti", "Naan", "Green Salad", *FIZZ]
    if category in ("Chinese Veg Starters", "Chinese Non Veg Starters"):
        veg = category == "Chinese Veg Starters"
        if veg or "egg" in n:
            return ["Veg Hakka Noodles", "Veg Fried Rice", *FIZZ]
        return ["Chicken Hakka Noodles", "Chicken Fried Rice", *FIZZ]
    if category == "Koliwada":
        return ["Green Salad", *FIZZ]
    if category == "Oriental Gravies":
        prefix = "Veg" if n.split()[0] in ("exotic", "paneer", "mushroom", "veg", "american") and "chicken" not in n else "Chicken"
        if "prawns" in n:
            prefix = "Prawns"
        return [f"{prefix} Fried Rice", f"{prefix} Hakka Noodles", *FIZZ]
    if category == "Veg Mughlai Handi / Tawa":
        if "dal" in n and "khichdi" not in n:
            return ["Jeera Rice", "Roti", "Naan", "Papad", *COOL]
        if "chole" in n:
            return ["Kulcha", "Roti", "Veg Raita", *COOL]
        if any(k in n for k in ("tawa", "khurchan", "bhurjee", "karhai", "kolhapuri", "do pyaza", "lahori", "angara", "aloo", "sabji", "methi")):
            return ["Roti", "Lacha Paratha", "Naan", "Veg Raita", *COOL]
        return ["Naan", "Roti", "Garlic Naan", "Jeera Rice", "Veg Raita", *COOL]
    if category == "Non Veg Mughlai Handi / Tawa":
        if "anda" in n:
            return ["Roti", "Naan", "Jeera Rice", *COOL]
        if "prawns" in n or "ravas" in n:
            return ["Jeera Rice", "Roti", "Naan", *COOL]
        if any(k in n for k in ("mutton", "gosht", "paya", "brain", "bhuna")):
            return ["Naan", "Roti", "Lacha Paratha", "Jeera Rice", *COOL]
        return ["Naan", "Garlic Naan", "Roti", "Jeera Rice", *COOL]
    if category == "Rice & Noodles":
        veg = n.startswith("veg")
        return ["Veg Manchurian Gravy" if veg else "Chicken in Sauce", "Paneer Chilli Dry" if veg else "Chicken Chilli", *FIZZ]
    return []


def flat() -> list[dict]:
    rows, order = [], 0
    for category in CATEGORIES:
        for name, price, veg in MENU[category]:
            order += 1
            row = {"category": category, "name": name, "is_veg": veg, "sort_order": order, "order_role": order_role(category, name)}
            if isinstance(price, dict):
                row["variants"] = [{"name": k, "price": v} for k, v in price.items()]
                row["price"] = min(price.values())
            else:
                row["price"] = price
            row["pairs_with"] = pairs_for(category, name)
            rows.append(row)
    return rows


def check(rows: list[dict]) -> list[str]:
    names = {r["name"] for r in rows}
    problems = []
    seen = set()
    for r in rows:
        if r["name"].lower() in seen:
            problems.append(f"duplicate dish {r['name']}")
        seen.add(r["name"].lower())
        for p in r["pairs_with"]:
            if p not in names:
                problems.append(f"{r['name']}: pairs with {p!r}, which is not on the menu")
            if p == r["name"]:
                problems.append(f"{r['name']}: pairs with itself")
    return problems


RESTAURANT = {
    "slug": "borivali-biryani-centre",
    "name": "Borivali Biryani Centre",
    "cuisine": "Biryani, Mughlai & Indo-Chinese",
    "tagline": "Dum biryani, tandoor, handi gravies and Indo-Chinese from Borivali West.",
    "agent_name": "Kabir",
    "accent_color": "#a16207",
}
STORY_FIELDS = ("short_description", "long_description", "ingredients", "allergens", "tags", "spice_level")


def build(stories_dir: Path) -> dict:
    """The skeleton plus the dish stories (stories_*.json, one object per group, keyed by dish name)."""
    stories: dict = {}
    for path in sorted(stories_dir.glob("stories_*.json")):
        stories.update(json.loads(path.read_text()))
    dishes = []
    for row in flat():
        story = stories.get(row["name"])
        if story is None:
            raise SystemExit(f"no story for {row['name']!r}")
        dish = {k: row[k] for k in ("category", "name", "price", "is_veg", "order_role", "pairs_with", "sort_order") if k in row}
        dish.update({k: story[k] for k in STORY_FIELDS})
        if row.get("variants"):
            dish["variants"] = row["variants"]
        dish["knowledge_status"] = "ai_draft"  # written from the dish name; the owner approves it in the dashboard
        dishes.append(dish)
    extra = set(stories) - {d["name"] for d in dishes}
    if extra:
        raise SystemExit(f"stories for dishes that are not on the menu: {sorted(extra)}")
    return {"restaurant": RESTAURANT, "categories": CATEGORIES, "dishes": dishes}


if __name__ == "__main__":
    here = Path(__file__).parent
    rows = flat()
    bad = check(rows)
    print(len(rows), "dishes,", len(bad), "problems")
    for b in bad:
        print(" ", b)
    if len(sys.argv) > 1:  # python -m app.data.restaurants.bbc_menu <folder with stories_*.json>
        spec = build(Path(sys.argv[1]))
        (here / "borivali-biryani-centre.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n")
        print("wrote borivali-biryani-centre.json with", len(spec["dishes"]), "dishes")
    else:
        (here / "borivali-biryani-centre.skeleton.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))

"""Dish names said in Hindi script find the English menu item (Samvaad's LLM often writes them that way)."""
from app.menu.snapshot import RestaurantMenu
from app.menu.translit import to_roman

NAMES = [
    "Paneer Tikka Pizza", "Paneer Tikka", "Margherita Pizza", "Garlic Breadsticks", "Penne Arrabbiata",
    "Miso Soup", "Butter Naan", "Kadai Paneer", "Shahi Paneer", "Dal Makhani", "Sweet Lassi",
    "Mysore Masala Dosa", "Set Dosa",
]


def menu() -> RestaurantMenu:
    dishes = [{"id": str(i), "name": n, "category": "Menu", "sort_order": i} for i, n in enumerate(NAMES)]
    return RestaurantMenu({"id": "r"}, [], dishes, 1)


def test_hindi_script_becomes_menu_spelling():
    assert to_roman("पनीर टिक्का पिज़्ज़ा") == "paneer tikka pizza"
    assert to_roman("दाल मखनी") == "dal makhanee"  # close enough: the match is fuzzy
    assert to_roman("Butter Naan") == "Butter Naan"  # Roman text is left alone


def test_dishes_said_in_hindi_script_are_found():
    m = menu()
    said = {
        "पनीर टिक्का पिज़्ज़ा": "Paneer Tikka Pizza",
        "पनीर टिक्का": "Paneer Tikka",
        "मार्गरीटा पिज़्ज़ा": "Margherita Pizza",
        "गार्लिक ब्रेडस्टिक्स": "Garlic Breadsticks",
        "पेने अराबियाटा": "Penne Arrabbiata",
        "मिसो सूप": "Miso Soup",
        "बटर नान": "Butter Naan",
        "कढ़ाई पनीर": "Kadai Paneer",
        "कड़ाही पनीर": "Kadai Paneer",
    }
    for hindi, dish in said.items():
        found = m.find_by_name(hindi)
        assert found and found["name"] == dish, hindi


def test_a_vague_or_unknown_hindi_name_is_not_guessed():
    m = menu()
    assert m.find_by_name("मैसूर डोसा") is None  # two dosas could be meant
    assert "Mysore Masala Dosa" in [d["name"] for d in m.candidates("मैसूर डोसा")]
    assert m.find_by_name("मैंगो लस्सी") is None  # not on this menu: never swapped for Sweet Lassi


def test_a_longer_dish_that_sounds_exactly_right_beats_a_shorter_fuzzy_spelling():
    # Borivali Biryani Centre: spelled roughly, the Hindi matched the kebab instead of the kebab biryani.
    dishes = [{"id": str(i), "name": n, "category": "Menu", "sort_order": i}
              for i, n in enumerate(["Mutton Seekh Kebab", "Mutton Seekh Kebab Biryani", "Chicken Dum Biryani"])]
    m = RestaurantMenu({"id": "r"}, [], dishes, 1)
    assert m.find_by_name("मटन सीख कबाब बिरयानी")["name"] == "Mutton Seekh Kebab Biryani"
    assert m.find_by_name("मटन सीख कबाब")["name"] == "Mutton Seekh Kebab"

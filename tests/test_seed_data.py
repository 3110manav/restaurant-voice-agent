"""The restaurant's and the demo stores' data files stay valid: a bad dish here would otherwise only
surface when seeding against the real database."""
import pytest

from app import seed_restaurants


@pytest.mark.parametrize("slug", seed_restaurants.RESTAURANT_FILES)
def test_restaurant_data_is_valid(slug):
    spec = seed_restaurants.load_specs()[slug]
    assert seed_restaurants.check_spec(slug, spec) == []
    assert spec["restaurant"]["slug"] == slug


def test_starter_menu_is_valid():
    assert seed_restaurants.check_spec("starter", seed_restaurants.load_starter_menu()) == []


def test_the_restaurant_menu_is_complete_and_paired():
    spec = seed_restaurants.load_specs()["borivali-biryani-centre"]
    dishes = spec["dishes"]
    names = {d["name"] for d in dishes}
    assert len(dishes) >= 300
    assert sum(1 for d in dishes if d.get("variants")) >= 15  # sizes, half / full, plain / butter
    assert all(d["long_description"] for d in dishes)  # every dish can be explained
    for d in dishes:
        assert d["order_role"] in ("food", "side", "drink", "dessert"), d["name"]
        assert set(d["pairs_with"]) <= names, d["name"]  # a pairing is always a dish on this menu
    by_name = {d["name"]: d for d in dishes}
    assert {"Roti", "Naan"} <= set(by_name["Paneer Tikka Dry"]["pairs_with"])
    assert "Boondi Raita" in by_name["Veg Dum Biryani"]["pairs_with"]
    assert by_name["Chicken Dum Biryani"]["pairs_with"][0].endswith("Raita")
    assert "Bombay Sandwich" not in names


def test_the_store_demos_are_a_kirana_and_a_pharmacy():
    specs = seed_restaurants.load_specs()
    kirana, pharmacy = specs["gupta-general-store"], specs["care-plus-medicals"]
    assert kirana["restaurant"]["business_type"] == "kirana" and len(kirana["dishes"]) == 100
    assert all(d["is_veg"] is None and d.get("brand") for d in kirana["dishes"])  # groceries are not veg or non-veg
    assert pharmacy["restaurant"]["business_type"] == "pharmacy"
    meds = [d for d in pharmacy["dishes"] if d["medicine"]["rx_required"]]
    assert len(meds) >= 8 and all(d["medicine"]["schedule"] in ("H", "H1") for d in meds)
    assert all(d["knowledge_status"] == "ai_draft" for d in pharmacy["dishes"])  # until a pharmacist approves
    assert seed_restaurants.check_spec("care-plus-medicals", pharmacy) == []


def test_no_dish_with_egg_is_marked_veg():
    for spec in seed_restaurants.load_specs().values():
        for d in spec["dishes"]:
            if any("egg" in i.lower() for i in d.get("ingredients", [])):
                assert not d["is_veg"], d["name"]

"""The demo restaurants' data files stay valid: a bad dish here would otherwise only
surface when seeding against the real database."""
import pytest

from app import seed_restaurants


@pytest.mark.parametrize("slug", ["saffron-table", "sarson-da-khet", "slice-station"])
def test_demo_restaurant_data_is_valid(slug):
    spec = seed_restaurants.load_specs()[slug]
    assert seed_restaurants.check_spec(slug, spec) == []
    assert spec["restaurant"]["slug"] == slug


def test_starter_menu_is_valid():
    assert seed_restaurants.check_spec("starter", seed_restaurants.load_starter_menu()) == []


def test_the_three_demos_cover_what_they_are_meant_to_show():
    specs = seed_restaurants.load_specs()
    assert len(specs["saffron-table"]["dishes"]) == 105
    assert sum(1 for d in specs["slice-station"]["dishes"] if d.get("variants")) >= 10  # sizes
    assert sum(1 for d in specs["sarson-da-khet"]["dishes"] if d.get("variants")) >= 5  # half/full
    for spec in specs.values():
        assert all(d["long_description"] for d in spec["dishes"])  # every dish can be explained


def test_no_dish_with_egg_is_marked_veg():
    for spec in seed_restaurants.load_specs().values():
        for d in spec["dishes"]:
            if any("egg" in i.lower() for i in d.get("ingredients", [])):
                assert not d["is_veg"], d["name"]

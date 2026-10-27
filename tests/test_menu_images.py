"""Dish photo matching and processing (no network: Pexels, storage and the database are stand-ins)."""
import io

import pytest
from PIL import Image

from app import menu_images as mi
from app.menu import images


def png(width, height):
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 80, 40)).save(out, "PNG")
    return out.getvalue()


def test_prepare_crops_any_shape_to_800x600_jpeg():
    for w, h in ((1600, 600), (500, 900), (800, 600)):
        result = Image.open(io.BytesIO(images.prepare(png(w, h))))
        assert result.format == "JPEG" and result.size == (800, 600)


def photo(pid, alt):
    return {"id": f"t:{pid}", "alt": alt, "page": f"https://example.com/{pid}", "creator": "Sam",
            "license": "CC BY 2.0", "license_url": "https://creativecommons.org/licenses/by/2.0/",
            "credit": f'"{alt}" by Sam, CC BY 2.0', "download": [f"https://img/{pid}.jpg"]}


def test_queries_go_from_specific_to_broad():
    dish = {"name": "Dragon Roll", "category": "Sushi"}
    assert mi.queries_for(dish) == ["Dragon Roll", "Dragon Roll Sushi", "Sushi food"]
    assert mi.queries_for({"name": "Garlic Naan", "category": "Mains - Veg"}) == ["Garlic Naan"]  # filler-only section adds nothing
    assert mi.name_words("Half Butter Chicken and Rice") == ["butter", "chicken", "rice"]


def test_the_photo_describing_the_dish_wins_over_an_earlier_result():
    search = lambda q: [photo(1, "A bowl of soup"), photo(2, "Creamy butter chicken curry in a bowl")]
    chosen, matched, _ = mi.pick_photo({"name": "Butter Chicken", "category": "Mains"}, search, set())
    assert chosen["id"] == "t:2" and matched


def test_a_photo_is_never_reused_within_a_restaurant():
    search = lambda q: [photo(1, "Margherita pizza"), photo(2, "Pizza with basil")]
    chosen, _, _ = mi.pick_photo({"name": "Margherita Pizza", "category": "Pizza"}, search, {"t:1"})
    assert chosen["id"] == "t:2"


def test_broader_queries_are_tried_when_the_exact_one_finds_nothing():
    calls = []

    def search(q):
        calls.append(q)
        return [] if q == "Cinnamon Dough Bites" else [photo(7, "Sweet dessert plate")]

    chosen, matched, query = mi.pick_photo({"name": "Cinnamon Dough Bites", "category": "Desserts"}, search, set())
    assert chosen["id"] == "t:7" and not matched and query != "Cinnamon Dough Bites" and len(calls) >= 2


def test_nothing_found_means_no_photo():
    assert mi.pick_photo({"name": "Zzz", "category": "Zzz"}, lambda q: [], set())[0] is None


class FakeMenu:
    def __init__(self, dishes):
        self.restaurant = {"id": "r1", "slug": "test"}
        self.menu = dishes


@pytest.fixture
def stubbed(monkeypatch):
    dishes = [
        {"id": "d1", "name": "Butter Chicken", "category": "Mains", "image_url": None},
        {"id": "d2", "name": "Garlic Naan", "category": "Breads", "image_url": "https://already/there.jpg"},
        {"id": "d3", "name": "Paneer Tikka", "category": "Starters", "image_url": None},
    ]
    saved, bumped = {}, []
    monkeypatch.setattr(mi.menu_cache, "invalidate", lambda slug: None)
    monkeypatch.setattr(mi.menu_cache, "get", lambda slug: FakeMenu(dishes))
    monkeypatch.setattr(mi.repository, "update_dish", lambda rid, did, fields: saved.update({did: fields}))
    monkeypatch.setattr(mi.repository, "bump_menu_version", lambda rid: bumped.append(rid))
    stored = []
    return saved, bumped, stored, lambda slug, did, data: (stored.append(did), f"https://cdn/{slug}/{did}.jpg")[1]


SEARCH = lambda q: [photo(11, "Butter chicken curry"), photo(12, "Paneer tikka skewers"), photo(13, "Indian food")]


def test_run_fills_only_dishes_without_photos_and_publishes_once(stubbed):
    saved, bumped, stored, store = stubbed
    credits = {}
    result = mi.run("test", SEARCH, lambda urls: b"jpeg", store, False, False, None, credits)
    assert result == {"photos": 2, "weak": 0, "skipped": 1, "left_out": []}
    assert saved == {"d1": {"image_url": "https://cdn/test/d1.jpg"}, "d3": {"image_url": "https://cdn/test/d3.jpg"}}
    assert bumped == ["r1"]
    assert credits["test"]["Butter Chicken"]["creator"] == "Sam"
    assert credits["test"]["Butter Chicken"]["image_url"] == "https://cdn/test/d1.jpg"
    assert credits["test"]["Butter Chicken"]["credit"].endswith("CC BY 2.0")
    assert credits["test"]["Butter Chicken"]["photo_id"] != credits["test"]["Paneer Tikka"]["photo_id"]


def test_dry_run_changes_nothing(stubbed):
    saved, bumped, stored, store = stubbed
    result = mi.run("test", SEARCH, lambda urls: b"jpeg", store, True, False, None, {})
    assert result["photos"] == 2 and saved == {} and stored == [] and bumped == []


def test_force_redoes_dishes_that_already_have_a_photo(stubbed):
    saved, bumped, stored, store = stubbed
    assert mi.run("test", SEARCH, lambda urls: b"jpeg", store, False, True, None, {})["photos"] == 3


def test_limit_caps_how_many_dishes_are_done(stubbed):
    saved, bumped, stored, store = stubbed
    assert mi.run("test", SEARCH, lambda urls: b"jpeg", store, False, False, 1, {})["photos"] == 1


def test_weak_matches_are_left_without_a_photo_unless_allowed(stubbed):
    saved, bumped, stored, store = stubbed
    vague = lambda q: [photo(21, "A table at a party")]
    strict = mi.run("test", vague, lambda urls: b"jpeg", store, False, False, None, {}, allow_weak=False)
    assert strict["photos"] == 0 and saved == {} and set(strict["left_out"]) == {"Butter Chicken", "Paneer Tikka"}
    lenient = mi.run("test", vague, lambda urls: b"jpeg", store, False, False, None, {}, allow_weak=True)
    assert lenient["photos"] == 1 and lenient["weak"] == 1  # the one photo can't be reused for the second dish


def test_openverse_results_become_credited_photos():
    result = mi._openverse_photo({
        "id": "abc", "title": "Gulab jamun", "creator": "Asha", "license": "by", "license_version": "2.0",
        "license_url": "https://creativecommons.org/licenses/by/2.0/", "width": 1024, "height": 768,
        "url": "https://flickr/orig.jpg", "thumbnail": "https://api/thumb", "foreign_landing_url": "https://flickr/page",
        "tags": [{"name": "dessert"}, {"name": "sweet"}],
    })
    assert result["id"] == "openverse:abc" and result["license"] == "CC BY 2.0"
    assert result["credit"] == '"Gulab jamun" by Asha, CC BY 2.0'
    assert "dessert" in result["alt"] and result["download"] == ["https://flickr/orig.jpg", "https://api/thumb"]


def test_openverse_skips_small_images_and_prefers_the_thumbnail_for_huge_ones():
    assert mi._openverse_photo({"id": "x", "title": "t", "license": "cc0", "width": 300, "url": "u", "thumbnail": "th"}) is None
    huge = mi._openverse_photo({"id": "y", "title": "t", "license": "cc0", "width": 6000, "url": "u", "thumbnail": "th"})
    assert huge["download"] == ["th", "u"] and huge["license"] == "CC0 1.0"


def test_a_photo_must_name_every_word_of_the_dish():
    dish = {"name": "Classic Cold Coffee", "category": "Beverages"}
    mansion = photo(1, "Former Robinson-Squier Mansion, Cold Spring, Buffalo")
    iced = photo(2, "Cold coffee with ice cream")
    assert not mi.is_match(dish, mansion) and mi.is_match(dish, iced)


def test_a_photo_must_also_name_the_dish_type_its_section_implies():
    dish = {"name": "Smoky BBQ Chicken", "category": "Non-Veg Pizzas"}
    wings = photo(1, "Chicken wings in smoky BBQ sauce")
    pizza = photo(2, "Smoky BBQ chicken pizza slice")
    assert mi.context_types(dish) == {"pizza"}
    assert not mi.is_match(dish, wings) and mi.is_match(dish, pizza)
    assert mi.pick_photo(dish, lambda q: [wings], set())[1:2] == (False,)  # only a weak guess is offered


def test_long_names_may_miss_one_word():
    dish = {"name": "Spicy Paneer Tikka Masala Pizza", "category": "Pizza"}
    assert mi.is_match(dish, photo(1, "paneer tikka masala pizza"))


def test_credits_are_listed_only_while_the_dish_still_shows_that_photo(tmp_path, monkeypatch):
    import json

    from app.menu import credits

    f = tmp_path / "credits.json"
    f.write_text(json.dumps({"test": {
        "Butter Chicken": {"image_url": "https://cdn/a.jpg", "credit": '"Butter chicken" by Asha, CC BY 2.0',
                           "license": "CC BY 2.0", "license_url": "https://cc/by", "page": "https://src/1"},
        "Garlic Naan": {"image_url": "https://cdn/old.jpg", "credit": "x", "license": "CC0 1.0"},
    }}))
    monkeypatch.setattr(credits, "CREDITS_FILE", f)
    dishes = [
        {"name": "Butter Chicken", "image_url": "https://cdn/a.jpg"},
        {"name": "Garlic Naan", "image_url": "https://cdn/owner-uploaded.jpg"},  # owner replaced it
        {"name": "Paneer Tikka", "image_url": None},
    ]
    listed = credits.photo_credits("test", dishes)
    assert [c["dish"] for c in listed] == ["Butter Chicken"] and listed[0]["license"] == "CC BY 2.0"
    assert credits.photo_credits("nobody", dishes) == []
    monkeypatch.setattr(credits, "CREDITS_FILE", tmp_path / "missing.json")
    assert credits.photo_credits("test", dishes) == []

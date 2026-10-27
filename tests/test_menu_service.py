"""Menu writes against an in-memory fake of the repository: what gets saved, and —
the point of the whole design — how many embedding calls each kind of edit costs."""
import itertools

import pytest

from app.menu import embedding, repository, service

RESTAURANT = {"id": "r1", "slug": "demo", "name": "Demo", "menu_version": 0}


class FakeDb:
    def __init__(self):
        self.ids = itertools.count(1)
        self.categories, self.dishes, self.variants, self.hashes = [], {}, {}, {}
        self.version = 0

    # category / dish rows
    def list_categories(self, rid):
        return list(self.categories)

    def create_category(self, rid, name, sort_order):
        row = {"id": f"c{next(self.ids)}", "name": name, "sort_order": sort_order}
        self.categories.append(row)
        return row

    def insert_dish(self, row):
        if any(d["name"] == row["name"] for d in self.dishes.values()):
            raise Exception('duplicate key value violates unique constraint "dishes_restaurant_id_name_key" (name)')
        defaults = {
            "is_veg": True, "is_available": True, "knowledge_status": "missing", "sort_order": 0,
            "short_description": "", "long_description": "", "ingredients": [], "allergens": [], "tags": [],
            "spice_level": None, "image_url": None,
        }
        row = {**defaults, **row, "id": f"d{next(self.ids)}"}
        self.dishes[row["id"]] = row
        return row

    def update_dish(self, rid, did, fields):
        if did not in self.dishes:
            return None
        self.dishes[did].update(fields)
        return self.dishes[did]

    def _nested(self, row):
        return {**row, "dish_variants": [{**v, "sort_order": i} for i, v in enumerate(self.variants.get(row["id"], []))]}

    def get_dish(self, rid, did):
        return self._nested(self.dishes[did]) if did in self.dishes else None

    def replace_variants(self, rid, did, variants):
        self.variants[did] = list(variants)

    def find_dish_id_by_name(self, rid, name):
        return next((i for i, d in self.dishes.items() if d["name"] == name), None)

    def delete_dish(self, rid, did):
        self.dishes.pop(did, None)
        self.hashes.pop(did, None)

    def load_menu_rows(self, rid):
        return list(self.categories), [self._nested(d) for d in self.dishes.values()]

    # embeddings / versioning
    def embedding_hashes(self, rid):
        return dict(self.hashes)

    def upsert_embeddings(self, rows):
        for r in rows:
            self.hashes[r["dish_id"]] = r["content_hash"]

    def bump_menu_version(self, rid):
        self.version += 1
        return self.version


@pytest.fixture
def env(monkeypatch):
    db = FakeDb()
    for name in (
        "list_categories create_category insert_dish update_dish get_dish replace_variants find_dish_id_by_name "
        "delete_dish load_menu_rows embedding_hashes upsert_embeddings bump_menu_version"
    ).split():
        monkeypatch.setattr(repository, name, getattr(db, name))
    calls = []

    def fake_embed(texts):
        calls.append(list(texts))
        return [[0.0] * 3 for _ in texts]

    monkeypatch.setattr(embedding, "embed_documents", fake_embed)
    invalidated = []
    monkeypatch.setattr(service.menu_cache, "invalidate", invalidated.append)
    return db, calls, invalidated


def new_dish(**kw):
    return {"name": "Paneer Tikka", "category": "Starters", "price": 280, "short_description": "Grilled paneer", **kw}


def test_creating_a_dish_embeds_exactly_that_dish(env):
    db, calls, invalidated = env
    result = service.save_dish(RESTAURANT, None, new_dish())
    assert result["embedding_synced"] and result["dish"]["category"] == "Starters"
    assert len(calls) == 1 and len(calls[0]) == 1 and "Paneer Tikka" in calls[0][0]
    assert db.version == 1 and invalidated == ["demo"]


def test_a_price_change_costs_zero_embedding_calls(env):
    db, calls, _ = env
    dish_id = service.save_dish(RESTAURANT, None, new_dish())["dish"]["id"]
    calls.clear()
    service.save_dish(RESTAURANT, dish_id, {"price": 320, "is_available": False})
    assert calls == []
    assert db.dishes[dish_id]["price"] == 320


def test_editing_one_dish_re_embeds_only_that_dish(env):
    db, calls, _ = env
    ids = [service.save_dish(RESTAURANT, None, new_dish(name=f"Dish {i}"))["dish"]["id"] for i in range(3)]
    calls.clear()
    service.save_dish(RESTAURANT, ids[1], {"short_description": "Now with extra smoky flavour"})
    assert len(calls) == 1 and len(calls[0]) == 1 and "Dish 1" in calls[0][0] and "smoky" in calls[0][0]


def test_every_edit_bumps_the_version_and_drops_the_cache(env):
    db, _, invalidated = env
    dish_id = service.save_dish(RESTAURANT, None, new_dish())["dish"]["id"]
    service.save_dish(RESTAURANT, dish_id, {"price": 300})
    service.delete_dish(RESTAURANT, dish_id)
    assert db.version == 3 and invalidated == ["demo"] * 3


def test_bulk_import_is_one_embedding_call_and_idempotent(env):
    db, calls, _ = env
    payloads = [new_dish(name=f"Dish {i}") for i in range(5)]
    first = service.bulk_upsert_dishes(RESTAURANT, payloads, source="starter")
    assert first == {"written": 5, "embedded": 5, "unchanged": 0}
    assert len(calls) == 1 and len(calls[0]) == 5
    calls.clear()
    again = service.bulk_upsert_dishes(RESTAURANT, payloads, source="starter")
    assert again == {"written": 5, "embedded": 0, "unchanged": 5} and calls == []
    assert len(db.dishes) == 5  # matched by name, updated in place


def test_embedding_outage_still_saves_the_dish(env, monkeypatch):
    db, calls, _ = env

    def down(_):
        raise RuntimeError("gemini is down")

    monkeypatch.setattr(embedding, "embed_documents", down)
    result = service.save_dish(RESTAURANT, None, new_dish())
    assert result["embedding_synced"] is False
    assert len(db.dishes) == 1 and db.version == 1
    monkeypatch.setattr(embedding, "embed_documents", lambda texts: [[0.0] * 3 for _ in texts])
    assert service.sync_restaurant_embeddings(RESTAURANT) == {"embedded": 1, "unchanged": 0}


def test_variants_set_the_base_price_to_the_cheapest(env):
    db, _, _ = env
    dish = service.save_dish(
        RESTAURANT, None, new_dish(price=999, variants=[{"name": "Large", "price": 549}, {"name": "Regular", "price": 199}])
    )["dish"]
    assert dish["price"] == 199.0
    assert [v["name"] for v in dish["variants"]] == ["Large", "Regular"]


def test_writing_a_story_marks_it_approved(env):
    dish = service.save_dish(RESTAURANT, None, new_dish(long_description="A smoky, charred starter."))["dish"]
    assert dish["knowledge_status"] == "approved"
    assert service.save_dish(RESTAURANT, dish["id"], {"long_description": ""})["dish"]["knowledge_status"] == "missing"


def test_duplicate_dish_name_gives_a_friendly_error(env):
    service.save_dish(RESTAURANT, None, new_dish())
    with pytest.raises(service.MenuValidationError, match="already a dish called"):
        service.save_dish(RESTAURANT, None, new_dish())


def test_updating_a_missing_dish_raises_lookup_error(env):
    with pytest.raises(LookupError):
        service.save_dish(RESTAURANT, "nope", {"price": 1})


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"price": 10}, "needs a name"),
        ({"name": "X"}, "needs a price"),
        ({"name": "X", "price": -1}, "negative"),
        ({"name": "X", "price": 1, "spice_level": "nuclear"}, "spice level"),
        ({"name": "X", "variants": [{"name": "A", "price": 1}, {"name": "a", "price": 2}]}, "duplicate size"),
        ({"name": "X", "variants": [{"name": "", "price": 1}]}, "needs a name"),
        ({"name": "X", "price": 1, "knowledge_status": "maybe"}, "knowledge status"),
    ],
)
def test_validation_rejects_bad_dishes(payload, message):
    with pytest.raises(service.MenuValidationError, match=message):
        service.validate_dish(payload, partial=False)


def test_partial_update_validation_only_checks_what_was_sent():
    assert service.validate_dish({"is_available": False}, partial=True) == {"is_available": False}

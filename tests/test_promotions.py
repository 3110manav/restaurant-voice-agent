"""What the owner pushes (bestsellers, new items) and the three switches that decide whether the waiter does."""
from app.agent import promotions, replies
from app.agent.salesflow import SalesState, dessert_hint, first_order_hint, first_order_offer
from app.menu.snapshot import RestaurantMenu
from app.menu.service import MenuValidationError, validate_dish
import pytest


def dish(i, name, category, role, veg=True, order=0, **extra):
    row = {"id": i, "name": name, "category": category, "price": 100, "veg": veg, "spice_level": "mild", "description": "",
           "long_description": "", "ingredients": [], "allergens": [], "tags": [], "variants": [], "is_available": True,
           "sort_order": order, "order_role": role, "pairs_with": [], "is_bestseller": False, "is_new": False, "promo_note": ""}
    row.update(extra)
    return row


def raw_menu():
    return [
        dish("f1", "Chicken Dum Biryani", "Biryani", "food", veg=False, pairs_with=["Veg Raita", "Chaas"]),
        dish("f2", "Butter Chicken", "Mughlai", "food", veg=False, is_bestseller=True, order=2),
        dish("f3", "Paneer Lava Tikka", "Tandoor", "food", is_new=True, promo_note="launched this week, with a smoked chilli marinade", order=3),
        dish("s1", "Veg Raita", "Sides", "side", order=4),
        dish("k1", "Chaas", "Coolers", "drink", order=5),
        dish("d1", "Gulab Jamun", "Desserts", "dessert", order=6),
    ]


def menu_for(restaurant=None):
    return RestaurantMenu({"id": "r", "slug": "x", **(restaurant or {})}, [{"name": c} for c in ("Biryani", "Mughlai", "Tandoor", "Sides", "Coolers", "Desserts")], raw_menu(), 1)


def first_offer(restaurant=None, ordered="f1"):
    menu = menu_for(restaurant)
    state = SalesState(settings=promotions.settings(menu.restaurant))
    cart = [{"id": ordered, "price": 100, "quantity": 1}]
    return first_order_offer(state, menu.menu, menu.get, cart, [menu.get(ordered)])


def test_every_switch_is_on_until_the_owner_turns_it_off():
    assert promotions.settings(None) == promotions.Promotions(True, True, True)
    assert promotions.settings({"suggest_pairings": None}).pairings  # a row from before the migration
    assert not promotions.settings({"promote_new_items": False}).new_items


def test_a_dish_is_featured_only_for_the_switches_that_are_on():
    flagged = {"is_new": True, "is_bestseller": True}
    assert promotions.featured_of(flagged, promotions.Promotions()) == ["new", "bestseller"]
    assert promotions.featured_of(flagged, promotions.Promotions(bestsellers=False)) == ["new"]
    assert promotions.featured_of(flagged, promotions.Promotions(new_items=False, bestsellers=False)) == []


def test_the_first_order_mentions_the_new_item_with_the_owners_note():
    offer = first_offer()
    assert offer.sides == ["Veg Raita"] and offer.drinks == ["Chaas"]
    assert offer.promo == {"name": "Paneer Lava Tikka", "why": "new", "note": "launched this week, with a smoked chilli marinade"}
    hint = offer.hint
    assert "Paneer Lava Tikka is new on the menu" in hint and "smoked chilli marinade" in hint


def test_with_new_items_off_a_bestseller_is_mentioned_instead():
    offer = first_offer({"promote_new_items": False})
    assert offer.promo["name"] == "Butter Chicken" and offer.promo["why"] == "bestseller"


def test_with_both_promotions_off_only_the_pairings_remain():
    offer = first_offer({"promote_new_items": False, "promote_bestsellers": False})
    assert offer.promo is None and offer.sides == ["Veg Raita"]


def test_with_pairings_off_only_the_promotion_is_said():
    offer = first_offer({"suggest_pairings": False})
    assert offer.drinks == [] and offer.sides == [] and offer.promo["name"] == "Paneer Lava Tikka"
    assert "Want" not in replies._offer(offer.event, "en")
    assert "new on our menu" in replies._offer(offer.event, "en")


def test_with_everything_off_the_waiter_says_nothing_extra():
    off = {"suggest_pairings": False, "promote_new_items": False, "promote_bestsellers": False}
    assert first_offer(off) is None
    menu = menu_for(off)
    state = SalesState(settings=promotions.settings(menu.restaurant))
    assert dessert_hint(state, menu.menu, menu.get, [{"id": "f1", "price": 100, "quantity": 1}]) is None


def test_the_dessert_offer_follows_the_pairings_switch():
    menu = menu_for()
    cart = [{"id": "f1", "price": 100, "quantity": 1}]
    assert "Gulab Jamun" in dessert_hint(SalesState(), menu.menu, menu.get, cart)
    assert dessert_hint(SalesState(settings=promotions.Promotions(pairings=False)), menu.menu, menu.get, cart) is None


def test_a_dish_already_ordered_is_not_promoted():
    assert first_offer(ordered="f2").promo["name"] == "Paneer Lava Tikka"  # the bestseller itself was just ordered
    offer = first_offer(ordered="f3")  # the new item was just ordered; the other pick is non-veg and the order is veg
    assert offer.promo is None


def test_an_all_veg_order_is_not_promoted_a_non_veg_dish():
    offer = first_offer({"promote_new_items": False}, ordered="f3")  # veg cart; the only bestseller is non-veg
    assert offer is None or offer.promo is None


def test_the_offer_is_said_in_the_guests_language():
    offer = first_offer().event
    assert "Waise" in replies._offer(offer, "hinglish") and "वैसे" in replies._offer(offer, "hi")
    assert replies._offer(offer, "en").startswith("Want Chaas with that, or some Veg Raita on the side?")


def test_two_sides_are_offered_together():
    menu = menu_for()
    menu.menu[0]["pairs_with"] = ["Veg Raita", "Roti"]
    menu.menu.append(dish("s2", "Roti", "Breads", "side", order=7))
    menu.by_id["s2"] = menu.menu[-1]
    state = SalesState(settings=promotions.Promotions(new_items=False, bestsellers=False))
    offer = first_order_offer(state, menu.menu, menu.get, [{"id": "f1", "price": 100, "quantity": 1}], [menu.get("f1")])
    assert offer.sides == ["Veg Raita", "Roti"]
    assert "Veg Raita or Roti on the side" in replies._offer(offer.event, "en")


def test_the_prompt_lists_only_what_is_switched_on():
    block = promotions.prompt_block(menu_for().menu)
    assert "Bestsellers" in block and "Butter Chicken" in block and "Paneer Lava Tikka" in block and "smoked chilli" in block
    assert "Butter Chicken" not in promotions.prompt_block(menu_for({"promote_bestsellers": False}).menu)
    assert promotions.prompt_block(menu_for({"promote_bestsellers": False, "promote_new_items": False}).menu) == ""


def test_search_results_mark_the_dishes_being_pushed():
    menu = menu_for()
    assert promotions.label(menu.get("f3")) == " [NEW on the menu]"
    assert promotions.label(menu.get("f2")) == " [bestseller]"
    assert promotions.label(menu.get("s1")) == ""


def test_the_owner_can_set_the_flags_and_the_note_is_bounded():
    assert validate_dish({"is_bestseller": True, "is_new": False, "promo_note": "  new   this week "}, partial=True) == {
        "is_bestseller": True, "is_new": False, "promo_note": "new this week"}
    with pytest.raises(MenuValidationError):
        validate_dish({"promo_note": "x" * 201}, partial=True)


def test_re_seeding_never_undoes_what_the_owner_chose(monkeypatch):
    from app.menu import repository, service

    written = []
    monkeypatch.setattr(service, "_Categories", lambda rid: type("C", (), {"ensure": lambda self, n: "c1"})())
    monkeypatch.setattr(repository, "find_dish_id_by_name", lambda rid, name: "d-existing" if name == "Old Dish" else None)
    monkeypatch.setattr(service, "_write_dish", lambda rid, dish_id, fields, cats, source, status_hint: written.append((dish_id, fields)) or "x")
    monkeypatch.setattr(service, "_sync_embeddings", lambda rid, dishes: {"embedded": 0, "unchanged": 0})
    monkeypatch.setattr(service, "_dish_dicts", lambda rid: [])
    monkeypatch.setattr(service, "_publish", lambda restaurant: None)
    flags = {"is_bestseller": True, "is_new": True, "promo_note": "from the file"}
    service.bulk_upsert_dishes({"id": "r", "slug": "s"}, [
        {"name": "Old Dish", "price": 10, **flags}, {"name": "Brand New Dish", "price": 20, **flags}], "manual")
    old, new = written
    assert old[0] == "d-existing" and "is_bestseller" not in old[1] and "promo_note" not in old[1]
    assert new[0] is None and new[1]["is_bestseller"] is True and new[1]["promo_note"] == "from the file"

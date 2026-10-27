"""Cross-sell: what is offered, when, and never twice."""
from app.agent.salesflow import SalesState, dessert_hint, first_order_hint, role_of
from app.agent.tools import build_tools


def dish(i, name, category, price, veg=True, spice="mild", tags=(), available=True, order=0):
    return {"id": i, "name": name, "category": category, "price": price, "veg": veg, "spice_level": spice,
            "description": "", "long_description": "", "ingredients": [], "allergens": [], "tags": list(tags),
            "variants": [], "is_available": available, "sort_order": order}


MENU = [
    dish("m1", "Butter Chicken", "Mains", 460, veg=False, spice="medium"),
    dish("m2", "Paneer Tikka Masala", "Mains", 380, spice="medium"),
    dish("b1", "Garlic Naan", "Breads", 90),
    dish("r1", "Boondi Raita", "Sides & Raita", 90, tags=["cooling"]),
    dish("d1", "Masala Chai", "Beverages", 60, order=1),
    dish("d2", "Sweet Lassi", "Beverages", 120, order=2),
    dish("d3", "Cola", "Beverages", 70, order=0, available=False),
    dish("s1", "Gulab Jamun", "Desserts", 140, order=1),
    dish("s2", "Phirni", "Desserts", 130, order=2),
]
BY_ID = {d["id"]: d for d in MENU}


class FakeStore:
    menu = MENU

    def get(self, i):
        return BY_ID.get(i)

    def find_by_name(self, name):
        return next((d for d in MENU if d["name"].lower() == name.strip().lower()), None)


def setup(monkeypatch=None):
    cart, sales = [], SalesState()
    import app.erp as erp
    erp.record_order = lambda *a, **k: None
    tools = {t.name: t for t in build_tools(cart, FakeStore(), "s", "waiter", restaurant_id="r", table_no="3", sales=sales)}
    return cart, sales, tools


def add(tools, *names):
    return tools["add_to_cart"].invoke({"items": [{"name": n} for n in names]})


def test_roles_come_from_the_section_name():
    assert [role_of(d) for d in (MENU[0], MENU[2], MENU[3], MENU[4], MENU[7])] == ["food", "side", "side", "drink", "dessert"]


def test_first_main_gets_a_drink_and_side_suggestion_with_prices():
    cart, sales, tools = setup()
    out = add(tools, "Butter Chicken")
    assert "Cart: 1x Butter Chicken. Total: ₹460." in out
    assert "HINT FOR YOU ONLY" in out
    assert "Sweet Lassi" in out and "Masala Chai" in out  # spicy dish: cooling drink ranked first
    assert out.index("Sweet Lassi") < out.index("Masala Chai")
    assert "Cola" not in out  # unavailable
    assert "Boondi Raita" in out  # cooling side ranked first for spicy food


def test_the_offer_is_made_once_only():
    cart, sales, tools = setup()
    assert "HINT" in add(tools, "Butter Chicken")
    assert "HINT" not in add(tools, "Paneer Tikka Masala")


def test_no_drink_suggestion_when_one_is_already_ordered():
    cart, sales, tools = setup()
    add(tools, "Sweet Lassi")
    out = add(tools, "Butter Chicken")
    assert "a drink" not in out and "Boondi Raita" in out


def test_ordering_only_a_drink_or_sweet_does_not_trigger_the_first_order_offer():
    cart, sales, tools = setup()
    assert "HINT" not in add(tools, "Sweet Lassi")
    assert "HINT" not in add(tools, "Gulab Jamun")


def test_veg_tables_are_not_offered_non_veg_items():
    menu = MENU + [dish("d9", "Chicken Soup", "Beverages", 50, veg=False, order=-1)]
    state = SalesState()
    hint = first_order_hint(state, menu, {d["id"]: d for d in menu}.get, [{"id": "m2", "price": 380, "quantity": 1}], [BY_ID["m2"]])
    assert "Chicken Soup" not in hint


def test_checkout_holds_once_to_offer_dessert_then_places_the_order():
    cart, sales, tools = setup()
    add(tools, "Butter Chicken")
    first = tools["checkout"].invoke({})
    assert first.startswith("Order not placed yet") and "Gulab Jamun" in first and "Phirni" in first
    second = tools["checkout"].invoke({})
    assert second.startswith("Order placed")


def test_no_dessert_offer_if_a_dessert_is_already_in_the_cart():
    cart, sales, tools = setup()
    add(tools, "Butter Chicken", "Gulab Jamun")
    assert tools["checkout"].invoke({}).startswith("Order placed")


def test_empty_cart_checkout_is_unchanged():
    cart, sales, tools = setup()
    assert "empty" in tools["checkout"].invoke({})


def test_dessert_hint_needs_a_dessert_on_the_menu():
    menu = [d for d in MENU if role_of(d) != "dessert"]
    assert dessert_hint(SalesState(), menu, BY_ID.get, [{"id": "m1", "price": 1, "quantity": 1}]) is None


def test_one_call_adds_several_items_and_reports_the_total():
    cart, sales, tools = setup()
    out = tools["add_to_cart"].invoke({"items": [{"name": "Butter Chicken", "quantity": 2}, {"name": "Garlic Naan", "quantity": 3}]})
    assert "Total: ₹1,190." in out and len(cart) == 2


def test_absurd_quantities_are_refused():
    cart, sales, tools = setup()
    out = tools["add_to_cart"].invoke({"items": [{"name": "Garlic Naan", "quantity": 500}]})
    assert "confirm the number" in out and cart == []


def test_a_veg_table_is_not_offered_egg_desserts():
    menu = MENU + [dish("s3", "Choco Lava Cake", "Desserts", 99, veg=False, order=-1)]
    cart = [{"id": "m2", "price": 380, "quantity": 1}]
    hint = dessert_hint(SalesState(), menu, {d["id"]: d for d in menu}.get, cart)
    assert "Choco Lava Cake" not in hint and "Gulab Jamun" in hint


def test_section_names_are_matched_as_whole_words():
    # "Classic" contains "lassi": the real Slice Station section "Classic Veg Pizzas" must stay food.
    for category, role in [("Classic Veg Pizzas", "food"), ("Signature Veg Pizzas", "food"), ("Non-Veg Pizzas", "food"),
                           ("Garlic Bread & Sides", "side"), ("Sides & Raita", "side"), ("Rice & Biryani", "side"),
                           ("Beverages", "drink"), ("Drinks", "drink"), ("Sweet Treats", "dessert"), ("Desserts", "dessert"),
                           ("Mains - Veg", "food"), ("Starters", "food"), ("Dim Sum", "food"), ("Breads", "side")]:
        assert role_of({"category": category}) == role, category


def test_a_real_pizza_order_gets_the_drink_offer_and_the_dessert_hold():
    menu = [
        dish("p1", "Margherita", "Classic Veg Pizzas", 499, spice=None),
        dish("g1", "Garlic Bread", "Garlic Bread & Sides", 129, order=0),
        dish("d1", "Chilled Soft Drink", "Beverages", 79),
        dish("s1", "Cinnamon Dough Bites", "Desserts", 129),
    ]
    by_id = {d["id"]: d for d in menu}
    cart = [{"id": "p1", "price": 499, "quantity": 1}]
    first = first_order_hint(SalesState(), menu, by_id.get, cart, [menu[0]])
    assert first and "Chilled Soft Drink" in first and "Garlic Bread" in first
    assert "Cinnamon Dough Bites" in dessert_hint(SalesState(), menu, by_id.get, cart)

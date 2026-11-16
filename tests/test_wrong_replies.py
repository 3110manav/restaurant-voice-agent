"""Replies seen going wrong on a real call: a pizza offered garlic naan and masala chai, and "sushi" called missing
when the menu has a Sushi section."""
from app.agent import salesflow, tools

DISHES = [
    {"id": "p1", "name": "Four Cheese Pizza", "category": "Pizza", "veg": True},
    {"id": "m1", "name": "Paneer Tikka", "category": "Starters", "veg": True, "spice_level": "medium"},
    {"id": "n1", "name": "Garlic Naan", "category": "Breads", "veg": True},
    {"id": "r1", "name": "Jeera Rice", "category": "Rice", "veg": True},
    {"id": "d1", "name": "Mango Lassi", "category": "Drinks", "veg": True},
    {"id": "d2", "name": "Masala Chai", "category": "Drinks", "veg": True},
    {"id": "d3", "name": "Cola", "category": "Drinks", "veg": True},
    {"id": "s1", "name": "California Roll", "category": "Sushi", "veg": True, "is_available": True},
    {"id": "s2", "name": "Spicy Tuna Roll", "category": "Sushi", "veg": False, "is_available": True},
    {"id": "s3", "name": "Salmon Nigiri", "category": "Sushi", "veg": False, "is_available": False},
]
BY_ID = {d["id"]: d for d in DISHES}


def offer(cart_ids):
    cart = [{"id": i, "name": BY_ID[i]["name"], "quantity": 1, "price": 100} for i in cart_ids]
    added = [BY_ID[i] for i in cart_ids]
    return salesflow.first_order_offer(salesflow.SalesState(), DISHES, BY_ID.get, cart, added)


def test_a_pizza_is_not_offered_indian_breads_or_drinks():
    # On this menu those are the only breads and drinks but the cola: the cola is fine, the rest is not.
    result = offer(["p1"])
    assert result is not None and result.drinks == ["Cola"] and result.sides == []


def test_nothing_is_offered_rather_than_something_that_does_not_go():
    only_indian = [d for d in DISHES if d["id"] not in ("d3",)]
    cart = [{"id": "p1", "name": "Four Cheese Pizza", "quantity": 1, "price": 100}]
    assert salesflow.first_order_offer(salesflow.SalesState(), only_indian, BY_ID.get, cart, [BY_ID["p1"]]) is None


def test_an_indian_dish_still_gets_its_bread_and_lassi():
    result = offer(["m1"])
    assert result is not None
    assert "Mango Lassi" in result.drinks and result.sides == ["Garlic Naan"]
    assert "Cola" in result.drinks or len(result.drinks) == 2


def test_a_menu_with_no_recognisable_cuisine_keeps_the_old_behaviour():
    plain = [{"id": "a", "name": "House Special", "category": "Mains", "veg": True},
             {"id": "b", "name": "Fresh Juice", "category": "Drinks", "veg": True},
             {"id": "c", "name": "Side Salad", "category": "Sides", "veg": True}]
    by = {d["id"]: d for d in plain}
    result = salesflow.first_order_offer(salesflow.SalesState(), plain, by.get, [{"id": "a", "name": "House Special", "quantity": 1, "price": 1}], [plain[0]])
    assert result is not None and result.drinks == ["Fresh Juice"] and result.sides == ["Side Salad"]


def test_the_table_pages_suggestion_card_follows_the_same_rule():
    cart = [{"id": "p1", "name": "Four Cheese Pizza", "quantity": 1, "price": 100}]
    names = [d["name"] for d in salesflow.pick(DISHES, BY_ID.get, cart, "drink", 3)]
    assert "Mango Lassi" not in names and "Masala Chai" not in names and "Cola" in names


class Menu:
    menu = DISHES
    categories = ["Pizza", "Starters", "Breads", "Rice", "Drinks", "Sushi"]

    def find_by_name(self, name):
        return next((d for d in DISHES if d["name"].lower() == name.lower()), None)


def test_naming_a_menu_section_lists_its_dishes_instead_of_saying_it_is_missing():
    item, message = tools._resolve(Menu(), "sushi")
    assert item is None
    assert "section of the menu" in message and "California Roll" in message and "Spicy Tuna Roll" in message
    assert "Salmon Nigiri" not in message  # not available right now
    assert "never say the restaurant doesn't have it" in message
    assert tools._resolve(Menu(), "pizzas")[1].startswith("'pizzas' is a section")


def test_a_word_that_is_neither_a_dish_nor_a_section_is_still_not_found():
    item, message = tools._resolve(Menu(), "unicorn steak")
    assert item is None and "Couldn't find" in message

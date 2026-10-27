"""Tests for the cart tools themselves (no LLM/API calls needed).

Agent-loop and RAG behavior are exercised manually via cli.py, since those
need live API keys.
"""
from app.agent.tools import add_item_to_cart, build_tools, remove_item_from_cart_by_id


class FakeMenuStore:
    """Minimal stand-in for MenuStore.find_by_name, no embeddings involved."""

    def __init__(self, items):
        self._items = {item["name"].lower(): item for item in items}

    def find_by_name(self, name):
        return self._items.get(name.strip().lower())


def make_tools():
    cart = []
    menu_store = FakeMenuStore(
        [
            {"id": "main-01", "name": "Butter Chicken", "price": 14.0, "veg": False},
            {"id": "bread-01", "name": "Garlic Naan", "price": 3.5, "veg": True},
        ]
    )
    tools = {t.name: t for t in build_tools(cart, menu_store)}
    return cart, tools


def test_add_to_cart_creates_line():
    cart, tools = make_tools()
    tools["add_to_cart"].invoke({"items": [{"name": "Butter Chicken", "quantity": 2}]})
    assert cart == [{"id": "main-01", "name": "Butter Chicken", "price": 14.0, "quantity": 2}]


def test_add_to_cart_twice_merges_quantity():
    cart, tools = make_tools()
    tools["add_to_cart"].invoke({"items": [{"name": "Butter Chicken", "quantity": 1}]})
    tools["add_to_cart"].invoke({"items": [{"name": "Butter Chicken", "quantity": 2}]})
    assert len(cart) == 1
    assert cart[0]["quantity"] == 3


def test_add_to_cart_unknown_item():
    cart, tools = make_tools()
    result = tools["add_to_cart"].invoke({"items": [{"name": "Pad Thai", "quantity": 1}]})
    assert "Couldn't find" in result
    assert cart == []


def test_remove_from_cart_partial_and_full():
    cart, tools = make_tools()
    tools["add_to_cart"].invoke({"items": [{"name": "Garlic Naan", "quantity": 3}]})
    tools["remove_from_cart"].invoke({"name": "Garlic Naan", "quantity": 1})
    assert cart[0]["quantity"] == 2
    tools["remove_from_cart"].invoke({"name": "Garlic Naan", "quantity": 2})
    assert cart == []


def test_checkout_empty_cart():
    _, tools = make_tools()
    result = tools["checkout"].invoke({})
    assert "empty" in result.lower()


def test_checkout_with_items():
    cart, tools = make_tools()
    tools["add_to_cart"].invoke({"items": [{"name": "Butter Chicken", "quantity": 1}]})
    result = tools["checkout"].invoke({})
    assert "Order placed" in result
    assert "₹14" in result


# add_item_to_cart / remove_item_from_cart_by_id back the direct /cart/add
# and /cart/remove API routes used by product-grid "Add" buttons — tested
# directly since that path never goes through the LLM tool.


def test_add_item_to_cart_by_id_creates_line():
    cart: list = []
    item = {"id": "main-01", "name": "Butter Chicken", "price": 14.0}
    add_item_to_cart(cart, item, 2)
    assert cart == [{"id": "main-01", "name": "Butter Chicken", "price": 14.0, "quantity": 2}]


def test_add_item_to_cart_by_id_merges_quantity():
    cart: list = []
    item = {"id": "main-01", "name": "Butter Chicken", "price": 14.0}
    add_item_to_cart(cart, item, 1)
    add_item_to_cart(cart, item, 2)
    assert len(cart) == 1
    assert cart[0]["quantity"] == 3


def test_remove_item_from_cart_by_id_partial_and_full():
    cart: list = []
    item = {"id": "bread-01", "name": "Garlic Naan", "price": 3.5}
    add_item_to_cart(cart, item, 3)
    remove_item_from_cart_by_id(cart, "bread-01", 1)
    assert cart[0]["quantity"] == 2
    remove_item_from_cart_by_id(cart, "bread-01", 2)
    assert cart == []


def test_remove_item_from_cart_by_id_unknown_item():
    cart: list = []
    result = remove_item_from_cart_by_id(cart, "nope", 1)
    assert "isn't in the cart" in result

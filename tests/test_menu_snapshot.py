"""Menu snapshots: name matching, the tools' size/availability/explain behavior,
embedding text, and the version-checked cache — all without a database."""
import pytest

from app.agent.tools import add_item_to_cart, build_tools, remove_item_from_cart_by_id
from app.menu import embedding
from app.menu.snapshot import MenuCache, RestaurantMenu, dish_from_row


def dish(id, name, price=100.0, category="Mains", veg=True, **extra):
    base = {
        "id": id, "name": name, "category": category, "price": price, "veg": veg, "spice_level": "mild",
        "description": f"{name} short", "long_description": "", "ingredients": ["onion"], "allergens": [],
        "tags": [], "variants": [], "is_available": True, "image_url": None, "knowledge_status": "missing",
        "sort_order": 0,
    }
    return {**base, **extra}


PIZZA_SIZES = [{"name": "Regular", "price": 199.0}, {"name": "Medium", "price": 399.0}, {"name": "Large", "price": 549.0}]


@pytest.fixture
def menu():
    dishes = [
        dish("1", "Butter Chicken", 350, veg=False, long_description="Creamy tomato curry with soft chicken."),
        dish("2", "Garlic Naan", 90),
        dish("3", "Margherita Classic", 199, category="Pizza", variants=PIZZA_SIZES),
        dish("4", "Double Cheese Margherita", 229, category="Pizza", variants=PIZZA_SIZES),
        dish("5", "Dal Makhani", 260),
        dish("6", "Sold Out Special", 500, is_available=False),
    ]
    cats = [{"name": "Mains"}, {"name": "Pizza"}]
    return RestaurantMenu({"id": "r1", "slug": "r", "name": "R", "menu_version": 1}, cats, dishes, 1)


def test_exact_and_case_insensitive(menu):
    assert menu.find_by_name("butter chicken")["id"] == "1"
    assert menu.find_by_name("  GARLIC   NAAN ")["id"] == "2"


def test_dish_name_inside_a_longer_phrase(menu):
    assert menu.find_by_name("two garlic naan please")["id"] == "2"


def test_unique_substring(menu):
    assert menu.find_by_name("dal")["id"] == "5"


def test_ambiguous_returns_none_but_offers_candidates(menu):
    assert menu.find_by_name("margherita") is None
    assert {d["name"] for d in menu.candidates("margherita")} == {"Margherita Classic", "Double Cheese Margherita"}


def test_fuzzy_match_survives_a_transcription_error(menu):
    assert menu.find_by_name("buter chiken")["id"] == "1"
    assert menu.find_by_name("garlic nan")["id"] == "2"


def test_nothing_close_is_none(menu):
    assert menu.find_by_name("sushi platter") is None
    assert menu.candidates("sushi platter") == []


def test_keyword_fallback_when_semantic_search_is_down(menu, monkeypatch):
    def boom(_):
        raise RuntimeError("embedding api down")

    monkeypatch.setattr(embedding, "embed_query", boom)
    names = [d["name"] for d in menu.search("creamy chicken")]
    assert names and names[0] == "Butter Chicken"


def test_keyword_search_skips_unavailable_dishes(menu, monkeypatch):
    monkeypatch.setattr(embedding, "embed_query", lambda _: (_ for _ in ()).throw(RuntimeError()))
    assert all(d["is_available"] for d in menu.search("special sold out"))


def test_categories_follow_menu_order(menu):
    assert menu.categories == ["Mains", "Pizza"]


# ---------------------------------------------------------------- sizes / cart --


def test_size_dish_without_a_size_asks_which_one(menu):
    cart = []
    msg = add_item_to_cart(cart, menu.find_by_name("Margherita Classic"), 1)
    assert cart == [] and "Regular" in msg and "Large" in msg and "which" in msg.lower()


def test_size_is_matched_loosely_and_priced_by_size(menu):
    cart = []
    add_item_to_cart(cart, menu.get("3"), 2, "med")
    assert cart == [{"id": "3", "name": "Margherita Classic", "price": 399.0, "quantity": 2, "variant": "Medium"}]


def test_sizes_of_one_dish_are_separate_lines(menu):
    cart = []
    pizza = menu.get("3")
    add_item_to_cart(cart, pizza, 1, "Regular")
    add_item_to_cart(cart, pizza, 1, "Large")
    add_item_to_cart(cart, pizza, 1, "Large")
    assert [(l["variant"], l["quantity"]) for l in cart] == [("Regular", 1), ("Large", 2)]


def test_remove_by_id_respects_the_size(menu):
    cart = []
    pizza = menu.get("3")
    add_item_to_cart(cart, pizza, 1, "Regular")
    add_item_to_cart(cart, pizza, 1, "Large")
    remove_item_from_cart_by_id(cart, "3", 1, "Large")
    assert [l["variant"] for l in cart] == ["Regular"]


def test_unavailable_dish_is_refused(menu):
    cart = []
    assert "isn't available" in add_item_to_cart(cart, menu.get("6"), 1)
    assert cart == []


def test_single_size_dish_needs_no_size(menu):
    cart = []
    add_item_to_cart(cart, menu.get("2"), 1)
    assert "variant" not in cart[0]


# ---------------------------------------------------------------------- tools --


def tool_map(menu, restaurant_id="r1"):
    cart = []
    tools = build_tools(cart, menu, "s", "waiter", restaurant_id=restaurant_id, table_no="7")
    return cart, {t.name: t for t in tools}


def test_ambiguous_name_makes_the_tool_ask(menu):
    cart, tools = tool_map(menu)
    out = tools["add_to_cart"].invoke({"items": [{"name": "margherita", "quantity": 1}]})
    assert cart == [] and "Margherita Classic" in out and "Double Cheese Margherita" in out


def test_explain_dish_is_restaurant_mode_only(menu):
    assert "explain_dish" in tool_map(menu)[1]
    assert "explain_dish" not in tool_map(menu, restaurant_id=None)[1]


def test_explain_dish_returns_the_story(menu):
    out = tool_map(menu)[1]["explain_dish"].invoke({"name": "butter chicken"})
    assert "Creamy tomato curry" in out and "Ingredients" in out


def test_explain_dish_without_a_story_says_not_to_invent(menu):
    out = tool_map(menu)[1]["explain_dish"].invoke({"name": "Garlic Naan"})
    assert "hasn't written detailed notes" in out


def test_checkout_records_the_restaurant_and_table(menu, monkeypatch):
    recorded = {}
    monkeypatch.setattr("app.erp.record_order", lambda *a, **kw: recorded.update(args=a, kw=kw))
    cart, tools = tool_map(menu)
    tools["add_to_cart"].invoke({"items": [{"name": "Margherita Classic", "quantity": 1, "variant": "Large"}]})
    out = tools["checkout"].invoke({})
    assert "Margherita Classic (Large)" in out
    assert recorded["kw"] == {"restaurant_id": "r1", "table_no": "7"}
    assert recorded["args"][2][0]["variant"] == "Large"


# ------------------------------------------------------------------ embeddings --


def test_embedding_text_ignores_price_and_availability():
    a = dish("1", "Butter Chicken", 350)
    b = dish("1", "Butter Chicken", 999, is_available=False, image_url="x.png")
    assert embedding.dish_embedding_text(a) == embedding.dish_embedding_text(b)
    assert embedding.content_hash(embedding.dish_embedding_text(a)) == embedding.content_hash(
        embedding.dish_embedding_text(b)
    )


def test_embedding_text_changes_when_meaning_changes():
    a = dish("1", "Butter Chicken")
    assert embedding.dish_embedding_text(a) != embedding.dish_embedding_text({**a, "description": "now spicy"})
    assert embedding.dish_embedding_text(a) != embedding.dish_embedding_text({**a, "veg": False})


def test_dish_from_row_orders_variants_and_converts_prices():
    row = {
        "id": "1", "name": "Pizza", "category_id": "c", "price": "199.00", "is_veg": True, "is_available": True,
        "dish_variants": [
            {"name": "Large", "price": "549", "sort_order": 1},
            {"name": "Regular", "price": "199", "sort_order": 0},
        ],
    }
    d = dish_from_row(row, {"c": "Pizza"})
    assert d["price"] == 199.0 and [v["name"] for v in d["variants"]] == ["Regular", "Large"]
    assert d["category"] == "Pizza"


# ----------------------------------------------------------------------- cache --


def test_menu_cache_reloads_only_when_the_version_changes(monkeypatch):
    from app.menu import repository

    state = {"version": 1, "loads": 0}

    def restaurant(slug):
        return {"id": "r1", "slug": slug, "name": "R", "menu_version": state["version"]}

    def load(_):
        state["loads"] += 1
        return [{"id": "c", "name": "Mains", "sort_order": 0}], [
            {"id": "d1", "category_id": "c", "name": f"Dish v{state['version']}", "price": 10, "is_veg": True,
             "is_available": True}
        ]

    monkeypatch.setattr(repository, "get_restaurant_by_slug", restaurant)
    monkeypatch.setattr(repository, "load_menu_rows", load)
    monkeypatch.setattr(repository, "get_menu_version", lambda _: state["version"])

    cache = MenuCache(version_check_seconds=0)  # check the version on every get
    assert cache.get("r").menu[0]["name"] == "Dish v1"
    assert cache.get("r").menu[0]["name"] == "Dish v1"
    assert state["loads"] == 1  # same version: served from memory
    state["version"] = 2  # an owner edit elsewhere bumps the version
    assert cache.get("r").menu[0]["name"] == "Dish v2"
    assert state["loads"] == 2


def test_menu_cache_unknown_restaurant_is_none(monkeypatch):
    from app.menu import repository

    monkeypatch.setattr(repository, "get_restaurant_by_slug", lambda s: None)
    assert MenuCache().get("nope") is None


# ------------------------------------------------------------ rate-limit handling --


def test_provider_rate_limit_becomes_agent_busy_error():
    import groq
    import httpx

    from app.agent.graph import AgentBusyError, RestaurantOrderingAgent

    class Boom:
        def invoke(self, *_a, **_kw):
            raise groq.RateLimitError(
                "rate limited",
                response=httpx.Response(429, request=httpx.Request("POST", "http://x")),
                body=None,
            )

    agent = object.__new__(RestaurantOrderingAgent)
    agent.session_id = "s"
    agent.restaurant_id = None
    agent.events = []
    agent.graph = Boom()
    with pytest.raises(AgentBusyError):
        agent.send("hello")


def test_reads_retry_once_after_a_stale_connection_but_writes_do_not(monkeypatch):
    import httpx

    from app.menu import repository

    calls = {"read": 0, "write": 0}

    @repository._read
    def flaky_read():
        calls["read"] += 1
        if calls["read"] == 1:
            raise httpx.ReadError("stale connection")
        return "ok"

    assert flaky_read() == "ok" and calls["read"] == 2

    def always_failing_read():
        raise httpx.ReadError("down")

    with pytest.raises(httpx.ReadError):
        repository._read(always_failing_read)()  # a second failure still surfaces

    # A write is not wrapped: one failure surfaces immediately instead of being repeated.
    assert not hasattr(repository.insert_dish, "__wrapped__")
    assert hasattr(repository.get_restaurant_by_slug, "__wrapped__")

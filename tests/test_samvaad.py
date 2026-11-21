"""The Samvaad tool API: what Sarvam's agent calls for one restaurant's menu, cart and order.
The LLM is Sarvam's and is left out; these are the rules that hold whatever it does."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.phone import carts, outbox, repository
from app.phone.catalog import StoreCatalog
from app.samvaad import router as samvaad_router
from app.samvaad import session as samvaad_session
from tests.fake_supabase import FakeSupabase

TOKEN = "tool-secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
OWNER = "919000000001"
CUSTOMER = "919000000002"
MENU = [
    {"id": "pbm", "name": "Paneer Butter Masala", "category": "Main Course", "price": 280, "veg": True,
     "aliases": ["paneer makhani"], "spice_level": "medium"},
    {"id": "naan", "name": "Butter Naan", "category": "Breads", "price": 60, "veg": True},
    {"id": "lassi", "name": "Sweet Lassi", "category": "Beverages", "price": 90, "veg": True},
    {"id": "jamun", "name": "Gulab Jamun", "category": "Desserts", "price": 120, "veg": True},
    {"id": "pizza", "name": "Margherita Pizza", "category": "Pizzas", "price": 250, "veg": True,
     "variants": [{"name": "Regular", "price": 250}, {"name": "Large", "price": 450}]},
]


@pytest.fixture
def fake(monkeypatch):
    client = FakeSupabase()
    monkeypatch.setattr(db, "get_client", lambda: client)
    monkeypatch.setattr(outbox, "flush_in_background", lambda: None)
    monkeypatch.setattr(carts, "run_later", lambda fn, *args: fn(*args))  # saved at once, so a test can look
    monkeypatch.setenv("SAMVAAD_TOOL_TOKEN", TOKEN)
    monkeypatch.setattr(samvaad_session, "MIN_CONFIRM_SECONDS", 0)
    # Restaurants read their menu from Supabase (LiveMenu); here the same menu comes from memory.
    monkeypatch.setattr(samvaad_session, "_menu_and_restaurant", lambda store: (StoreCatalog(MENU), "rest-1"))
    monkeypatch.setattr(samvaad_session, "sessions", samvaad_session.SessionRegistry())
    monkeypatch.setattr(samvaad_router, "sessions", samvaad_session.sessions)
    return client


@pytest.fixture
def store(fake):
    return repository.save_store(
        {
            "id": "store-1", "slug": "spice-route", "name": "Spice Route", "business_type": "restaurant",
            "agent_name": "Kabir", "phone_number": "+918000000000", "owner_whatsapp": OWNER,
            "restaurant_slug": "spice-route", "upi_id": "spice@okbank", "upi_payee_name": "Spice Route",
            "upi_is_merchant": False,
        }
    )


@pytest.fixture
def api(store):
    app = FastAPI()
    app.include_router(samvaad_router.router)
    return TestClient(app)


def tool(api, name, **body):
    body = {"interaction_id": "call-1", "store_slug": "spice-route", "caller": f"+{CUSTOMER}", **body}
    response = api.post(f"/samvaad/tools/{name}", json=body, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def order_to_read_back(api) -> dict:
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 2}, {"name": "Butter Naan", "quantity": 4}])
    held = tool(api, "set_order_details", order_type="delivery", address="12 MG Road")
    assert "dessert" in held["result"] and "Gulab Jamun" in held["result"]  # suggested once, before the read-back
    return tool(api, "read_back_order")


# ------------------------------------------------------------------ security --


def test_every_route_needs_the_tool_token(api):
    body = {"interaction_id": "call-1", "store_slug": "spice-route"}
    assert api.post("/samvaad/start", json=body).status_code == 401
    assert api.post("/samvaad/tools/view_cart", json=body, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert api.post("/samvaad/end", json=body).status_code == 401


def test_without_a_configured_token_nothing_runs(api, monkeypatch):
    monkeypatch.delenv("SAMVAAD_TOOL_TOKEN")
    response = api.post("/samvaad/start", json={"interaction_id": "c", "store_slug": "spice-route"}, headers=AUTH)
    assert response.status_code == 503


# -------------------------------------------------------------- finding the store --


def test_start_finds_the_store_by_slug_and_returns_greeting_variables(api):
    response = api.post("/samvaad/start", json={"interaction_id": "c1", "store_slug": "spice-route"}, headers=AUTH)
    body = response.json()
    assert body["store_name"] == "Spice Route" and body["agent_name"] == "Kabir"
    assert body["cart_summary"] == "empty"


def test_a_phone_call_finds_the_store_by_the_dialled_number(api):
    body = {"interaction_id": "c2", "called_number": "08000000000", "store_slug": ""}
    assert api.post("/samvaad/start", json=body, headers=AUTH).json()["store_slug"] == "spice-route"


def test_the_default_store_answers_when_nothing_names_one(api, monkeypatch):
    monkeypatch.setenv("SAMVAAD_DEFAULT_STORE", "spice-route")
    body = {"interaction_id": "c3", "store_slug": "@store_slug"}  # an unfilled Samvaad variable
    assert api.post("/samvaad/start", json=body, headers=AUTH).json()["store_slug"] == "spice-route"


def test_an_unknown_store_is_refused(api):
    body = {"interaction_id": "c4", "store_slug": "nowhere"}
    assert api.post("/samvaad/start", json=body, headers=AUTH).status_code == 404


def test_the_tool_editors_send_button_works_without_an_interaction_id(api):
    # Samvaad's "Send" test has no call yet, so the built-in Interaction ID arrives empty.
    body = {"interaction_id": None, "store_slug": "spice-route", "caller": "", "query": "paneer"}
    response = api.post("/samvaad/tools/search_menu", json=body, headers=AUTH)
    assert response.status_code == 200 and "Paneer Butter Masala" in response.json()["result"]


def test_a_tool_call_without_a_start_still_finds_its_store(api):
    assert "Paneer Butter Masala" in tool(api, "search_menu", query="paneer")["result"]


# ----------------------------------------------------------------- the cart --


def test_add_to_cart_matches_names_and_adds_up_the_total_in_code(api):
    body = tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 2}, {"name": "Butter Naan", "quantity": 4}])
    assert body["cart_summary"] == "2 x Paneer Butter Masala, 4 x Butter Naan"
    assert body["cart_total"] == "₹800"
    assert "Sweet Lassi" in body["result"]  # the drink suggestion for a first order, decided in code


def test_one_item_can_come_as_flat_fields_or_json_text(api):
    tool(api, "add_to_cart", item_name="Sweet Lassi", quantity="2")
    body = tool(api, "add_to_cart", items='[{"name": "Butter Naan"}]')
    assert body["cart_summary"] == "2 x Sweet Lassi, 1 x Butter Naan"


def test_a_dish_with_sizes_asks_which_one(api):
    assert "Regular" in tool(api, "add_to_cart", item_name="Margherita Pizza")["result"]
    assert tool(api, "add_to_cart", item_name="Margherita Pizza", variant="large")["cart_total"] == "₹450"


def test_a_dish_not_on_the_menu_is_never_reported_as_added(api):
    body = tool(api, "add_to_cart", items=[{"name": "Butter Naan", "quantity": 2}, {"name": "Veg Kolhapuri"}])
    assert body["result"].startswith("NOT ADDED, not on the menu: Veg Kolhapuri.")
    assert body["cart_summary"] == "2 x Butter Naan"
    # The exact words: what went in, what isn't on the menu, and dishes we do have.
    assert body["say"].startswith("2 Butter Naan जोड़ दिया। माफ़ कीजिए, Veg Kolhapuri हमारे मेन्यू में नहीं है।")
    assert "Say exactly this to the guest:" in body["result"]


def test_only_versions_of_the_same_dish_are_a_which_one_question():
    # A real call: "Shahi Paneer" was offered Paneer Tikka Masala, a different dish, so it isn't on the menu.
    assert not samvaad_session._names_every_word("Shahi Paneer", ["Paneer Tikka Masala", "Paneer Tikka Pizza"])
    assert samvaad_session._names_every_word("chicken pizza", ["BBQ Chicken Pizza", "Buffalo Chicken Pizza"])
    assert samvaad_session._names_every_word("चिकन पिज़्ज़ा", ["BBQ Chicken Pizza", "Buffalo Chicken Pizza"])


def test_remove_and_view_cart(api):
    tool(api, "add_to_cart", item_name="Butter Naan", quantity=3)
    assert tool(api, "remove_from_cart", item_name="Butter Naan", quantity=1)["cart_summary"] == "2 x Butter Naan"
    assert "₹120" in tool(api, "view_cart")["result"]


# ------------------------------------------------------------- placing the order --


def test_nothing_is_placed_before_the_read_back(api, fake):
    tool(api, "add_to_cart", item_name="Butter Naan")
    assert tool(api, "checkout")["result"].startswith("Order not placed")
    assert "orders" not in fake.tables


def test_the_read_back_gives_the_exact_words_to_say(api):
    body = order_to_read_back(api)
    assert body["say"].startswith("आपका ऑर्डर") and "800" in body["say"]


def test_a_checkout_straight_after_the_read_back_is_refused(api, fake, monkeypatch):
    monkeypatch.setattr(samvaad_session, "MIN_CONFIRM_SECONDS", 60)
    order_to_read_back(api)
    assert tool(api, "checkout")["result"].startswith("Order not placed")  # the model didn't wait for a yes
    assert "orders" not in fake.tables


def test_after_the_yes_the_order_is_saved_and_whatsapp_queued(api, fake):
    order_to_read_back(api)
    body = tool(api, "checkout")
    assert body["result"].startswith("Order placed") and body["order_placed"] and body["order_id"]
    saved = fake.tables["orders"][0]
    assert saved["total"] == 800 and saved["store_id"] == "store-1" and saved["address"] == "12 MG Road"
    assert {m["kind"] for m in fake.tables["message_outbox"]} == {"owner_order", "customer_bill"}
    assert tool(api, "checkout")["result"].startswith("Order placed already.")
    assert len(fake.tables["orders"]) == 1


def test_a_change_after_the_read_back_needs_a_new_one(api, fake):
    order_to_read_back(api)
    tool(api, "add_to_cart", item_name="Sweet Lassi")
    assert tool(api, "checkout")["result"].startswith("Order not placed")
    tool(api, "read_back_order")
    assert tool(api, "checkout")["result"].startswith("Order placed")
    assert fake.tables["orders"][0]["total"] == 890


def test_english_calls_get_english_read_backs(api):
    tool(api, "add_to_cart", item_name="Butter Naan", language="English")
    tool(api, "set_order_details", order_type="pickup")
    assert tool(api, "read_back_order", language="English")["say"].startswith("Your order")


def test_a_callback_alerts_the_owner(api, fake):
    tool(api, "request_callback", reason="wants to book a party")
    alert = fake.tables["message_outbox"][0]
    assert alert["kind"] == "callback_alert" and alert["recipient"] == OWNER


def test_the_end_hook_closes_the_call_log(api, fake):
    order_to_read_back(api)
    tool(api, "checkout")
    response = api.post("/samvaad/end", json={"interaction_id": "call-1", "transcript": "hi"}, headers=AUTH)
    assert response.json() == {"closed": True, "outcome": "ordered"}
    assert fake.tables["phone_calls"][0]["outcome"] == "ordered"


# --------------------------------------------------------------- browser proxy --


def test_signed_url_only_for_the_configured_agent(api, monkeypatch):
    monkeypatch.setenv("SARVAM_ORG_ID", "org")
    monkeypatch.setenv("SARVAM_WORKSPACE_ID", "ws")
    monkeypatch.setenv("SARVAM_APP_ID", "app")
    monkeypatch.setenv("SARVAM_API_KEY", "sk")
    assert api.get("/samvaad/browser/orgs/org/workspaces/ws/apps/other/url").status_code == 404

    seen = {}

    class Reply:
        status_code = 200

        def json(self):
            return {"url": "wss://signed", "reference_id": "r1"}

    def fake_get(url, params, headers, timeout):
        seen.update(url=url, params=params, headers=headers)
        return Reply()

    monkeypatch.setattr(samvaad_router.httpx, "get", fake_get)
    response = api.get("/samvaad/browser/orgs/org/workspaces/ws/apps/app/url?interaction_type=call&evil=1")
    assert response.json() == {"url": "wss://signed", "reference_id": "r1"}
    assert seen["headers"] == {"X-API-Key": "sk"} and seen["params"] == {"interaction_type": "call"}
    assert seen["url"].endswith("orgs/org/workspaces/ws/apps/app/url")


def test_the_browser_sees_the_live_cart_of_its_call(api):
    assert api.get("/samvaad/browser/cart/call-1").json()["active"] is False
    tool(api, "add_to_cart", item_name="Butter Naan", quantity=2)
    body = api.get("/samvaad/browser/cart/call-1").json()
    assert body["active"] and body["cart_summary"] == "2 x Butter Naan" and body["store_name"] == "Spice Route"


def test_the_live_cart_works_with_samvaads_interaction_ids(api):
    call_id = "20261119/4d6019b6-15:08:22-aw179716"  # the shape Samvaad really sends, with a slash
    tool(api, "add_to_cart", interaction_id=call_id, item_name="Butter Naan")
    assert api.get(f"/samvaad/browser/cart/{call_id}").json()["cart_summary"] == "1 x Butter Naan"


def test_a_dish_can_be_removed_by_a_name_said_differently(api):
    tool(api, "add_to_cart", item_name="Paneer Butter Masala", quantity=3)
    body = tool(api, "remove_from_cart", item_name="paneer makhani", quantity=1)  # the menu's other name for it
    assert body["cart_summary"] == "2 x Paneer Butter Masala"


def test_a_caller_without_a_whatsapp_number_is_asked_for_one(api, fake):
    # Samvaad's test chat identifies the tester by email, so there is no number to send the bill to.
    tool(api, "add_to_cart", caller="tester@example.com", item_name="Butter Naan")
    held = tool(api, "set_order_details", caller="tester@example.com", order_type="pickup")
    assert "WhatsApp" in held["result"] and "व्हाट्सएप नंबर" in held["say"]
    assert "Say exactly this to the guest: " + held["say"] in held["result"]  # visible through {{result}}
    refused = tool(api, "checkout", caller="tester@example.com")
    assert refused["result"].startswith("Order not placed") and "व्हाट्सएप नंबर" in refused["say"]
    tool(api, "set_order_details", order_type="pickup", whatsapp_number="9876543210")
    assert tool(api, "read_back_order")["say"].startswith("आपका ऑर्डर")


def test_a_store_without_upi_bills_as_text_paid_on_delivery(api, fake):
    store = repository.get_store_by_slug("spice-route")
    repository.save_store({**store, "upi_id": None, "upi_payee_name": None})
    tool(api, "add_to_cart", item_name="Butter Naan", language="English")
    tool(api, "set_order_details", order_type="pickup", language="English")
    said = tool(api, "read_back_order", language="English")["say"]
    assert "QR" not in said and "The bill will come on WhatsApp" in said
    assert "pay on delivery" in tool(api, "checkout", language="English")["say"]
    bill = next(m for m in fake.tables["message_outbox"] if m["kind"] == "customer_bill")
    assert bill["body"]["type"] == "text" and "Pay on delivery or at pickup" in bill["body"]["text"]


# ------------------------------------------------------------ requests on a dish --


def test_a_change_to_a_dish_is_read_back_saved_and_sent_to_the_kitchen(api, fake):
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 1, "note": "without capsicum"}])
    tool(api, "add_to_cart", items=[{"name": "Butter Naan", "quantity": 2}])
    tool(api, "add_note", item_name="Butter Naan", note="well done")  # asked for after it was added
    tool(api, "set_order_details", order_type="delivery", address="12 MG Road, Borivali West")
    read_back = tool(api, "read_back_order")
    assert "without capsicum" in read_back["result"] and "well done" in read_back["result"]
    tool(api, "checkout")
    order = fake.tables["orders"][0]
    assert {line["name"]: line.get("note") for line in order["items"]} == {
        "Paneer Butter Masala": "without capsicum", "Butter Naan": "well done",
    }
    ticket = next(m for m in fake.tables["message_outbox"] if m["kind"] == "owner_order")["body"]["text"]
    assert "Note: without capsicum" in ticket and "Note: well done" in ticket


def test_a_note_on_a_dish_not_in_the_cart_is_refused_not_lost(api):
    result = tool(api, "add_note", item_name="Butter Naan", note="crispy")["result"]
    assert "isn't in the cart" in result


# ------------------------------------------------------------ who ordered, and the saved cart --


def place_order(api, **details):
    tool(api, "add_to_cart", items=[{"name": "Butter Naan", "quantity": 2}])
    tool(api, "set_order_details", order_type="delivery", address="12 MG Road, Borivali West", **details)
    tool(api, "set_order_details", order_type="delivery", address="12 MG Road, Borivali West", **details)  # past the dessert hold
    tool(api, "read_back_order")
    return tool(api, "checkout")


def test_an_order_carries_who_ordered_it_and_what_they_asked_for(api, fake):
    tool(api, "add_to_cart", items=[{"name": "Butter Naan", "quantity": 2, "note": "well done"}])
    tool(api, "add_special_request", request="deliver after 8 pm")
    tool(api, "set_order_details", order_type="delivery", address="12 MG Road, Borivali West", customer_name="Priya Shah")
    tool(api, "set_order_details", order_type="delivery", address="12 MG Road, Borivali West")  # past the dessert hold
    read_back = tool(api, "read_back_order")["result"]
    assert "deliver after 8 pm" in read_back and "well done" in read_back
    assert tool(api, "checkout")["order_placed"]

    order = fake.tables["orders"][0]
    customer = fake.tables["customers"][0]
    assert order["customer_name"] == "Priya Shah" and order["special_requests"] == "deliver after 8 pm"
    assert order["customer_id"] == customer["id"] and order["channel"] == "call" and order["phone_verified"] is True
    assert customer["phone"] == f"+{CUSTOMER}" and customer["name"] == "Priya Shah" and customer["restaurant_id"] == "rest-1"
    assert order["customer_phone"] == f"+{CUSTOMER}"
    ticket = next(m for m in fake.tables["message_outbox"] if m["kind"] == "owner_order")["body"]["text"]
    assert "Special request: deliver after 8 pm" in ticket and "Priya Shah" in ticket
    assert fake.tables["phone_calls"][0]["customer_id"] == customer["id"]


def test_a_number_heard_as_a_name_is_not_kept(api, fake):
    place_order(api, customer_name="98765 43210")
    assert fake.tables["orders"][0]["customer_name"] is None and fake.tables["customers"][0].get("name") is None


def test_a_number_the_caller_only_told_us_never_renames_an_existing_customer(api, fake):
    fake.tables["customers"] = [{"id": "c-1", "restaurant_id": "rest-1", "phone": f"+{CUSTOMER}", "name": "Real Owner"}]
    tool(api, "add_to_cart", items=[{"name": "Butter Naan", "quantity": 1}], channel="browser", caller="")
    tool(api, "set_order_details", order_type="pickup", whatsapp_number=CUSTOMER[2:], customer_name="Someone Else", channel="browser")
    assert fake.tables["customers"][0]["name"] == "Real Owner"
    assert fake.tables["carts"][0]["phone_verified"] is False


def test_the_cart_is_saved_as_it_changes_and_closes_with_the_order(api, fake):
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 1, "note": "without capsicum"}])
    saved = fake.tables["carts"][0]
    assert saved["interaction_id"] == "call-1" and saved["status"] == "open" and saved["total"] == 280
    assert saved["items"][0]["note"] == "without capsicum" and saved["customer_phone"] == f"+{CUSTOMER}"
    place_order(api)
    assert len(fake.tables["carts"]) == 1
    cart = fake.tables["carts"][0]
    assert cart["status"] == "ordered" and cart["order_id"] == fake.tables["orders"][0]["id"] and cart["closed_at"]


def test_a_call_that_ends_with_items_and_no_order_leaves_an_abandoned_cart(api, fake):
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 2}])
    api.post("/samvaad/end", json={"interaction_id": "call-1", "end_reason": "user_hangup"}, headers=AUTH)
    assert fake.tables["carts"][0]["status"] == "abandoned"
    call = fake.tables["phone_calls"][0]
    assert call["outcome"] == "abandoned" and call["end_reason"] == "user_hangup" and call["interaction_id"] == "call-1"


def test_a_call_with_nothing_in_the_cart_leaves_no_cart(api, fake):
    tool(api, "search_menu", query="paneer")
    api.post("/samvaad/end", json={"interaction_id": "call-1"}, headers=AUTH)
    assert fake.tables.get("carts", []) == []


def test_an_abandoned_cart_is_won_back_when_the_caller_orders_later(api, fake):
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 1}], interaction_id="call-1")
    api.post("/samvaad/end", json={"interaction_id": "call-1"}, headers=AUTH)
    tool(api, "add_to_cart", items=[{"name": "Butter Naan", "quantity": 1}], interaction_id="call-2")
    for _ in range(2):
        tool(api, "set_order_details", order_type="pickup", interaction_id="call-2")
    tool(api, "read_back_order", interaction_id="call-2")
    assert tool(api, "checkout", interaction_id="call-2")["order_placed"]
    first, second = fake.tables["carts"]
    assert first["status"] == "recovered" and first["order_id"] == second["order_id"]


def test_a_restart_in_the_middle_of_a_call_picks_the_saved_cart_back_up(api, fake, monkeypatch):
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 2, "note": "less oil"}])
    tool(api, "add_special_request", request="call when you arrive")
    registry = samvaad_session.SessionRegistry()  # the API restarted: no sessions in memory
    monkeypatch.setattr(samvaad_session, "sessions", registry)
    monkeypatch.setattr(samvaad_router, "sessions", registry)
    body = tool(api, "view_cart")
    assert body["cart"][0]["quantity"] == 2 and body["cart"][0]["note"] == "less oil"
    assert len(fake.tables["phone_calls"]) == 1  # the same call, not a second one
    assert len(fake.tables["carts"]) == 1


def test_the_sweeper_asks_the_database_to_close_stale_carts(fake):
    fake.rpc_results["close_stale_carts"] = {"abandoned": 2}
    assert carts.sweep() == {"abandoned": 2}
    assert fake.rpc_calls == [("close_stale_carts", {})]


def test_a_database_failure_while_saving_never_breaks_the_call(api, fake, monkeypatch):
    def broken(fn, *args):
        raise RuntimeError("database is down")

    monkeypatch.setattr(carts, "run_later", broken)
    # The real run_later swallows this; the point here is the order rules still answer the guest.
    monkeypatch.setattr(carts, "run_later", lambda fn, *args: carts._guarded(broken, fn, *args))
    assert tool(api, "add_to_cart", items=[{"name": "Butter Naan", "quantity": 1}])["cart"][0]["quantity"] == 1

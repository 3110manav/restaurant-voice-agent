"""The Samvaad tool API: what Sarvam's agent calls for one restaurant's menu, cart and order.
The LLM is Sarvam's and is left out; these are the rules that hold whatever it does."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.phone import carts, messages, numbers, outbox, repository
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
    asked = tool(api, "set_order_details", order_type="delivery", address="12 MG Road")
    # The caller's own number is not read out: they know it (28 Nov feedback).
    assert asked["say"] == "आपका नाम बता दीजिए? और बिल व्हाट्सएप पर इसी नंबर पर भेज दूँ जिससे आप कॉल कर रहे हैं, या किसी और नंबर पर?"
    assert not any(ch.isdigit() for ch in asked["say"])
    held = tool(api, "set_order_details", order_type="delivery", customer_name="Priya")  # "Priya, isi pe"
    # The drink suggestion came with the first dishes, so no dessert as well: one suggestion per call.
    assert "dessert" not in held["result"] and held["result"].startswith("Read back")
    return held


def details(api, **body) -> dict:
    """set_order_details, then the guest's answer to the one name-and-number question."""
    tool(api, "set_order_details", **body)
    return tool(api, "set_order_details", **{k: v for k, v in body.items() if k in ("order_type", "language", "caller")})


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
    started = api.post("/samvaad/start", json=body, headers=AUTH).json()
    assert started["line_ready"] is False and "not connected" in started["result"]  # said politely, no order taken
    assert api.post("/samvaad/tools/view_cart", json=body, headers=AUTH).status_code == 404


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
    assert body["say"].startswith("Priya जी, आपका ऑर्डर") and "800" in body["say"]
    assert "इसी नंबर पर आएगा" in body["say"] and "0 0 0 2" not in body["say"]  # their own number isn't spelt out


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
    details(api, order_type="pickup", language="English")
    assert tool(api, "read_back_order", language="English")["say"].startswith("Your order")


def test_a_callback_alerts_the_owner(api, fake):
    tool(api, "request_callback", reason="wants to book a party")
    alert = fake.tables["message_outbox"][0]
    assert alert["kind"] == "callback_alert" and alert["recipient"] == OWNER
    assert "Callbacks" in alert["body"]["text"]
    # ...and a support ticket on the owner's dashboard, with the number to call back.
    ticket = fake.tables["requests"][0]
    assert ticket["type"] == "callback" and ticket["status"] == "open" and ticket["details"] == "wants to book a party"
    assert ticket["restaurant_id"] == "rest-1" and ticket["customer_phone"] == f"+{CUSTOMER}" and ticket["call_id"]
    tool(api, "request_callback", reason="again")
    assert len(fake.tables["requests"]) == 1  # asked twice in one call: still one ticket


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
    assert held["say"] == "आपका नाम और व्हाट्सएप नंबर बता दीजिए? बिल उसी पर भेजूँगा।"
    assert "Say exactly this to the guest: " + held["say"] in held["result"]  # visible through {{result}}
    assert "आपका ऑर्डर" not in held["say"]  # asked in one short line: the order is read back once, later
    refused = tool(api, "checkout", caller="tester@example.com")
    assert refused["result"].startswith("Order not placed")
    tool(api, "set_order_details", order_type="pickup", whatsapp_number="9876543210")
    said = tool(api, "read_back_order")["say"]
    assert said.startswith("आपका ऑर्डर") and "9 8 7 6 5, 4 3 2 1 0 नंबर पर" in said  # read out in full


def test_an_order_is_never_dropped_for_want_of_a_whatsapp_number(api, fake):
    caller = "tester@example.com"
    tool(api, "add_to_cart", caller=caller, item_name="Butter Naan")
    assert "व्हाट्सएप नंबर" in tool(api, "set_order_details", caller=caller, order_type="pickup")["say"]
    # The guest has no WhatsApp: asked once, the order goes ahead without the bill.
    read_back = tool(api, "read_back_order", caller=caller)
    if "dessert" in read_back["result"]:
        read_back = tool(api, "read_back_order", caller=caller)
    assert "बिल व्हाट्सएप पर नहीं आ पाएगा" in read_back["say"]
    placed = tool(api, "checkout", caller=caller)
    assert placed["result"].startswith("Order placed") and "व्हाट्सएप" not in placed["say"]
    assert [m["kind"] for m in fake.tables["message_outbox"]] == ["owner_order"]  # the store hears; no bill
    assert "did NOT get a bill" in fake.tables["message_outbox"][0]["body"]["text"]


# ------------------------------------------------------------- repeated calls --


def test_the_same_add_sent_again_is_not_repeated(api):
    # A real call: "4 Paneer Tikka" sent five times in 13 seconds became 17.
    tool(api, "add_to_cart", item_name="Butter Naan", quantity=4)
    again = tool(api, "add_to_cart", item_name="butter naan", quantity=4)
    assert again["cart_summary"] == "4 x Butter Naan" and again["result"].startswith("NOT DONE AGAIN")
    both = tool(api, "add_to_cart", items=[{"name": "Butter Naan", "quantity": 4}, {"name": "Sweet Lassi"}])
    assert both["cart_summary"] == "4 x Butter Naan, 1 x Sweet Lassi"
    # A different amount is a different request, and goes through.
    assert tool(api, "add_to_cart", item_name="Butter Naan", quantity=1)["cart_summary"].startswith("5 x Butter Naan")


def test_the_same_add_later_on_goes_through(api, monkeypatch):
    monkeypatch.setattr(samvaad_session, "DUPLICATE_SECONDS", 0)
    tool(api, "add_to_cart", item_name="Butter Naan", quantity=2)
    assert tool(api, "add_to_cart", item_name="Butter Naan", quantity=2)["cart_summary"] == "4 x Butter Naan"


def test_the_same_remove_sent_again_does_not_take_away_a_whole_dish(api):
    # "Ek hi karo" sent twice once took Margherita from 2 to 0.
    tool(api, "add_to_cart", item_name="Butter Naan", quantity=2)
    assert tool(api, "remove_from_cart", item_name="Butter Naan", quantity=1)["cart_summary"] == "1 x Butter Naan"
    again = tool(api, "remove_from_cart", item_name="Butter Naan", quantity=1)
    assert again["cart_summary"] == "1 x Butter Naan" and again["result"].startswith("NOT DONE AGAIN")


def test_a_store_without_upi_bills_as_text_paid_on_delivery(api, fake):
    store = repository.get_store_by_slug("spice-route")
    repository.save_store({**store, "upi_id": None, "upi_payee_name": None})
    tool(api, "add_to_cart", item_name="Butter Naan", language="English")
    details(api, order_type="pickup", language="English")
    said = tool(api, "read_back_order", language="English")["say"]
    assert "QR" not in said and "The bill will come on WhatsApp" in said
    # Said briefly on the call; how to pay is on the bill itself.
    assert tool(api, "checkout", language="English")["say"] == "Your order is placed, and the bill is on WhatsApp. Thank you!"
    bill = next(m for m in fake.tables["message_outbox"] if m["kind"] == "customer_bill")
    assert bill["body"]["type"] == "text" and "Pay on delivery or at pickup" in bill["body"]["text"]


# ------------------------------------------------------------ requests on a dish --


def test_a_change_to_a_dish_is_read_back_saved_and_sent_to_the_kitchen(api, fake):
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 1, "note": "without capsicum"}])
    tool(api, "add_to_cart", items=[{"name": "Butter Naan", "quantity": 2}])
    tool(api, "add_note", item_name="Butter Naan", note="well done")  # asked for after it was added
    details(api, order_type="delivery", address="12 MG Road, Borivali West")
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


# ------------------------------------------------------------ one confirmation --
# A real complaint: the agent confirmed the address, offered a dessert, then read the whole order and address
# back again. The guest should hear the order once, unless it changes or they ask.

READ_BACK = "ऑर्डर पक्का कर दूँ?"


def test_a_whole_call_has_one_read_back(api, fake):
    said = []
    for name, body in [
        ("add_to_cart", {"items": [{"name": "paneer makhani", "quantity": 1}]}),
        ("add_special_request", {"request": "no cutlery"}),
        ("set_order_details", {"order_type": "delivery", "address": "12 MG Road"}),
        ("set_order_details", {"order_type": "delivery", "customer_name": "Priya"}),  # past the one question
        ("set_order_details", {"order_type": "delivery", "customer_name": "Priya Shah"}),  # the model resends
        ("checkout", {}),
    ]:
        said.append(tool(api, name, **body).get("say") or "")
    assert sum(READ_BACK in s for s in said) == 1
    assert "no cutlery" in said[3] and fake.tables["orders"][0]["customer_name"] == "Priya Shah"


def test_a_special_request_before_the_read_back_is_only_noted(api):
    tool(api, "add_to_cart", item_name="Butter Naan")
    body = tool(api, "add_special_request", request="deliver after 8 pm")
    assert "say" not in body and "Do not read the order back now" in body["result"]
    assert "delivery or pickup" not in body["result"]  # no longer pushes the agent ahead of the guest


def test_a_special_request_after_the_read_back_reads_it_again_once(api):
    order_to_read_back(api)
    body = tool(api, "add_special_request", request="ring the bell twice")
    assert READ_BACK in body["say"] and "ring the bell twice" in body["say"]
    assert tool(api, "checkout")["result"].startswith("Order placed")


def test_the_name_and_number_question_is_asked_once(api):
    tool(api, "add_to_cart", item_name="Butter Naan")
    first = tool(api, "set_order_details", order_type="pickup")
    assert "नाम" in first["say"]
    again = tool(api, "read_back_order")  # the guest would rather not give a name: carry on without it
    assert "नाम" not in (again.get("say") or "") and "नाम" not in again["result"]


def test_same_number_in_words_means_the_callers_own(api, fake):
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 1}])
    tool(api, "set_order_details", order_type="pickup")
    body = tool(api, "set_order_details", order_type="pickup", whatsapp_number="same", customer_name="Ravi")
    assert "valid" not in body["result"]
    tool(api, "read_back_order")
    assert tool(api, "checkout")["order_placed"]
    assert fake.tables["orders"][0]["customer_phone"] == f"+{CUSTOMER}"


def test_another_number_for_the_bill_is_read_out_to_catch_a_misheard_digit(api, fake):
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 1}])
    tool(api, "set_order_details", order_type="pickup")
    said = tool(api, "set_order_details", order_type="pickup", whatsapp_number="98765 43210", customer_name="Ravi")["say"]
    assert "9 8 7 6 5, 4 3 2 1 0 नंबर पर" in said  # the whole number, digit by digit
    tool(api, "checkout")
    bill = next(m for m in fake.tables["message_outbox"] if m["kind"] == "customer_bill")
    assert bill["recipient"] == "919876543210"


def test_a_name_and_number_given_up_front_skip_the_question(api):
    tool(api, "add_to_cart", item_name="Butter Naan")
    body = tool(api, "set_order_details", order_type="pickup", customer_name="Ravi", whatsapp_number="9876543210")
    assert "नाम" not in (body.get("say") or "") and "इसी नंबर" not in (body.get("say") or "")


def test_each_call_starts_with_its_restaurants_rule_book(api, fake):
    fake.tables.setdefault("restaurants", []).append(
        {"id": "rest-1", "slug": "spice-route", "agent_rules": "Pasta comes in penne or spaghetti: always ask which."}
    )
    body = api.post("/samvaad/start", json={"interaction_id": "c9", "store_slug": "spice-route"}, headers=AUTH).json()
    assert body["house_rules"] == "Pasta comes in penne or spaghetti: always ask which."


def test_a_restaurant_without_a_rule_book_starts_with_none(api):
    body = api.post("/samvaad/start", json={"interaction_id": "c10", "store_slug": "spice-route"}, headers=AUTH).json()
    assert body["house_rules"] == "none"
# ------------------------------------------------------------- opening hours --


def test_a_closed_store_takes_no_new_order_and_says_when_it_opens(api, monkeypatch):
    monkeypatch.setattr(samvaad_session.hours, "is_open", lambda store, now=None: False)
    body = tool(api, "add_to_cart", item_name="Butter Naan")
    assert body["result"].startswith("NOT ADDED: the store is closed") and body["cart_summary"] == "empty"
    assert body["say"].startswith("माफ़ कीजिए, Spice Route")  # the hours module words it (tests/test_hours.py)


def test_an_order_under_way_at_closing_time_is_finished(api, monkeypatch):
    tool(api, "add_to_cart", item_name="Butter Naan")
    monkeypatch.setattr(samvaad_session.hours, "is_open", lambda store, now=None: False)
    assert tool(api, "add_to_cart", item_name="Sweet Lassi")["cart_summary"] == "1 x Butter Naan, 1 x Sweet Lassi"


# ------------------------------------------------------- the total the guest heard --


def test_checkout_goes_through_when_the_guest_heard_the_real_total(api, fake):
    order_to_read_back(api)  # ₹800
    heard = "Kabir: आपका ऑर्डर: 2 Paneer Butter Masala, 4 Butter Naan। कुल ८०० रुपये। ऑर्डर पक्का कर दूँ?\nGuest: haan"
    assert tool(api, "checkout", transcript=heard)["result"].startswith("Order placed")


def test_a_made_up_total_sends_the_order_back_for_a_true_read_back(api, fake):
    # A real call: Kabir read back ₹2,400; the cart was ₹6,380; the guest's "haan" placed the real cart.
    order_to_read_back(api)
    heard = [{"role": "agent", "text": "Your order comes to 2,400 rupees. Shall I place it?"}, {"role": "user", "text": "haan"}]
    refused = tool(api, "checkout", transcript=heard)
    assert refused["result"].startswith("Order not placed yet: the guest has not heard the real total, 800")
    assert "कुल 800 रुपये" in refused["say"] and not fake.tables.get("orders")
    # Still not heard the second time: placed, never a loop, and the owner is asked to confirm the total.
    placed = tool(api, "checkout", transcript=heard)
    assert placed["result"].startswith("Order placed")
    owner = next(m for m in fake.tables["message_outbox"] if m["kind"] == "owner_order")
    assert "may not have heard this total" in owner["body"]["text"]


def test_without_a_transcript_checkout_is_unchanged(api, fake):
    order_to_read_back(api)
    assert tool(api, "checkout", transcript="@Call Transcript")["result"].startswith("Order placed")


def test_amounts_are_found_as_whole_numbers():
    says = samvaad_session._says_amount
    assert says("कुल 6380 रुपये", 6380) and says("total ₹6,380.", 6380) and says("1 190 rupees", 1190)
    assert not says("total 16380", 6380) and not says("2,400 rupees", 6380) and not says("₹7200", 720)



# ---------------------------------------------------------- saying less --


def test_the_read_back_says_the_start_of_a_long_address_and_no_digits_for_the_callers_own_number(api):
    tool(api, "add_to_cart", item_name="paneer makhani")  # a main dish: its drink suggestion is the call's one offer
    address = "1902 A Wing, Modi Space, Ganges, opposite Bhagwati Hospital, Borivali West"
    tool(api, "set_order_details", order_type="delivery", address=address)  # the name-and-number question
    said = tool(api, "set_order_details", order_type="delivery", customer_name="Priya")["say"]  # "Priya, isi pe"
    assert "1902 A Wing Modi पर डिलीवरी" in said and "Bhagwati" not in said
    assert "व्हाट्सएप पर इसी नंबर पर आएगा" in said and "9 8 7" not in said  # asked once already


def test_a_dessert_is_offered_only_when_nothing_else_was(api):
    tool(api, "add_to_cart", item_name="Sweet Lassi")  # a drink on its own: no drink-and-side suggestion
    tool(api, "add_to_cart", item_name="Paneer Butter Masala")
    samvaad_session.sessions.get("call-1").sales.offered.discard("first_order")
    held = details(api, order_type="pickup")
    assert "dessert" in held["result"] and "Gulab Jamun" in held["result"]


def test_alternatives_for_a_missing_dish_are_two_at_most_and_veg_for_a_veg_dish(api):
    said = tool(api, "add_to_cart", item_name="Garlic Naan")["say"]
    assert "Garlic Naan हमारे मेन्यू में नहीं है" in said
    offered = said.split("इसकी जगह ")[1].split(" ले सकते")[0].split(", ") if "इसकी जगह" in said else []
    assert len(offered) <= 2 and all(name in {"Paneer Butter Masala", "Butter Naan", "Sweet Lassi", "Gulab Jamun",
                                              "Margherita Pizza"} for name in offered)


# ------------------------------------------------------------------ language --


def test_one_english_tool_call_does_not_switch_a_hindi_call(api):
    tool(api, "add_to_cart", item_name="Butter Naan")
    tool(api, "add_to_cart", item_name="Sweet Lassi", language="English")
    said = tool(api, "set_order_details", order_type="pickup", language="Hindi")["say"]
    assert "नाम" in said  # still Hindi: one "English" in the middle was noise


def test_a_guest_who_really_switches_gets_english(api):
    tool(api, "add_to_cart", item_name="Butter Naan", language="English")
    said = tool(api, "set_order_details", order_type="pickup", language="English")["say"]
    assert said.startswith("May I have your name")


def test_the_whatsapp_bill_is_in_english_after_a_hindi_call(api, fake):
    order_to_read_back(api)
    tool(api, "checkout")
    bill = next(m for m in fake.tables["message_outbox"] if m["kind"] == "customer_bill")["body"]["text"]
    assert "Order " in bill and "Total: " in bill and "Deliver to: 12 MG Road" in bill
    assert not any("ऀ" <= ch <= "ॿ" for ch in bill)  # no Devanagari at all


def test_an_unchanged_order_is_not_read_back_twice(api):
    first = order_to_read_back(api)
    again = tool(api, "read_back_order")  # Samvaad's LLM calls it again on its own
    assert "say" not in again and "do not read it again" in again["result"]
    assert first["say"] in again["result"]  # there to repeat, only if the guest asked
    assert tool(api, "checkout")["result"].startswith("Order placed")


def test_a_changed_order_is_read_back_again(api):
    order_to_read_back(api)
    tool(api, "add_to_cart", item_name="Sweet Lassi")
    assert "Sweet Lassi" in tool(api, "read_back_order")["say"]


def test_alternatives_are_only_the_same_kind_of_dish():
    assert samvaad_session._same_kind("Veg Kolhapuri", "Paneer Kolhapuri")
    assert samvaad_session._same_kind("shahi paneer", "Paneer Makhani")
    assert not samvaad_session._same_kind("bhindi masala", "Veg Pink Pasta")
    assert not samvaad_session._same_kind("veg sabji", "Veg Club Sandwich")  # "veg" alone makes nothing alike


def test_the_owner_message_has_the_order_number_mobile_and_an_english_address():
    text = messages.owner_order({
        "id": "o1", "payment_ref": "M5P6F3", "items": [{"name": "Veg Dum Biryani", "quantity": 1, "price": 1155}],
        "total": 1155, "order_type": "delivery", "address": "1902 ए विंग, बोरीवली", "customer_name": "प्रिया",
        "customer_phone": "+919876543210",
    })["text"]
    assert text.startswith("Order M5P6F3\n") and "New phone" not in text
    assert "Mobile: +91 98765 43210" in text and "Name: Priya" in text
    assert not any("\u0900" <= ch <= "\u097f" for ch in text)


# ------------------------------------------------------------ a dropped call --


def start(api, interaction_id, **body):
    body = {"interaction_id": interaction_id, "store_slug": "spice-route", "caller": f"+{CUSTOMER}", **body}
    return api.post("/samvaad/start", json=body, headers=AUTH).json()


def test_a_call_that_dropped_gets_its_cart_back_on_the_next_call(api, fake):
    start(api, "call-1")
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 2}, {"name": "Butter Naan", "quantity": 4}])
    tool(api, "set_order_details", order_type="delivery", address="12 MG Road")
    # The line drops. The same number calls again.
    body = start(api, "call-2")
    assert body["resumed_order"] == "2 Paneer Butter Masala, 4 Butter Naan"
    assert body["cart_summary"] == "2 x Paneer Butter Masala, 4 x Butter Naan"
    old = next(c for c in fake.tables["carts"] if c["interaction_id"] == "call-1")
    assert old["status"] == "recovered"  # won back, not counted as a dropped cart
    # The address came back too, so the next step is the name-and-number question, then one read-back.
    asked = tool(api, "set_order_details", interaction_id="call-2", order_type="delivery")
    assert "नाम" in asked["say"]


def test_a_new_caller_or_an_old_cart_starts_empty(api, fake):
    assert start(api, "call-1")["resumed_order"] == "none"
    tool(api, "add_to_cart", item_name="Butter Naan")
    next(c for c in fake.tables["carts"] if c["interaction_id"] == "call-1")["last_activity_at"] = "2020-01-01T00:00:00+00:00"
    assert start(api, "call-2")["resumed_order"] == "none"  # more than an hour ago
    assert start(api, "call-3", caller="+919111111111")["resumed_order"] == "none"  # someone else


def test_an_ordered_cart_is_not_brought_back(api):
    start(api, "call-1")
    order_to_read_back(api)
    tool(api, "checkout")
    assert start(api, "call-2")["resumed_order"] == "none"


def test_same_kind_alternatives_put_the_owners_picks_first(api, monkeypatch):
    tool(api, "view_cart")  # opens the call
    session = samvaad_session.sessions.get("call-1")
    paneer = [{"name": "Paneer Tikka Masala", "veg": True}, {"name": "Paneer Butter Masala", "veg": True},
              {"name": "Kadai Paneer", "veg": True, "featured": ["bestseller"]}, {"name": "Veg Pink Pasta", "veg": True}]
    monkeypatch.setattr(session.menu, "search", lambda name, k=8: paneer)
    session._not_on_menu("Couldn't find 'Shahi Paneer' on the menu.", {})
    assert "इसकी जगह Kadai Paneer, Paneer Tikka Masala ले सकते हैं" in session.order.spoken  # bestseller first, no pasta
    for dish in paneer:
        dish.pop("featured", None)  # the owner turned Bestsellers off: nothing is featured, the search's own order
    session._not_on_menu("Couldn't find 'Shahi Paneer' on the menu.", {})
    assert "इसकी जगह Paneer Tikka Masala, Paneer Butter Masala ले सकते हैं" in session.order.spoken


# ------------------------------------------------------------ the number mapper --
# One agent, many restaurants: the number the guest dialled says which restaurant the call is for.


@pytest.fixture
def two_restaurants(store, fake):
    repository.save_store({
        "id": "store-2", "slug": "fusion", "name": "The Fusion Kitchen", "business_type": "restaurant",
        "agent_name": "Aria", "phone_number": None, "owner_whatsapp": OWNER, "restaurant_slug": "fusion",
    })
    repository.assign_number("fusion", "+917965861786", "main line")
    return fake


def dial(api, **body):
    return api.post("/samvaad/start", json={"interaction_id": body.pop("interaction_id", "m1"), **body}, headers=AUTH).json()


def test_each_dialled_number_reaches_its_own_restaurant(api, two_restaurants):
    assert dial(api, interaction_id="a", called_number="+918000000000")["store_name"] == "Spice Route"
    fusion = dial(api, interaction_id="b", called_number="07965861786")  # the way a landline may arrive
    assert fusion["store_name"] == "The Fusion Kitchen" and fusion["agent_name"] == "Aria" and fusion["line_ready"] is True
    assert two_restaurants.tables["phone_calls"][-1]["called_number"] == "+917965861786"


def test_the_dialled_number_beats_a_slug_left_in_the_agents_variables(api, two_restaurants):
    body = dial(api, called_number="+91 79658 61786", store_slug="spice-route")
    assert body["store_slug"] == "fusion"


def test_a_test_chat_without_a_dialled_number_uses_the_slug(api, two_restaurants):
    assert dial(api, store_slug="fusion")["store_name"] == "The Fusion Kitchen"


def test_a_number_nobody_owns_never_borrows_another_restaurant(api, two_restaurants, monkeypatch):
    monkeypatch.setenv("SAMVAAD_DEFAULT_STORE", "spice-route")
    body = dial(api, called_number="+919999999999")
    assert body["line_ready"] is False and body["store_slug"] == "" and "say" in body
    assert "phone_calls" not in two_restaurants.tables or not any(
        c.get("called_number") == "+919999999999" for c in two_restaurants.tables["phone_calls"])


def test_a_restaurant_can_have_several_numbers_and_a_number_can_move(api, two_restaurants):
    repository.assign_number("fusion", "+912228000000", "old number, forwarded")
    assert dial(api, interaction_id="x", called_number="02228000000")["store_slug"] == "fusion"
    assert repository.numbers_of_store("store-2") == ["+917965861786", "+912228000000"]
    repository.assign_number("spice-route", "+917965861786")  # moved: it reaches one restaurant only
    assert dial(api, interaction_id="y", called_number="7965861786")["store_slug"] == "spice-route"
    repository.unassign_number("+912228000000")
    assert dial(api, interaction_id="z", called_number="02228000000")["line_ready"] is False


def test_later_tool_calls_stay_with_the_restaurant_the_call_started_with(api, two_restaurants):
    dial(api, interaction_id="t1", called_number="7965861786")
    body = api.post("/samvaad/tools/view_cart", json={"interaction_id": "t1", "store_slug": "spice-route"}, headers=AUTH)
    assert body.status_code == 200
    assert samvaad_session.sessions.get("t1").store["slug"] == "fusion"


def test_a_name_heard_in_hindi_is_saved_in_english_letters(api):
    tool(api, "add_to_cart", items=[{"name": "paneer makhani", "quantity": 1}])
    tool(api, "set_order_details", order_type="pickup", customer_name="ऋत्विक दोषी")
    assert samvaad_session.sessions.get("call-1").order.customer_name == "Ritvik Doshi"


def test_the_board_shows_old_hindi_names_and_addresses_in_english():
    from app.owner_board import _address, _who
    assert _who({"name": "मानव"}, "+919000000002", True)["name"] == "Manav"
    assert _address({"address": "बोरीवली"}).isascii()
    assert _address({"address": "1902, A Wing, Borivali"}) == "1902, A Wing, Borivali"

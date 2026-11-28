"""A restaurant's own rules and WhatsApp numbers: the owner edits them, every call and every message uses them."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import agent_config, db, owner_api
from app.phone import outbox, repository, whatsapp
from tests.fake_supabase import FakeSupabase

OWNER_NUMBER = "919000000001"


@pytest.fixture
def fake(monkeypatch):
    client = FakeSupabase()
    monkeypatch.setattr(db, "get_client", lambda: client)
    monkeypatch.setattr(outbox, "_senders", {})
    client.tables.update(
        restaurants=[{"id": "r1", "slug": "tfk", "name": "The Fusion Kitchen", "agent_rules": ""}],
        restaurant_members=[
            {"user_id": "owner-1", "restaurant_id": "r1", "role": "owner"},
            {"user_id": "staff-1", "restaurant_id": "r1", "role": "staff"},
        ],
        phone_stores=[{"id": "s1", "slug": "tfk", "restaurant_slug": "tfk", "owner_whatsapp": OWNER_NUMBER,
                       "phone_number": "+918000000000", "agent_name": "Kabir", "created_at": "1"}],
        orders=[{"id": "o1", "store_id": "s1"}],
        phone_calls=[{"id": "c1", "store_id": "s1", "room": "samvaad:1"}],
    )
    return client


@pytest.fixture
def api(fake):
    app = FastAPI()
    app.include_router(owner_api.router)
    user = {"id": "owner-1"}
    app.dependency_overrides[owner_api.current_user_id] = lambda: user["id"]
    client = TestClient(app)
    client.user = user
    return client


# ----------------------------------------------------------------- the rule book --


def test_rules_are_tidied_and_capped():
    assert agent_config.clean_rules("  Pasta: penne or spaghetti.  \r\n\r\n\r\n\r\nNo delivery after 11.\x07 ") == (
        "Pasta: penne or spaghetti.\n\nNo delivery after 11."
    )
    with pytest.raises(agent_config.ConfigError):
        agent_config.clean_rules("x" * (agent_config.RULES_LIMIT + 1))


def test_a_restaurant_without_rules_gives_the_call_none():
    assert agent_config.rules_for_call({"agent_rules": "  "}) == "none"
    assert agent_config.rules_for_call(None) == "none"
    assert agent_config.rules_for_call({"agent_rules": "Desserts are eggless."}) == "Desserts are eggless."


def test_the_owner_sees_and_edits_the_rule_book(api, fake):
    view = api.get("/owner/restaurants/r1/agent").json()
    assert view["rules"] == "" and view["rules_limit"] == 2000
    assert view["calls"]["alert_whatsapp"] == "+91 90000 00001" and view["whatsapp_sender"]["own_number"] is False

    saved = api.put("/owner/restaurants/r1/agent", json={"rules": "Ask penne or spaghetti for every pasta."}).json()
    assert saved["rules"] == "Ask penne or spaghetti for every pasta." and saved["rules_updated_at"]
    assert fake.tables["restaurants"][0]["agent_rules"] == "Ask penne or spaghetti for every pasta."


def test_a_rule_book_that_is_too_long_is_refused(api):
    response = api.put("/owner/restaurants/r1/agent", json={"rules": "x" * 2001})
    assert response.status_code == 422 and "2000" in response.json()["detail"]


def test_staff_cannot_see_the_settings_or_the_owners_number(api):
    api.user["id"] = "staff-1"
    assert api.get("/owner/restaurants/r1/agent").status_code == 404
    assert api.put("/owner/restaurants/r1/agent", json={"rules": "hi"}).status_code == 404


# ------------------------------------------------------------ where alerts go --


def test_the_owner_can_send_order_alerts_to_another_number(api, fake):
    saved = api.put("/owner/restaurants/r1/agent", json={"alert_whatsapp": "98765 43210"}).json()
    assert saved["calls"]["alert_whatsapp"] == "+91 98765 43210"
    assert fake.tables["phone_stores"][0]["owner_whatsapp"] == "919876543210"
    assert fake.tables["restaurants"][0]["agent_rules"] == ""  # untouched: only what was sent changes


def test_a_number_without_whatsapp_is_refused(api, fake):
    response = api.put("/owner/restaurants/r1/agent", json={"alert_whatsapp": "022 2345 6789"})
    assert response.status_code == 422
    assert fake.tables["phone_stores"][0]["owner_whatsapp"] == OWNER_NUMBER


def test_the_first_alert_number_switches_phone_ordering_on(api, fake):
    fake.tables["phone_stores"] = []
    assert api.get("/owner/restaurants/r1/agent").json()["calls"] is None
    saved = api.put("/owner/restaurants/r1/agent", json={"alert_whatsapp": "9876543210"}).json()
    store = fake.tables["phone_stores"][0]
    assert store["restaurant_slug"] == "tfk" and store["owner_whatsapp"] == "919876543210" and store["business_type"] == "restaurant"
    assert saved["calls"]["calls_number"] is None and saved["calls"]["calls_numbers"] == []  # until Sarthi links one


def test_upi_needs_somewhere_for_alerts_first(api, fake):
    fake.tables["phone_stores"] = []
    response = api.put("/owner/restaurants/r1/agent", json={"upi_id": "tfk@okhdfcbank"})
    assert response.status_code == 422 and "First save" in response.json()["detail"]


def test_the_owner_sets_and_clears_their_upi_id(api, fake):
    saved = api.put("/owner/restaurants/r1/agent", json={"upi_id": " tfk@okhdfcbank ", "upi_payee_name": ""}).json()
    assert saved["calls"]["upi_id"] == "tfk@okhdfcbank" and saved["calls"]["upi_payee_name"] == "The Fusion Kitchen"
    assert api.put("/owner/restaurants/r1/agent", json={"upi_id": "not a upi"}).status_code == 422
    cleared = api.put("/owner/restaurants/r1/agent", json={"upi_id": ""}).json()
    assert cleared["calls"]["upi_id"] is None  # bills then say pay on delivery or at pickup


# ------------------------------------------------------- which number sends --


def test_a_restaurant_with_its_own_number_sends_from_it(fake, monkeypatch):
    fake.tables["store_channels"] = [{"id": "ch1", "restaurant_id": "r1", "phone_number_id": "555", "display_number": "+917000000000",
                                      "token_env": "WHATSAPP_TOKEN_TFK", "enabled": True, "created_at": "1"}]
    monkeypatch.setenv("WHATSAPP_TOKEN_TFK", "tfk-token")
    sender = outbox.sender_for({"id": "m1", "order_id": "o1", "call_id": None})
    assert sender == whatsapp.Sender("555", "tfk-token")
    assert outbox.sender_for({"id": "m2", "order_id": None, "call_id": "c1"}) == sender  # a callback alert too
    assert agent_config.view(fake.tables["restaurants"][0])["whatsapp_sender"] == {"own_number": True, "number": "+917000000000"}


def test_without_its_own_number_or_its_token_the_shared_number_sends(fake, monkeypatch):
    assert outbox.sender_for({"id": "m1", "order_id": "o1", "call_id": None}) is None
    monkeypatch.setattr(outbox, "_senders", {})
    fake.tables["store_channels"] = [{"id": "ch1", "restaurant_id": "r1", "phone_number_id": "555", "token_env": "MISSING_TOKEN",
                                      "enabled": True, "created_at": "1"}]
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    assert outbox.sender_for({"id": "m1", "order_id": "o1", "call_id": None}) is None


def test_the_sender_reaches_whatsapps_api(monkeypatch):
    seen = {}

    class Reply:
        is_success = True

        def json(self):
            return {"messages": [{"id": "wamid.1"}]}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, auth=headers["Authorization"])
        return Reply()

    monkeypatch.setattr(whatsapp.httpx, "post", fake_post)
    whatsapp.send_text("919000000002", "hi", whatsapp.Sender("555", "tfk-token"))
    assert seen["url"].endswith("/555/messages") and seen["auth"] == "Bearer tfk-token"


def test_a_message_with_no_order_or_call_uses_the_shared_number(fake):
    assert repository.store_id_of(None, None) is None
    assert outbox.sender_for({"id": "m1", "order_id": None, "call_id": None}) is None


def test_the_owner_sees_every_number_that_reaches_them(api, fake):
    repository.assign_number("tfk", "+912228000000", "old number, forwarded")
    calls = api.get("/owner/restaurants/r1/agent").json()["calls"]
    assert calls["calls_numbers"] == ["+918000000000", "+912228000000"] and calls["calls_number"] == "+918000000000"

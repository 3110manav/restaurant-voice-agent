"""The table QR pilot: rounds sent to the kitchen, the bill, the turn tracker, the owner's views,
and the guest endpoints, with Supabase faked out."""
import copy
import importlib
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import db
from app.table import service
from app.table.state import TableState
from app.table.suggest import next_suggestion
from tests.fake_supabase import FakeSupabase

RESTAURANT = {"id": "r1", "slug": "dhaba", "name": "Sarson Da Khet", "status": "live", "gst_rate": 5,
              "upi_id": "sarson@okbank", "upi_payee_name": "Sarson Da Khet", "google_review_url": "https://g.page/r/x"}


def line(i, name, price, qty, variant=None):
    out = {"id": i, "name": name, "price": price, "quantity": qty}
    if variant:
        out["variant"] = variant
    return out


def dish(i, name, category, price, veg=True, order=0):
    return {"id": i, "name": name, "category": category, "price": price, "veg": veg, "spice_level": "mild",
            "tags": [], "is_available": True, "sort_order": order, "description": ""}


MENU = [
    dish("m1", "Dal Makhani", "Mains - Veg", 220),
    dish("b1", "Butter Naan", "Breads", 60),
    dish("d1", "Sweet Lassi", "Beverages", 110),
    dish("s1", "Gajar Halwa", "Desserts", 160),
]
BY_ID = {d["id"]: d for d in MENU}


@pytest.fixture
def fake_db(monkeypatch):
    client = FakeSupabase()
    monkeypatch.setattr(db, "get_client", lambda: client)
    return client


# --------------------------------------------------------------- cart lines --


def test_only_what_is_new_goes_to_the_kitchen():
    placed = [line("m1", "Dal", 220, 1), line("b1", "Naan", 60, 2)]
    cart = [line("m1", "Dal", 220, 1), line("b1", "Naan", 60, 3), line("d1", "Lassi", 110, 1)]
    assert service.unplaced(cart, placed) == [line("b1", "Naan", 60, 1), line("d1", "Lassi", 110, 1)]
    assert service.unplaced(placed, placed) == []
    assert service.unplaced([], placed) == []  # removing after sending doesn't un-send


def test_sizes_are_separate_lines():
    placed = [line("p1", "Pizza", 179, 1, "Regular")]
    cart = [line("p1", "Pizza", 179, 1, "Regular"), line("p1", "Pizza", 499, 1, "Large")]
    assert service.unplaced(cart, placed) == [line("p1", "Pizza", 499, 1, "Large")]


def test_bill_adds_gst_and_rounds_each_share_up():
    bill = service.bill([line("m1", "Dal", 220, 1), line("b1", "Naan", 60, 2), line("t1", "Tikka", 320, 1)], 5, 2)
    assert (bill["subtotal"], bill["gst"], bill["total"], bill["share"]) == (660, 33, 693, 347)
    assert service.bill([], 5, 0)["people"] == 1


# ------------------------------------------------------------- turn tracker --


def at(minutes):
    return (datetime(2026, 11, 6, 13, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes)).isoformat()


def test_tonight_shows_open_tables_and_average_waits():
    rows = [
        {"id": "a", "table_no": "3", "seated_at": at(0), "first_order_at": at(3), "food_served_at": at(22),
         "bill_requested_at": at(48), "paid_at": at(52), "status": "closed", "ordered": []},
        {"id": "b", "table_no": "10", "seated_at": at(20), "first_order_at": at(24), "status": "open",
         "ordered": [line("m1", "Dal", 220, 2)]},
        {"id": "c", "table_no": "2", "seated_at": at(50), "status": "open", "ordered": []},
    ]
    view = service.tonight(rows, datetime.fromisoformat(at(55)))
    assert [t["table_no"] for t in view["tables"]] == ["2", "10"]  # numeric order, the paid table gone
    assert [t["state"] for t in view["tables"]] == ["ordering", "long"]  # 31 min since ordering
    assert view["tables"][1]["amount"] == 440
    assert view["averages"]["turn"] == 52 and view["averages"]["ordered_to_food"] == 19


def test_month_bounds_are_indian_months():
    start, end, label = service.month_bounds("2026-10", datetime.now(timezone.utc))
    assert label == "2026-10"
    assert start.isoformat() == "2026-09-30T18:30:00+00:00" and end.isoformat() == "2026-10-31T18:30:00+00:00"
    assert service.month_bounds("nonsense", datetime(2026, 12, 31, 20, tzinfo=timezone.utc))[2] == "2027-01"


def test_report_counts_the_month():
    start, end, _ = service.month_bounds("2026-11", datetime.now(timezone.utc))
    rows = [
        {"seated_at": at(0), "first_order_at": at(3), "paid_at": at(53), "upsell_total": 170, "rating": 5},
        {"seated_at": at(0), "first_order_at": at(5), "paid_at": at(45), "upsell_total": 60, "rating": 2,
         "feedback": "Naan was cold"},
        {"seated_at": at(0)},
    ]
    customers = [{"first_seen_at": at(10), "offers_opt_in": True}, {"first_seen_at": "2026-01-01T00:00:00+00:00"}]
    out = service.report(rows, 4, customers, start, end, 61)
    assert out["tables_served"] == 2 and out["table_orders"] == 4 and out["upsell_total"] == 230
    assert out["averages"]["turn"] == 49 and out["turn_saved_minutes"] == 12
    assert (out["new_customers"], out["new_customers_opted_in"]) == (1, 1)
    assert (out["ratings"], out["average_rating"], out["complaints"]) == (2, 3.5, 1)


# --------------------------------------------------------------- table state --


def test_a_table_session_is_saved_as_it_goes(fake_db):
    state = TableState.open(RESTAURANT, "guest-1", "3")
    [row] = fake_db.tables["table_sessions"]
    assert row["table_no"] == "3" and row["seated_at"]
    state.suggestion_added("d1")
    state.record_round([line("m1", "Dal", 220, 1), line("d1", "Lassi", 110, 1)])
    state.record_round([line("m1", "Dal", 220, 1)])
    assert row["rounds"] == 2 and row["upsell_total"] == 110 and row["first_order_at"]
    assert row["ordered"] == [line("m1", "Dal", 220, 2), line("d1", "Lassi", 110, 1)]
    assert state.bill()["total"] == 578  # 550 + 5% GST


def test_staff_and_guest_taps_keep_the_first_time(fake_db):
    state = TableState.open(RESTAURANT, "guest-1", "3")
    row = fake_db.tables["table_sessions"][0]
    row["food_served_at"] = "2026-11-06T13:20:00+00:00"  # staff tapped Food served first
    state.food_served()
    assert row["food_served_at"] == "2026-11-06T13:20:00+00:00"


def test_a_restarted_server_reads_the_session_back(fake_db):
    TableState.open(RESTAURANT, "guest-1", "3").record_round([line("m1", "Dal", 220, 1)])
    again = TableState.open(RESTAURANT, "guest-1", None)
    assert again.rounds == 1 and again.table_no == "3" and len(fake_db.tables["table_sessions"]) == 1


def test_paying_saves_the_customer_once_per_visit(fake_db):
    state = TableState.open(RESTAURANT, "guest-1", "3")
    state.pay("upi", "Harpreet", "9812345678", True)
    TableState.open(RESTAURANT, "guest-2", "4").pay("counter", None, "9812345678", False)
    [customer] = fake_db.tables["customers"]
    assert customer["visits"] == 2 and customer["name"] == "Harpreet" and customer["offers_opt_in"] is False


def test_a_database_outage_never_blocks_the_guest(fake_db):
    fake_db.failing = True
    state = TableState.open(RESTAURANT, "guest-1", "3")
    assert state.record_round([line("m1", "Dal", 220, 1)]) == 1
    state.food_served()
    state.pay("upi", None, "9812345678", True)


def test_suggestions_offer_a_drink_then_a_dessert_and_stop_at_two():
    state = TableState(RESTAURANT, "guest-1", "3")
    cart = [line("m1", "Dal Makhani", 220, 1)]
    first = next_suggestion(state, MENU, BY_ID.get, cart)
    assert first["id"] == "d1" and first["role"] == "drink"
    state.suggestion_dismissed("d1")
    assert next_suggestion(state, MENU, BY_ID.get, cart)["id"] == "b1"
    state.suggestion_dismissed("b1")
    assert next_suggestion(state, MENU, BY_ID.get, cart) is None  # two shown already


def test_dessert_comes_after_the_food_is_ordered():
    state = TableState(RESTAURANT, "guest-1", "3")
    state.ordered, state.rounds = [line("m1", "Dal Makhani", 220, 1), line("d1", "Sweet Lassi", 110, 1),
                                   line("b1", "Butter Naan", 60, 1)], 1
    assert next_suggestion(state, MENU, BY_ID.get, [])["id"] == "s1"


# ------------------------------------------------------------ guest endpoints --


class StubAgent:
    persona = "waiter"

    def __init__(self, key):
        self.session_id, self.cart, self._placed_cart, self.on_round = key, [], [], None
        self.service_log = []

    def set_language(self, _):
        pass

    def mark_order_placed(self):
        lines = service.unplaced(self.cart, self._placed_cart)
        self._placed_cart = copy.deepcopy(self.cart)
        if self.on_round and lines:
            self.on_round(lines)

    def sync_placed(self, placed):
        lines = service.unplaced(placed, self._placed_cart)
        self._placed_cart = copy.deepcopy(placed)
        if self.on_round and lines:
            self.on_round(lines)


class StubLiveMenu:
    def __init__(self, _slug):
        self.menu = MENU

    def get(self, i):
        return BY_ID.get(i)


class StubStore:
    def __init__(self, data_path=None, collection_name="restaurant_menu"):
        self.menu = []


@pytest.fixture
def api(monkeypatch, fake_db):
    from app.rag import menu_store

    monkeypatch.setattr(menu_store, "MenuStore", StubStore)
    monkeypatch.delitem(sys.modules, "app.main", raising=False)
    main = importlib.import_module("app.main")
    agents = {}
    monkeypatch.setattr(main, "_session", lambda sid, persona, restaurant=None, table_no=None:
                        agents.setdefault(f"{restaurant}:{sid}:waiter", StubAgent(f"{restaurant}:{sid}:waiter")))
    monkeypatch.setattr(main, "live_restaurant", lambda slug: RESTAURANT)
    monkeypatch.setattr(main, "LiveMenu", StubLiveMenu)
    sent = []
    monkeypatch.setattr(main.erp, "record_order", lambda *a, **k: sent.append((a, k)) or True)
    monkeypatch.setattr(main.erp, "record_request", lambda *a, **k: sent.append(("request", a, k)))
    yield TestClient(main.app), main, sent
    sys.modules.pop("app.main", None)


TABLE = {"session_id": "g1", "restaurant": "dhaba", "table_no": "3"}


def add(http, item_id, **extra):
    return http.post("/cart/add", json={**TABLE, "item_id": item_id, **extra})


def test_send_places_each_round_once(api):
    http, _, sent = api
    assert http.post("/table/open", json=TABLE).json()["rounds"] == 0
    add(http, "m1")
    first = http.post("/table/send", json=TABLE).json()
    assert first["round"] == 1 and [l["id"] for l in first["lines"]] == ["m1"]
    assert http.post("/table/send", json=TABLE).status_code == 409  # nothing new
    add(http, "b1")
    second = http.post("/table/send", json=TABLE).json()
    assert [l["id"] for l in second["lines"]] == ["b1"]
    assert [a[2] for a, _ in sent] == [[{"id": "m1", "name": "Dal Makhani", "price": 220, "quantity": 1}],
                                       [{"id": "b1", "name": "Butter Naan", "price": 60, "quantity": 1}]]
    assert sent[0][1] == {"restaurant_id": "r1", "table_no": "3"}


def test_a_failed_save_tells_the_guest_and_sends_nothing(api, monkeypatch):
    http, main, _ = api
    monkeypatch.setattr(main.erp, "record_order", lambda *a, **k: False)
    add(http, "m1")
    assert http.post("/table/send", json=TABLE).status_code == 503
    assert http.post("/table/state", json=TABLE).status_code == 405
    state = http.get("/table/state", params=TABLE).json()
    assert state["rounds"] == 0 and [l["id"] for l in state["unsent"]] == ["m1"]


def test_bill_split_and_upi_link(api):
    http, _, _ = api
    assert http.post("/table/bill", json={**TABLE, "people": 2}).status_code == 409  # nothing ordered yet
    add(http, "m1")
    add(http, "b1")
    http.post("/table/send", json=TABLE)
    bill = http.post("/table/bill", json={**TABLE, "people": 2}).json()
    assert (bill["total"], bill["share"]) == (294, 147)
    assert bill["upi_link"].startswith("upi://pay?pa=sarson@okbank") and "am=147.00" in bill["upi_link"]


def test_a_voice_call_order_counts_without_a_second_ticket(api):
    http, _, sent = api
    http.post("/table/open", json=TABLE)
    voice_cart = [{"id": "m1", "name": "Dal Makhani", "price": 220, "quantity": 1}]
    http.post("/cart/sync", json={**TABLE, "persona": "waiter", "cart": voice_cart, "placed_cart": voice_cart})
    assert http.get("/table/state", params=TABLE).json()["rounds"] == 1
    assert http.post("/table/send", json=TABLE).status_code == 409 and sent == []


def test_pay_checks_the_number_and_feedback_reaches_the_owner(api, fake_db):
    http, _, sent = api
    http.post("/table/open", json=TABLE)
    assert http.post("/table/pay", json={**TABLE, "method": "cash"}).status_code == 422
    assert http.post("/table/pay", json={**TABLE, "method": "upi", "phone": "12345"}).status_code == 422
    ok = http.post("/table/pay", json={**TABLE, "method": "upi", "phone": "+91 98123 45678", "offers_opt_in": True})
    assert ok.status_code == 200 and fake_db.tables["customers"][0]["phone"] == "9812345678"
    out = http.post("/table/feedback", json={**TABLE, "rating": 2, "message": "Naan was cold"}).json()
    assert out["review_url"] == "https://g.page/r/x"  # everyone is offered the Google link
    assert sent[-1][0] == "request" and sent[-1][1][2] == "complaint"


def test_suggestion_added_from_the_card_counts_as_upsell(api, fake_db):
    http, _, _ = api
    add(http, "m1")
    suggestion = http.get("/table/suggestion", params=TABLE).json()["suggestion"]
    assert suggestion["id"] == "d1"
    add(http, "d1", suggested=True)
    http.post("/table/send", json=TABLE)
    assert fake_db.tables["table_sessions"][0]["upsell_total"] == 110


def test_a_page_without_a_table_cannot_order_from_one(api):
    http, _, _ = api
    assert http.post("/table/open", json={"session_id": "g2", "restaurant": "dhaba"}).status_code == 400

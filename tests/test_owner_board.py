"""The owner's Calls & Orders board: joined, and with no full phone number or pay token in it."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db, owner_api, owner_board
from app.menu import repository
from tests.fake_supabase import FakeSupabase

RESTAURANT = {"id": "r1", "slug": "demo", "name": "Demo"}
PHONE = "+919876542828"


@pytest.fixture
def fake(monkeypatch):
    client = FakeSupabase()
    monkeypatch.setattr(db, "get_client", lambda: client)
    client.tables.update(
        customers=[{"id": "c1", "restaurant_id": "r1", "phone": PHONE, "name": "Priya Shah"}],
        phone_calls=[{"id": "call1", "room": "samvaad:x", "outcome": "ordered", "started_at": "2026-11-21T10:00:00+00:00", "ended_at": None}],
        phone_stores=[{"id": "s1", "restaurant_slug": "demo"}],
        orders=[
            {"id": "o1", "restaurant_id": "r1", "created_at": "2026-11-21T10:05:00+00:00", "status": "placed", "total": 560,
             "items": [{"name": "Chicken Biryani", "quantity": 1, "price": 320, "note": "without beans"}],
             "customer_id": "c1", "customer_phone": PHONE, "customer_name": "Priya Shah", "phone_verified": True,
             "order_type": "delivery", "address": "12 MG Road", "call_id": "call1", "pay_token": "SECRET", "special_requests": "deliver after 8"},
            {"id": "o2", "restaurant_id": "r1", "created_at": "2026-11-21T09:00:00+00:00", "status": "placed", "total": 90,
             "items": [], "table_no": "5", "customer_phone": None},
        ],
        requests=[{"id": "q1", "restaurant_id": "r1", "order_id": "o1", "type": "callback", "details": "wants a call",
                   "status": "open", "created_at": "2026-11-21T10:06:00+00:00"}],
        carts=[
            {"id": "k1", "restaurant_id": "r1", "status": "abandoned", "opened_at": "t", "last_activity_at": "2026-11-21T11:00:00+00:00",
             "items": [{"name": "Butter Naan", "quantity": 2}], "total": 120, "customer_id": None, "customer_phone": "+919000000001"},
            {"id": "k2", "restaurant_id": "r1", "status": "expired", "opened_at": "t", "last_activity_at": "2026-11-20T11:00:00+00:00",
             "items": [], "total": 0, "closed_reason": "empty"},
        ],
        call_funnel=[{"store_id": "s1", "day": "2026-11-21", "calls": 3, "ordered": 1}],
    )
    return client


def test_a_phone_number_is_masked_to_its_last_four_digits():
    assert owner_board.mask_phone("+919876542828") == "+91 ••••• 2828"
    assert owner_board.mask_phone("919876542828") == "+91 ••••• 2828"
    assert owner_board.mask_phone("2828") == "••••• 2828"
    assert owner_board.mask_phone(None) is None


def test_the_board_joins_each_order_with_its_customer_requests_and_call(fake):
    board = owner_board.build(RESTAURANT)
    order = next(o for o in board["orders"] if o["id"] == "o1")
    assert order["customer"] == {"name": "Priya Shah", "phone": "+91 ••••• 2828", "verified": True, "orders": 1}
    assert order["fulfilment"] == "delivery" and order["address"] == "12 MG Road" and order["channel"] == "call"
    assert order["items"][0]["note"] == "without beans" and order["special_requests"] == "deliver after 8"
    assert order["requests"][0]["details"] == "wants a call"
    assert order["call"]["outcome"] == "ordered"
    assert next(o for o in board["orders"] if o["id"] == "o2")["channel"] == "table"


def test_no_full_number_and_no_pay_token_is_ever_returned(fake):
    text = str(owner_board.build(RESTAURANT))
    assert "9876542828" not in text and "SECRET" not in text and "919000000001" not in text


def test_dropped_carts_show_what_was_left_and_skip_empty_ones(fake):
    dropped = owner_board.build(RESTAURANT)["dropped_carts"]
    assert [c["id"] for c in dropped] == ["k1"]
    assert dropped[0]["items"][0]["name"] == "Butter Naan" and dropped[0]["customer"]["phone"] == "+91 ••••• 0001"


def test_the_funnel_comes_from_the_stores_of_this_restaurant(fake):
    assert owner_board.build(RESTAURANT)["funnel"] == [{"store_id": "s1", "day": "2026-11-21", "calls": 3, "ordered": 1}]


def test_the_endpoint_needs_a_member_and_the_orders_list_hides_numbers(fake, monkeypatch):
    class Auth:
        def get_user(self, token):
            if token != "owner":
                raise Exception("invalid JWT")
            return SimpleNamespace(user=SimpleNamespace(id="u1"))

    monkeypatch.setattr(owner_api.db, "get_client", lambda: SimpleNamespace(auth=Auth(), table=fake.table, rpc=fake.rpc))
    owner_api._tokens.clear()
    monkeypatch.setattr(repository, "user_role", lambda uid, rid: "owner" if rid == "r1" else None)
    monkeypatch.setattr(repository, "get_restaurant", lambda rid: RESTAURANT if rid == "r1" else None)
    monkeypatch.setattr(repository, "list_orders", lambda rid: fake.tables["orders"])
    app = FastAPI()
    app.include_router(owner_api.router)
    api = TestClient(app)
    auth = {"Authorization": "Bearer owner"}
    assert api.get("/owner/restaurants/r1/board").status_code == 401
    assert api.get("/owner/restaurants/other/board", headers=auth).status_code == 404
    assert api.get("/owner/restaurants/r1/board", headers=auth).status_code == 200
    orders = api.get("/owner/restaurants/r1/orders", headers=auth).json()["orders"]
    assert "pay_token" not in orders[0] and "customer_phone" not in orders[0]

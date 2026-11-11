"""Recognising a caller and deciding whether an order has somewhere to go (no database)."""
import pytest

from app.customers import session as cs
from app.customers.phone import mask_phone, normalize_phone
from app.customers.session import CustomerContext, CustomerSession, start_session


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("9876543210", "+919876543210"),
        ("+91 98765 43210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("0091 9876543210", "+919876543210"),
        ("+14155552671", "+14155552671"),
        ("1234567890", None),  # not an Indian mobile start
        ("", None),
        (None, None),
        ("anonymous", None),
        ("+0123456789", None),
    ],
)
def test_phone_numbers_are_normalised_to_e164(raw, expected):
    assert normalize_phone(raw) == expected


def test_a_logged_number_is_masked():
    assert mask_phone("+919876543210") == "+91******3210"
    assert mask_phone(None) == "unknown"


ROW = {
    "customer": {"id": "c1", "name": "Meera", "language": "hi", "phone": "+919876543210"},
    "address": {"id": "a1", "line": "12 Palm Road, Andheri West", "area": "Andheri West", "landmark": None, "pincode": "400053"},
    "order_count": 3,
    "last_order": {"items": [{"name": "Dolo 650", "quantity": 2}, {"name": "ORS", "quantity": 1}, {"name": "Dolo 650", "quantity": 1}]},
}


def test_context_is_built_from_the_database_function_json():
    ctx = CustomerContext.from_row(ROW)
    assert ctx.known and ctx.name == "Meera" and ctx.order_count == 3
    assert ctx.address["area"] == "Andheri West"
    assert ctx.last_items == ("Dolo 650", "ORS")  # names once each, in order


@pytest.mark.parametrize("row", [None, {}, {"customer": None}])
def test_no_row_means_a_new_caller(row):
    assert not CustomerContext.from_row(row).known


def test_a_failed_lookup_is_a_new_caller_not_a_crash(monkeypatch):
    def boom(*_):
        raise RuntimeError("database down")

    monkeypatch.setattr(cs.repository, "customer_context", boom)
    assert not cs.load_context("r1", "+919876543210").known


def test_a_returning_customer_is_ready_to_order_without_an_address_question():
    s = CustomerSession("r1", "+919876543210", CustomerContext.from_row(ROW))
    assert s.delivery_ready() and s.fulfilment_kind() == "delivery"
    block = s.prompt_block()
    assert "NEVER ask for it" in block and "Andheri West" in block and "Meera" in block and "Dolo 650" in block
    assert "Do not ask for an address while" not in block


def test_a_new_delivery_customer_is_held_until_an_address_is_saved(monkeypatch):
    monkeypatch.setattr(cs.repository, "save_details", lambda *a: ("c9", "a9"))
    s = CustomerSession("r1", "+919876543210")
    assert not s.delivery_ready()
    assert "Do not ask for an address while they are choosing items" in s.prompt_block()
    s.save_details("Ravi", {"line": "4 MG Road, Bandra", "area": "Bandra"})
    assert s.delivery_ready() and s.customer_id == "c9" and s.display_name() == "Ravi"
    fields = s.order_fields()
    assert fields["customer_id"] == "c9" and fields["caller_phone"] == "+919876543210"
    assert fields["fulfilment"] == "delivery" and fields["address_snapshot"] == {"line": "4 MG Road, Bandra", "area": "Bandra"}


def test_pickup_needs_no_address():
    s = CustomerSession("r1", None)
    s.choose_pickup()
    assert s.delivery_ready() and s.fulfilment_kind() == "pickup" and "address_snapshot" not in s.order_fields()


def test_details_are_kept_for_this_call_even_when_the_database_save_fails(monkeypatch):
    def boom(*_):
        raise RuntimeError("down")

    monkeypatch.setattr(cs.repository, "save_details", boom)
    s = CustomerSession("r1", "+919876543210")
    s.save_details("Ravi", {"line": "4 MG Road, Bandra"})
    assert s.delivery_ready()


def test_a_caller_with_no_number_cannot_be_remembered_but_can_still_order(monkeypatch):
    called = []
    monkeypatch.setattr(cs.repository, "save_details", lambda *a: called.append(a))
    s = CustomerSession("r1", None)
    s.save_details("Ravi", {"line": "4 MG Road, Bandra"})
    assert s.delivery_ready() and not called


def test_a_table_guest_at_a_restaurant_gets_no_customer_session():
    assert start_session({"id": "r1", "business_type": "restaurant"}, None, "7") is None
    assert start_session({"id": "r1"}, None, "7") is None  # rows from before migration 002


def test_a_restaurant_phone_order_is_a_delivery(monkeypatch):
    monkeypatch.setattr(cs, "load_context", lambda *a: CustomerContext())
    s = start_session({"id": "r1", "business_type": "restaurant"}, "9876543210", None, verified=True)
    assert s.delivery_required and s.phone == "+919876543210"


def test_a_restaurant_guest_with_a_number_and_a_table_is_dine_in(monkeypatch):
    monkeypatch.setattr(cs, "load_context", lambda *a: CustomerContext.from_row(ROW))
    s = start_session({"id": "r1", "business_type": "restaurant"}, "9876543210", "7", verified=True)
    assert not s.delivery_required and s.delivery_ready() and s.fulfilment_kind() == "dine_in"


@pytest.mark.parametrize("kind", ["kirana", "pharmacy"])
def test_stores_always_deliver_even_with_no_number(kind):
    s = start_session({"id": "r1", "business_type": kind}, None, None)
    assert s.delivery_required and not s.delivery_ready()


def test_a_number_typed_into_a_web_page_is_ignored_on_a_real_store(monkeypatch):
    # Otherwise anyone could type someone else's number and be greeted with their name and area.
    looked_up = []
    monkeypatch.setattr(cs, "load_context", lambda *a: looked_up.append(a) or CustomerContext.from_row(ROW))
    for store in ({"id": "r1", "business_type": "kirana"}, {"id": "r1", "business_type": "kirana", "demo_mode": False}):
        s = start_session(store, "9876543210", None)
        assert s.phone is None and not s.context.known and not s.phone_verified
    assert not looked_up


def test_a_demo_store_accepts_a_typed_number_but_never_marks_it_verified(monkeypatch):
    monkeypatch.setattr(cs, "load_context", lambda *a: CustomerContext.from_row(ROW))
    s = start_session({"id": "r1", "business_type": "kirana", "demo_mode": True}, "9876543210", None)
    assert s.context.known and not s.phone_verified  # recognised for the demo, but never messaged on WhatsApp


def test_a_caller_id_or_whatsapp_sender_is_verified_on_any_store(monkeypatch):
    monkeypatch.setattr(cs, "load_context", lambda *a: CustomerContext.from_row(ROW))
    s = start_session({"id": "r1", "business_type": "kirana"}, "09876543210", None, verified=True)
    assert s.phone == "+919876543210" and s.phone_verified and s.context.known


def test_a_number_arriving_after_the_chat_began_starts_it_over_as_that_caller():
    anonymous = CustomerSession("r1", None)
    known = CustomerSession("r1", "+919876543210", phone_verified=False)
    assert cs.needs_identification(anonymous, known) and cs.needs_identification(None, known)
    assert not cs.needs_identification(known, known)  # already identified: leave it alone
    assert not cs.needs_identification(anonymous, CustomerSession("r1", None))  # still no number
    assert not cs.needs_identification(anonymous, None)

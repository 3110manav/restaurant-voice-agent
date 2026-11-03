"""Phone ordering without a phone: the order rules, WhatsApp queue, owner buttons, pay page and webhook.
The LLM is left out here; the rules these test are the ones that hold whatever the LLM does."""
import hashlib
import hmac
import json
import threading

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.agent import language as lang
from app.phone import actions, numbers, outbox, repository, upi, whatsapp
from app.phone.catalog import StoreCatalog
from app.phone.ordering import PhoneOrder
from app.phone.router import router
from tests.fake_supabase import FakeSupabase

OWNER = "919000000001"
CUSTOMER = "919000000002"
CATALOG = [
    {"id": "sugar", "name": "Sugar", "price": 48, "aliases": ["cheeni", "चीनी"],
     "variants": [{"name": "500 g", "price": 24}, {"name": "1 kg", "price": 48}]},
    {"id": "fortune", "name": "Fortune Sunflower Oil", "price": 165},
    {"id": "mustard", "name": "Mustard Oil", "price": 180},
]
LINE = {"id": "sugar", "name": "Sugar", "variant": "1 kg", "price": 48, "quantity": 2}


@pytest.fixture
def fake(monkeypatch):
    client = FakeSupabase()
    monkeypatch.setattr(db, "get_client", lambda: client)
    # Send only when a test calls flush, so what's in the queue can be checked first.
    monkeypatch.setattr(outbox, "flush_in_background", lambda: None)
    return client


@pytest.fixture
def store(fake):
    return repository.save_store(
        {
            "id": "store-1", "slug": "demo", "name": "Sharma Kirana", "business_type": "kirana",
            "agent_name": "Veer", "phone_number": "+918000000000", "owner_whatsapp": OWNER,
            "upi_id": "shop@okbank", "upi_payee_name": "Sharma Kirana", "upi_is_merchant": False,
        }
    )


@pytest.fixture
def sent(monkeypatch):
    """WhatsApp is configured, and everything sent is recorded instead."""
    log = []
    monkeypatch.setenv("WHATSAPP_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
    monkeypatch.setattr(whatsapp, "send_text", lambda to, text: log.append((to, "text", text)) or f"wa-{len(log)}")
    monkeypatch.setattr(
        whatsapp, "send_buttons", lambda to, text, buttons: log.append((to, "buttons", text, buttons)) or f"wa-{len(log)}"
    )
    monkeypatch.setattr(
        whatsapp, "send_image", lambda to, png, caption: log.append((to, "image", png, caption)) or f"wa-{len(log)}"
    )
    return log


def phone_order(store, caller=f"+{CUSTOMER}", delivery=True) -> PhoneOrder:
    order = PhoneOrder(store, caller, "quick_commerce", call_id="call-1")
    order.tools([dict(LINE)])
    if delivery:  # set directly: set_order_details also reads the order back, which tests do themselves
        order.order_type, order.address = "delivery", "12 MG Road"
    return order


def placed_order(store, fake) -> dict:
    order = phone_order(store)
    order.turn = 1
    order.prepare_read_back()
    order.turn = 2
    assert order.checkout().startswith("Order placed")
    return fake.tables["orders"][0]


# ------------------------------------------------------------------ the rules --


def test_nothing_is_placed_without_a_read_back(fake, store):
    order = phone_order(store)
    order.turn = 1
    assert order.checkout().startswith("Order not placed")
    assert "orders" not in fake.tables


def test_the_customer_must_answer_in_a_later_turn(fake, store):
    order = phone_order(store)
    order.turn = 1
    order.prepare_read_back()
    assert order.checkout().startswith("Order not placed")  # the LLM tried in the same turn
    assert "orders" not in fake.tables
    order.turn = 2
    assert order.checkout().startswith("Order placed")


def test_a_change_after_the_read_back_means_reading_it_again(fake, store):
    order = phone_order(store)
    order.turn = 1
    order.prepare_read_back()
    order.cart[0]["quantity"] = 3
    order.turn = 2
    assert order.checkout().startswith("Order not placed")
    order.prepare_read_back()
    order.turn = 3
    assert order.checkout().startswith("Order placed")
    assert fake.tables["orders"][0]["total"] == 144


def test_delivery_needs_an_address_and_pickup_doesnt(fake, store):
    order = phone_order(store, delivery=False)
    assert "address" in order.set_details("delivery").lower()
    assert "delivery or pickup" in order.prepare_read_back()
    assert order.set_details("pickup").startswith("Read back")


def test_a_landline_caller_must_give_a_whatsapp_number(fake, store):
    order = phone_order(store, caller="+914012345678")
    assert "WhatsApp" in order.prepare_read_back()
    assert "valid" in order.set_details("delivery", "12 MG Road", "12345")
    assert order.set_details("delivery", "12 MG Road", "9000000002").startswith("Read back")
    assert order.whatsapp == CUSTOMER


def test_placing_twice_saves_one_order(fake, store):
    order = phone_order(store)
    order.turn = 1
    order.prepare_read_back()
    order.turn = 2
    order.checkout()
    assert "already" in order.checkout()
    assert len(fake.tables["orders"]) == 1


def test_a_failed_save_never_says_placed_and_alerts_the_store(fake, store, sent):
    order = phone_order(store)
    order.turn = 1
    order.prepare_read_back()
    order.turn = 2
    fake.failing = True
    result = order.checkout()
    assert "could NOT be saved" in result and not result.startswith("Order placed")
    assert order.order_id is None and order.callback_reason
    assert sent[0][0] == OWNER and CUSTOMER in sent[0][2]


def test_a_callback_request_alerts_the_store_once(fake, store):
    order = phone_order(store)
    order.request_callback("wants to talk to the owner")
    assert "already" in order.request_callback("again")
    alerts = fake.tables["message_outbox"]
    assert len(alerts) == 1 and alerts[0]["recipient"] == OWNER and CUSTOMER in alerts[0]["body"]["text"]


def test_the_read_back_and_confirmation_are_spoken_from_code(fake, store):
    order = phone_order(store)
    order.start_turn("hi")
    order.prepare_read_back()
    assert "2 Sugar 1 kg" in order.spoken and "कुल 96 रुपये" in order.spoken and "MG Road" in order.spoken
    order.start_turn("en")
    assert order.spoken_reply() is None
    order.checkout()
    assert order.spoken.startswith("Your order is placed")


def test_changing_the_cart_after_a_read_back_reads_it_back_with_the_new_total(fake, store):
    order = phone_order(store)
    order.start_turn("en")
    order.prepare_read_back()
    order.start_turn("en")
    order.cart[0]["quantity"] = 1
    assert "Total forty eight rupees" in order.spoken_reply()
    assert order.read_back == order.cart and order.read_back_turn == order.turn
    assert order.checkout().startswith("Order not placed")  # a fresh read-back needs a fresh yes
    order.start_turn("en")
    assert order.checkout().startswith("Order placed")


# --------------------------------------------------------- messages and retries --


def test_the_order_queues_both_messages_from_saved_figures(fake, store):
    placed_order(store, fake)
    owner, customer = fake.tables["message_outbox"]
    assert owner["recipient"] == OWNER and owner["kind"] == "owner_order"
    assert [b["title"] for b in owner["body"]["buttons"]] == ["Accept", "Out of stock", "Paid"]
    assert "12 MG Road" in owner["body"]["text"] and CUSTOMER in owner["body"]["text"]
    assert customer["recipient"] == CUSTOMER and customer["kind"] == "customer_bill"
    assert "am=96.00" in customer["body"]["upi_uri"]


def test_flush_sends_a_bill_with_its_qr_and_marks_sent(fake, store, sent):
    placed_order(store, fake)
    outbox.flush()
    assert [entry[1] for entry in sent] == ["buttons", "image"]
    assert sent[1][2].startswith(b"\x89PNG")
    assert all(m["status"] == "sent" and m["wa_message_id"] for m in fake.tables["message_outbox"])
    outbox.flush()
    assert len(sent) == 2  # nothing is sent twice


def test_messages_wait_while_whatsapp_isnt_configured(fake, store, monkeypatch):
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    placed_order(store, fake)
    assert outbox.flush() == 0
    assert all(m["status"] == "pending" and m["attempts"] == 0 for m in fake.tables["message_outbox"])


def test_a_failed_send_keeps_the_order_and_is_retried(fake, store, sent, monkeypatch):
    placed_order(store, fake)

    def boom(*_):
        raise whatsapp.WhatsAppError("500: down")

    monkeypatch.setattr(whatsapp, "send_buttons", boom)
    monkeypatch.setattr(whatsapp, "send_image", boom)
    outbox.flush()
    assert len(fake.tables["orders"]) == 1
    messages = fake.tables["message_outbox"]
    assert all(m["status"] == "pending" and m["attempts"] == 1 and "down" in m["last_error"] for m in messages)
    assert outbox.flush() == 0  # the backoff hasn't passed

    monkeypatch.setattr(whatsapp, "send_image", lambda to, png, caption: "wa-ok")
    monkeypatch.setattr(whatsapp, "send_buttons", lambda to, text, buttons: "wa-ok")
    for message in messages:
        message["next_attempt_at"] = "2000-01-01T00:00:00+00:00"
    outbox.flush()
    assert all(m["status"] == "sent" for m in messages)


def test_a_bill_that_can_never_arrive_tells_the_owner(fake, store, sent, monkeypatch):
    placed_order(store, fake)

    def closed_window(*_):
        raise whatsapp.WhatsAppError("131047: window closed", retryable=False)

    monkeypatch.setattr(whatsapp, "send_image", closed_window)
    outbox.flush()
    bill = next(m for m in fake.tables["message_outbox"] if m["kind"] == "customer_bill")
    assert bill["status"] == "failed" and bill["attempts"] == 1
    note = next(m for m in fake.tables["message_outbox"] if m["kind"] == "owner_note")
    assert note["recipient"] == OWNER and CUSTOMER in note["body"]["text"]


def test_two_senders_cant_both_send_a_message(fake, store, sent):
    placed_order(store, fake)
    message = dict(fake.tables["message_outbox"][0])
    assert repository.claim_message(message) is True
    assert repository.claim_message(message) is False


# ---------------------------------------------------------------- owner buttons --


def tap(order, action, sender=OWNER):
    return actions.handle_button(sender, f"{action}:{order['id']}")


def customer_messages(fake):
    return [m["body"]["text"] for m in fake.tables["message_outbox"] if m["kind"].startswith("customer_") and m["kind"] != "customer_bill"]


def test_accept_updates_the_order_and_tells_the_customer(fake, store):
    order = placed_order(store, fake)
    assert tap(order, "accept") == "accepted"
    assert fake.tables["orders"][0]["status"] == "accepted"
    assert "स्वीकार" in customer_messages(fake)[0]


def test_a_double_tap_changes_nothing_and_doesnt_message_the_customer_twice(fake, store):
    order = placed_order(store, fake)
    tap(order, "accept")
    assert tap(order, "accept") == "unchanged"
    assert len(customer_messages(fake)) == 1


def test_only_the_stores_owner_can_tap(fake, store):
    order = placed_order(store, fake)
    assert tap(order, "paid", sender=CUSTOMER) == "not_owner"
    assert fake.tables["orders"][0]["payment_status"] == "unpaid"


def test_out_of_stock_cancels_the_bill(fake, store):
    order = placed_order(store, fake)
    assert tap(order, "out_of_stock") == "out_of_stock"
    assert "न चुकाएँ" in customer_messages(fake)[0]
    assert tap(order, "paid") == "unchanged"
    assert fake.tables["orders"][0]["payment_status"] == "unpaid"


def test_out_of_stock_after_payment_tells_the_owner_to_refund(fake, store):
    order = placed_order(store, fake)
    assert tap(order, "paid") == "paid"
    assert tap(order, "out_of_stock") == "out_of_stock"
    notes = [m["body"]["text"] for m in fake.tables["message_outbox"] if m["kind"] == "owner_note"]
    assert "refund" in notes[-1]


def test_unknown_buttons_are_ignored(fake, store):
    assert actions.handle_button(OWNER, "nonsense") == "ignored"
    assert actions.handle_button(OWNER, "paid:no-such-order") == "ignored"


# ------------------------------------------------------- pay page, webhook, admin --


@pytest.fixture
def http(fake, monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify-me")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-key")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_pay_page_shows_the_amount_and_link_but_no_personal_details(fake, store, http):
    order = placed_order(store, fake)
    page = http.get(f"/pay/{order['pay_token']}").text
    assert "upi://pay?pa=shop@okbank" in page and "am=96.00" in page and "Pay with UPI app" in page
    assert CUSTOMER not in page and "MG Road" not in page
    assert http.get(f"/pay/{order['pay_token']}/qr.png").content.startswith(b"\x89PNG")
    assert http.get("/pay/not-a-token").status_code == 404


def test_pay_page_stops_offering_payment_once_cancelled_or_paid(fake, store, http):
    order = placed_order(store, fake)
    tap(order, "out_of_stock")
    page = http.get(f"/pay/{order['pay_token']}").text
    assert "cancelled" in page and "upi://" not in page
    assert http.get(f"/pay/{order['pay_token']}/qr.png").status_code == 410


def _button_payload(button_id, sender=OWNER):
    return {"entry": [{"changes": [{"value": {"messages": [
        {"from": sender, "type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": button_id}}}
    ]}}]}]}


def _signed(payload, secret="secret"):
    raw = json.dumps(payload).encode()
    return raw, {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()}


def test_webhook_acts_on_a_signed_tap(fake, store, http):
    order = placed_order(store, fake)
    raw, headers = _signed(_button_payload(f"paid:{order['id']}"))
    assert http.post("/whatsapp/webhook", content=raw, headers=headers).status_code == 200
    assert fake.tables["orders"][0]["payment_status"] == "paid"


@pytest.mark.parametrize("headers", [{}, {"X-Hub-Signature-256": "sha256=wrong"}])
def test_webhook_refuses_a_forged_tap(fake, store, http, headers):
    order = placed_order(store, fake)
    raw = json.dumps(_button_payload(f"paid:{order['id']}")).encode()
    assert http.post("/whatsapp/webhook", content=raw, headers=headers).status_code == 403
    assert fake.tables["orders"][0]["payment_status"] == "unpaid"


def test_webhook_refuses_everything_without_a_secret(fake, store, http, monkeypatch):
    raw, headers = _signed({"entry": []})
    monkeypatch.delenv("WHATSAPP_APP_SECRET")
    assert http.post("/whatsapp/webhook", content=raw, headers=headers).status_code == 403


def test_webhook_records_a_failed_delivery(fake, store, sent, http):
    placed_order(store, fake)
    outbox.flush()
    wa_id = fake.tables["message_outbox"][1]["wa_message_id"]
    payload = {"entry": [{"changes": [{"value": {"statuses": [
        {"id": wa_id, "status": "failed", "errors": [{"code": 131026, "message": "Not on WhatsApp"}]}
    ]}}]}]}
    raw, headers = _signed(payload)
    http.post("/whatsapp/webhook", content=raw, headers=headers)
    bill = fake.tables["message_outbox"][1]
    assert bill["delivery_status"] == "failed" and "131026" in bill["last_error"]


def test_webhook_verification(http):
    params = {"hub.mode": "subscribe", "hub.challenge": "42", "hub.verify_token": "verify-me"}
    assert http.get("/whatsapp/webhook", params=params).text == "42"
    assert http.get("/whatsapp/webhook", params={**params, "hub.verify_token": "no"}).status_code == 403


def test_the_calls_view_needs_the_admin_key(fake, store, http):
    assert http.get("/admin/calls").status_code == 401
    assert http.get("/admin/calls", headers={"X-Admin-Key": "wrong"}).status_code == 401
    call_id = repository.start_call("call-room", "store-1", f"+{CUSTOMER}")
    order = phone_order(store)
    order.call_id = call_id
    order.turn = 1
    order.prepare_read_back()
    order.turn = 2
    order.checkout()
    calls = http.get("/admin/calls", headers={"X-Admin-Key": "admin-key"}).json()["calls"]
    assert calls[0]["store_name"] == "Sharma Kirana"
    assert calls[0]["order"]["total"] == 96 and "pay_token" not in calls[0]["order"]
    assert [m["kind"] for m in calls[0]["messages"]] == ["owner_order", "customer_bill"]
    assert "upi_uri" not in calls[0]["messages"][1]["body"]


def test_the_calls_view_is_off_without_a_key_set(http, monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY")
    assert http.get("/admin/calls", headers={"X-Admin-Key": "x"}).status_code == 503


def test_the_open_orders_view_hides_phone_customers(monkeypatch):
    from app import erp

    client = FakeSupabase()
    client.tables["orders"] = [
        {"id": "1", "total": 96, "customer_phone": CUSTOMER, "address": "12 MG Road", "pay_token": "secret", "created_at": "1"}
    ]
    monkeypatch.setattr(erp, "_client", client)
    assert erp.list_orders() == [{"id": "1", "total": 96, "created_at": "1"}]


# ---------------------------------------------------------- catalog and helpers --


@pytest.mark.parametrize("said", ["cheeni", "चीनी", "Sugar", "sugar"])
def test_a_catalog_item_is_found_however_its_said(said):
    assert StoreCatalog(CATALOG).find_by_name(said)["id"] == "sugar"


def test_a_vague_name_is_a_question_not_a_guess():
    catalog = StoreCatalog(CATALOG)
    assert catalog.find_by_name("oil") is None
    assert {item["id"] for item in catalog.candidates("oil")} == {"fortune", "mustard"}


@pytest.mark.parametrize(
    "raw, expected",
    [("09000000002", CUSTOMER), (f"+{CUSTOMER}", CUSTOMER), ("9000000002", CUSTOMER), ("12345", None), ("+14155550100", None), (None, None)],
)
def test_whatsapp_numbers(raw, expected):
    assert numbers.whatsapp_number(raw) == expected


def test_a_dialled_landline_still_matches_its_store():
    assert numbers.canonical("08047123456") == "+918047123456" == numbers.canonical("+918047123456")


@pytest.mark.parametrize(
    "text, current, expected",
    [
        ("मुझे two Dove soap चाहिए", "en", "hi"),
        ("bhaiya do kilo cheeni bhejo", "en", "hi"),
        ("please send two soaps", "hi", "en"),
        ("yes", "hi", "hi"),
        ("Dove", "en", "en"),
        ("हाँ", "en", "hi"),
    ],
)
def test_caller_language_follows_what_they_say(text, current, expected):
    assert lang.caller_language(text, current) == expected


def test_upi_link_is_encoded_and_only_merchants_get_a_reference():
    personal = {"upi_id": "shop@okbank", "upi_payee_name": "Sharma & Sons"}
    uri = upi.payment_uri(personal, 96, "AB12CD")
    assert uri == "upi://pay?pa=shop@okbank&pn=Sharma%20%26%20Sons&am=96.00&cu=INR&tn=Order%20AB12CD"
    assert "tr=AB12CD" in upi.payment_uri({**personal, "upi_is_merchant": True}, 96, "AB12CD")


def test_whatsapp_errors_say_whether_a_retry_can_help(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1")

    def respond(status, code):
        return httpx.Response(status, json={"error": {"code": code, "message": "m"}}, request=httpx.Request("POST", "http://x"))

    with pytest.raises(whatsapp.WhatsAppError) as closed:
        whatsapp._checked(respond(400, 131047))
    assert closed.value.retryable is False
    with pytest.raises(whatsapp.WhatsAppError) as limited:
        whatsapp._checked(respond(429, 130429))
    assert limited.value.retryable is True


def test_the_requests_sent_to_whatsapp(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "555")
    requests = []

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        body = {"id": "media-1"} if url.endswith("/media") else {"messages": [{"id": "wa-1"}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(whatsapp.httpx, "post", fake_post)

    assert whatsapp.send_buttons(OWNER, "hi", [{"id": "paid:1", "title": "Paid"}]) == "wa-1"
    url, sent = requests[-1]
    assert url.endswith("/555/messages") and sent["headers"]["Authorization"] == "Bearer t"
    assert sent["json"]["messaging_product"] == "whatsapp" and sent["json"]["to"] == OWNER
    assert sent["json"]["interactive"]["action"]["buttons"] == [
        {"type": "reply", "reply": {"id": "paid:1", "title": "Paid"}}
    ]

    assert whatsapp.send_image(CUSTOMER, b"png", "bill") == "wa-1"
    upload_url, upload = requests[-2]
    assert upload_url.endswith("/555/media") and upload["files"]["file"][2] == "image/png"
    assert requests[-1][1]["json"]["image"] == {"id": "media-1", "caption": "bill"}


def test_a_very_long_bill_goes_as_text_then_qr(fake, store, sent):
    order = {"id": "1", "items": [dict(LINE, name=f"Item {i}" * 8) for i in range(30)], "total": 1, "order_type": "pickup", "address": None, "payment_ref": "AB"}
    from app.phone import messages

    body = messages.customer_bill(order, store, "upi://pay?pa=a@b", None, "en")
    assert len(body["caption"]) <= messages.CAPTION_LIMIT and "Item 0" in body["text_first"]
    repository.queue_message(CUSTOMER, "customer_bill", body)
    outbox.flush()
    assert [entry[1] for entry in sent] == ["text", "image"]


def test_the_retry_loop_stops_when_told(fake, store, monkeypatch):
    stop = threading.Event()
    stop.set()
    outbox.run_forever(stop)  # returns at once instead of hanging the tests

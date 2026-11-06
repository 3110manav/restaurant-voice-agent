"""WhatsApp: sending, who gets told about an order, the webhook, and an owner's replies (no network, no database)."""
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.whatsapp import channels, client, inbound, notify, webhook
from app.whatsapp.channels import Channel

CH = Channel("ch1", "r1", "PNID1", "+919000011111", "WHATSAPP_ACCESS_TOKEN", ("+919811111111",), ("+919822222222",))
STORE = {"id": "r1", "slug": "care-plus", "name": "Care Plus Medicals", "status": "live", "business_type": "pharmacy"}


@pytest.fixture
def sent(monkeypatch):
    """Capture every outgoing message instead of calling Meta or the database."""
    log = []
    monkeypatch.setattr(channels, "log_message", lambda *a, **k: log.append(("logged", a, k)) or True)
    monkeypatch.setattr(client, "_post", lambda channel, payload: log.append(("post", payload)) or "wamid.1")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    return log


def posts(log):
    return [entry[1] for entry in log if entry[0] == "post"]


# ----------------------------------------------------------------------------------------- sending --


def test_a_text_message_has_the_cloud_api_shape(sent):
    client.send_text(CH, "+919876543210", "hello")
    (payload,) = posts(sent)
    assert payload == {"to": "919876543210", "type": "text", "text": {"body": "hello"}}


def test_a_template_message_has_named_text_parameters(sent):
    client.send_template(CH, "+919811111111", "sarthi_order_alert", ["K7M2P", "Ravi", "2 x Soap"])
    (payload,) = posts(sent)
    assert payload["type"] == "template" and payload["template"]["name"] == "sarthi_order_alert"
    body = payload["template"]["components"][0]
    assert body["type"] == "body" and [p["text"] for p in body["parameters"]] == ["K7M2P", "Ravi", "2 x Soap"]


def test_template_variables_never_contain_newlines_or_runs_of_spaces():
    assert client.clean_param("2 x Soap,\n  1 x\tBatteries") == "2 x Soap, 1 x Batteries"
    assert client.clean_param("") == "-" and len(client.clean_param("x" * 999)) == 300


def test_with_no_token_nothing_is_sent_but_it_is_logged(monkeypatch):
    log = []
    monkeypatch.setattr(channels, "log_message", lambda *a, **k: log.append((a, k)) or True)
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(client, "_post", lambda *a: pytest.fail("must not call Meta without a token"))
    client.send_text(CH, "+919876543210", "hello")
    assert log[0][0][6] == "logged"  # status


def test_a_rejected_send_is_logged_as_failed_and_never_raises(monkeypatch):
    log = []
    monkeypatch.setattr(channels, "log_message", lambda *a, **k: log.append((a, k)) or True)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    monkeypatch.setattr(client, "_post", lambda *a: (_ for _ in ()).throw(client.WhatsAppError("131047: window closed")))
    assert client.send_text(CH, "+919876543210", "hi") is None
    assert log[0][0][6] == "failed" and "131047" in log[0][1]["error"]


def test_post_reports_metas_error_message():
    transport = httpx.MockTransport(lambda r: httpx.Response(400, json={"error": {"code": 131030, "message": "not in allowed list"}}))
    client._http = httpx.Client(transport=transport)
    try:
        with pytest.raises(client.WhatsAppError, match="131030"):
            client._post(CH, {"to": "1", "type": "text", "text": {"body": "x"}})
    finally:
        client._http = None


# ------------------------------------------------------------------------------------ order alerts --

LINES = [{"name": "Dolo 650", "quantity": 2, "price": 32}, {"name": "Azithral 500", "quantity": 1, "price": 120, "rx": True}]


def order(**kw):
    return {"code": "K7M2P", "order_id": "o1", "lines": LINES, "total": 184.0, "fulfilment": "delivery",
            "address": "402 Sunrise Apts, Bandra West", "customer_name": "Ravi", "phone": "+919876543210",
            "phone_verified": True, "rx_path": None, "channel": "voice", **kw}


@pytest.fixture
def announce(monkeypatch):
    out = []
    monkeypatch.setattr(channels, "channel_for_store", lambda rid: CH)
    monkeypatch.setattr(client, "send_template", lambda ch, to, name, params, oid=None: out.append((to, name, params)))
    monkeypatch.setattr(client, "send_text", lambda ch, to, body, oid=None: out.append((to, "text", body)))
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: False)
    notify._alerts.clear()
    return out


def test_an_ordinary_order_alerts_the_owner_and_confirms_to_a_verified_caller(announce):
    notify.order_placed(STORE, order(lines=[LINES[0]], total=64.0))
    assert [(to, name) for to, name, _ in announce] == [("+919811111111", "sarthi_order_alert"), ("+919876543210", "sarthi_order_confirmation")]
    params = announce[0][2]
    assert params[0] == "K7M2P" and "Ravi (+919876543210)" in params[1] and "Rs 64" in params and "Deliver to: 402 Sunrise Apts, Bandra West" in params


def test_an_unverified_number_is_never_messaged_as_a_customer(announce):
    notify.order_placed(STORE, order(lines=[LINES[0]], phone_verified=False, channel="web"))
    assert [to for to, *_ in announce] == ["+919811111111"]  # the owner only


def test_a_typed_number_on_a_real_store_is_never_messaged_even_if_it_wrote_first(announce, monkeypatch):
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: True)
    notify.order_placed(STORE, order(lines=[LINES[0]], phone_verified=False, channel="web"))
    assert [to for to, *_ in announce] == ["+919811111111"]


def test_a_typed_number_on_a_demo_store_is_messaged_only_after_it_wrote_first(announce, monkeypatch):
    demo = {**STORE, "demo_mode": True}
    notify.order_placed(demo, order(lines=[LINES[0]], phone_verified=False, channel="web"))
    assert [to for to, *_ in announce] == ["+919811111111"]  # never opted in: no message
    announce.clear()
    notify._alerts.clear()
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: True)  # they sent "hi" to the store's number
    notify.order_placed(demo, order(lines=[LINES[0]], phone_verified=False, channel="web"))
    customer = [m for m in announce if m[0] == "+919876543210"]
    assert customer and customer[0][1] == "text" and "Rs 184" in customer[0][2]  # free text inside their window


def test_a_verified_number_gets_free_text_inside_its_window_and_a_template_outside(announce, monkeypatch):
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: True)
    notify.order_placed(STORE, order(lines=[LINES[0]], total=64.0))
    assert ("+919876543210", "text") in [(to, name) for to, name, _ in announce]


def test_a_customer_already_chatting_on_whatsapp_is_not_sent_a_template(announce):
    notify.order_placed(STORE, order(lines=[LINES[0]], channel="whatsapp"))
    assert [to for to, *_ in announce] == ["+919811111111"]


def test_a_prescription_order_to_be_sent_on_whatsapp_goes_to_the_pharmacist_and_asks_the_customer(announce):
    notify.order_placed(STORE, order(rx_path="whatsapp"))
    assert [(to, name) for to, name, _ in announce] == [("+919822222222", "sarthi_rx_order"), ("+919876543210", "sarthi_rx_request")]
    assert "[Rx]" in announce[0][2][2] and "prescription on WhatsApp" in announce[0][2][3]


def test_choosing_the_pharmacist_asks_the_pharmacist_to_call_and_says_nothing_to_the_customer(announce):
    notify.order_placed(STORE, order(rx_path="pharmacist"))
    assert [(to, name) for to, name, _ in announce] == [("+919822222222", "sarthi_rx_order")]
    assert "call +919876543210" in announce[0][2][3]


def test_prescription_alerts_fall_back_to_the_owner_when_there_is_no_pharmacist_number(announce, monkeypatch):
    monkeypatch.setattr(channels, "channel_for_store", lambda rid: Channel("c", "r1", "P", None, "T", ("+919811111111",), ()))
    notify.order_placed(STORE, order(rx_path="pharmacist", phone_verified=False))
    assert [to for to, *_ in announce] == ["+919811111111"]


def test_a_store_with_no_channel_just_skips_the_alert(monkeypatch):
    monkeypatch.setattr(channels, "channel_for_store", lambda rid: None)
    monkeypatch.setattr(client, "send_template", lambda *a, **k: pytest.fail("no channel, nothing to send"))
    notify.order_placed(STORE, order())


def test_alerts_to_one_store_are_capped_per_hour(announce, monkeypatch):
    monkeypatch.setattr(notify, "MAX_ALERTS_PER_HOUR", 2)
    for _ in range(5):
        notify.order_placed(STORE, order(lines=[LINES[0]], phone_verified=False))
    assert len(announce) == 2  # a flood of fake web orders cannot spam the owner


def test_a_status_update_is_free_text_inside_the_window_and_a_template_outside(announce, monkeypatch):
    o = {"id": "o1", "short_code": "K7M2P", "caller_phone": "+919876543210", "customer_name": "Ravi"}
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: True)
    notify.tell_customer_update(CH, STORE, o, "confirmed")
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: False)
    notify.tell_customer_update(CH, STORE, o, "confirmed")
    assert [name for _, name, _ in announce] == ["text", "sarthi_order_update"]


# --------------------------------------------------------------------------------------- webhook --


def sign(body: bytes, secret="s3cret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def inbound_payload(text="hi", mid="wamid.A", sender="919876543210", kind="text", **extra):
    message = {"from": sender, "id": mid, "type": kind, **extra}
    if kind == "text":
        message["text"] = {"body": text}
    return {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "PNID1"}, "messages": [message]}}]}]}


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "s3cret")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify-me")
    api = FastAPI()
    api.include_router(webhook.router)
    return TestClient(api)


def test_the_handshake_echoes_the_challenge_only_for_the_right_token(app_client):
    ok = app_client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    assert app_client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"}).status_code == 403


def test_an_event_with_a_bad_or_missing_signature_is_rejected(app_client, monkeypatch):
    monkeypatch.setattr(webhook, "process_payload", lambda p: pytest.fail("must not process an unsigned event"))
    body = json.dumps(inbound_payload()).encode()
    assert app_client.post("/whatsapp/webhook", content=body).status_code == 401
    assert app_client.post("/whatsapp/webhook", content=body, headers={"x-hub-signature-256": sign(body, "wrong")}).status_code == 401


def test_a_correctly_signed_event_is_accepted_and_processed(app_client, monkeypatch):
    seen = []
    monkeypatch.setattr(webhook, "process_payload", lambda p: seen.append(p))
    body = json.dumps(inbound_payload()).encode()
    assert app_client.post("/whatsapp/webhook", content=body, headers={"x-hub-signature-256": sign(body)}).status_code == 200
    assert seen and seen[0]["entry"]


def test_with_no_app_secret_events_are_refused_unless_testing_is_switched_on(app_client, monkeypatch):
    monkeypatch.delenv("WHATSAPP_APP_SECRET")
    assert app_client.post("/whatsapp/webhook", json={}).status_code == 503
    monkeypatch.setenv("WHATSAPP_ALLOW_UNSIGNED", "1")
    assert app_client.post("/whatsapp/webhook", json={}).status_code == 200


@pytest.fixture
def chat(monkeypatch):
    out = {"replies": [], "texts": [], "statuses": []}
    monkeypatch.setattr(channels, "channel_by_phone_number_id", lambda pid: CH if pid == "PNID1" else None)
    monkeypatch.setattr(webhook.repository, "get_restaurant", lambda rid: STORE)
    monkeypatch.setattr(channels, "log_message", lambda *a, **k: True)
    monkeypatch.setattr(client, "send_text", lambda ch, to, body, oid=None: out["texts"].append((to, body)))
    monkeypatch.setattr(inbound, "reply_to_text", lambda store, phone, text: out["replies"].append((phone, text)) or "agent says hi")
    return out


def test_a_customers_text_goes_to_the_agent_and_its_reply_is_sent_back(chat):
    webhook.process_payload(inbound_payload("two soaps please"))
    assert chat["replies"] == [("+919876543210", "two soaps please")]
    assert ("+919876543210", "agent says hi") in chat["texts"]


def test_a_message_for_an_unknown_number_is_ignored(chat):
    payload = inbound_payload()
    payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "OTHER"
    webhook.process_payload(payload)
    assert chat["replies"] == []


def test_a_retried_message_is_handled_once(monkeypatch):
    handled, seen = [], set()
    monkeypatch.setattr(channels, "channel_by_phone_number_id", lambda pid: CH)
    monkeypatch.setattr(webhook.repository, "get_restaurant", lambda rid: STORE)
    monkeypatch.setattr(channels, "log_message", lambda *a, wa_message_id=None, **k: wa_message_id not in seen and not seen.add(wa_message_id))
    monkeypatch.setattr(client, "send_text", lambda *a, **k: None)
    monkeypatch.setattr(inbound, "reply_to_text", lambda store, phone, text: handled.append(text) or "ok")
    payload = inbound_payload("hello", mid="wamid.SAME")
    webhook.process_payload(payload)
    webhook.process_payload(payload)  # Meta delivers again because it did not get a fast 200
    assert handled == ["hello"]


def test_staff_commands_are_parsed(monkeypatch):
    assert inbound.parse_command("Confirm k7m2p") == ("confirm", "K7M2P", "")
    assert inbound.parse_command("reject K7M2P out of stock") == ("reject", "K7M2P", "out of stock")
    assert inbound.parse_command("show K7M2P") == ("show", "K7M2P", "")
    assert inbound.parse_command("ok thanks") is None and inbound.parse_command("two soaps") is None
    assert inbound.parse_command("ready please") is None and inbound.parse_command("confirm hello") is None


def test_an_owner_command_updates_the_order_and_tells_the_customer(monkeypatch):
    updates, told = [], []
    order_row = {"id": "o1", "short_code": "K7M2P", "caller_phone": "+919876543210", "customer_name": "Ravi"}
    monkeypatch.setattr(channels, "order_by_code", lambda rid, code: order_row)
    monkeypatch.setattr(channels, "set_order_status", lambda oid, status: updates.append((oid, status)))
    monkeypatch.setattr(notify, "tell_customer_update", lambda ch, store, order, text: told.append(text))
    reply = inbound.staff_command(CH, STORE, "+919811111111", ("reject", "K7M2P", "out of stock"))
    assert updates == [("o1", "rejected")] and "out of stock" in told[0] and "K7M2P" in told[0]
    assert "rejected" in reply
    inbound.staff_command(CH, STORE, "+919811111111", ("confirm", "K7M2P", ""))
    assert updates[-1] == ("o1", "confirmed") and "confirmed" in told[-1]


def test_an_unknown_order_code_is_reported(monkeypatch):
    monkeypatch.setattr(channels, "order_by_code", lambda rid, code: None)
    assert "can't find" in inbound.staff_command(CH, STORE, "+919811111111", ("confirm", "ZZZZZ", ""))


def test_a_staff_member_chatting_normally_is_treated_as_a_customer(chat):
    webhook.process_payload(inbound_payload("I need paracetamol", sender="919811111111"))  # the owner's own number
    assert chat["replies"] == [("+919811111111", "I need paracetamol")]


def test_a_prescription_photo_moves_the_order_on_and_tells_the_pharmacist(monkeypatch):
    status, shown = [], []
    monkeypatch.setattr(channels, "latest_order_awaiting_prescription", lambda rid, phone: {"id": "o1", "short_code": "K7M2P", "customer_name": "Ravi"})
    monkeypatch.setattr(channels, "set_order_status", lambda oid, s: status.append(s))
    monkeypatch.setattr(notify, "prescription_arrived", lambda ch, store, order, media, who: shown.append((media, who)))
    monkeypatch.setattr(inbound, "_chat", lambda store, phone, lang: type("C", (), {"agent": type("A", (), {"language": "en"})()})())
    reply = inbound.handle_media(CH, STORE, "+919876543210", "MEDIA9", "")
    assert status == ["prescription_received"] and shown[0][0] == "MEDIA9" and "K7M2P" in reply


def test_a_photo_with_no_order_waiting_gets_a_friendly_answer(monkeypatch):
    monkeypatch.setattr(channels, "latest_order_awaiting_prescription", lambda rid, phone: None)
    monkeypatch.setattr(inbound, "_chat", lambda store, phone, lang: type("C", (), {"agent": type("A", (), {"language": "en"})()})())
    assert "don't see an order" in inbound.handle_media(CH, STORE, "+919876543210", "M", "")


def test_the_pharmacist_gets_the_photo_in_an_open_window_and_a_template_otherwise(announce, monkeypatch):
    images = []
    monkeypatch.setattr(client, "send_image_by_id", lambda ch, to, media, caption, oid=None: images.append((to, media)))
    o = {"id": "o1", "short_code": "K7M2P"}
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: True)
    notify.prescription_arrived(CH, STORE, o, "MEDIA9", "Ravi (+91...)")
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: False)
    notify.prescription_arrived(CH, STORE, o, "MEDIA9", "Ravi (+91...)")
    assert images == [("+919822222222", "MEDIA9")] and announce[0][1] == "sarthi_rx_received"


# ---------------------------------------------------------------------------------- the checker --


def test_the_checker_reports_who_the_number_is(monkeypatch):
    from app import whatsapp_check
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    seen = {}

    def handler(request):
        seen["url"], seen["auth"] = str(request.url), request.headers["authorization"]
        return httpx.Response(200, json={"verified_name": "Test Number", "display_phone_number": "+1 555 000 1111", "quality_rating": "GREEN"})

    info = whatsapp_check.describe("PNID1", httpx.Client(transport=httpx.MockTransport(handler)))
    assert info["verified_name"] == "Test Number"
    assert "/PNID1" in seen["url"] and seen["auth"] == "Bearer t"


def test_the_checker_surfaces_metas_own_message_for_a_bad_token(monkeypatch):
    from app import whatsapp_check
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "expired")
    transport = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"code": 190, "message": "Session has expired"}}))
    with pytest.raises(client.WhatsAppError, match="190: Session has expired"):
        whatsapp_check.describe("PNID1", httpx.Client(transport=transport))


def test_registering_a_number_posts_the_pin_and_reports_metas_refusal(monkeypatch):
    from app import whatsapp_check
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    seen = {}

    def ok(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"success": True})

    whatsapp_check.register("PNID1", "123456", httpx.Client(transport=httpx.MockTransport(ok)))
    assert seen["url"].endswith("/PNID1/register") and seen["body"] == {"messaging_product": "whatsapp", "pin": "123456"}
    refuse = httpx.MockTransport(lambda r: httpx.Response(400, json={"error": {"code": 133005, "message": "Two-step verification PIN mismatch"}}))
    with pytest.raises(client.WhatsAppError, match="133005"):
        whatsapp_check.register("PNID1", "000000", httpx.Client(transport=refuse))


def test_an_alert_is_plain_text_when_the_owner_has_messaged_the_shop_recently(announce, monkeypatch):
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: peer == "+919811111111")  # only the owner wrote first
    notify.order_placed(STORE, order(lines=[LINES[0]], total=64.0, phone_verified=False))
    (to, kind, body), = [m for m in announce if m[0] == "+919811111111"]
    assert kind == "text" and "New order K7M2P" in body and "Rs 64" in body and "Reply with CONFIRM or REJECT" in body


def test_a_prescription_alert_is_plain_text_inside_the_pharmacists_window(announce, monkeypatch):
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: True)
    notify.order_placed(STORE, order(rx_path="whatsapp", phone_verified=False))
    (to, kind, body), = [m for m in announce if m[0] == "+919822222222"]
    assert kind == "text" and "needs a prescription check" in body and "[Rx]" in body

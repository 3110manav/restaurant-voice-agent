"""The template wording must satisfy Meta's rules and match what the code sends."""
import httpx
import pytest

from app.whatsapp import notify, template_defs
from app import whatsapp_templates


@pytest.mark.parametrize("key", list(template_defs.DEFINITIONS))
def test_each_template_follows_metas_rules(key):
    d = template_defs.DEFINITIONS[key]
    nums = template_defs.variables(d["body"])
    assert sorted(set(nums)) == list(range(1, len(set(nums)) + 1)), "variables are numbered 1..n"
    assert len(nums) == len(set(nums)), "a variable is used once: Meta rejects repeats"
    assert len(d["samples"]) == len(set(nums)), "one sample value per variable"
    assert not d["body"].startswith("{{") and not d["body"].rstrip().endswith("}}"), "must not start or end with a variable"
    assert len(d["body"]) <= 1024 and all("\n" not in s for s in d["samples"])


def test_every_template_the_code_sends_is_defined():
    assert set(notify.TEMPLATES) == set(template_defs.DEFINITIONS)


def test_the_number_of_values_the_code_sends_matches_the_template(monkeypatch):
    """notify fills the variables in the order of the numbers: the counts must agree."""
    from app.whatsapp import channels, client
    sent = {}
    monkeypatch.setattr(channels, "channel_for_store", lambda rid: channels.Channel("c", "r1", "P", None, "T", ("+919811111111",), ("+919822222222",)))
    monkeypatch.setattr(client, "send_template", lambda ch, to, name, params, oid=None: sent.setdefault(name, len(params)))
    monkeypatch.setattr(channels, "window_open", lambda rid, peer: False)
    notify._alerts.clear()
    store = {"id": "r1", "name": "Care Plus", "slug": "cp"}
    base = {"code": "K7M2P", "lines": [{"name": "Dolo", "quantity": 1}], "total": 32.0, "fulfilment": "delivery",
            "address": "x", "customer_name": "Ravi", "phone": "+919876543210", "phone_verified": True, "channel": "voice"}
    notify.order_placed(store, {**base, "rx_path": None})
    notify.order_placed(store, {**base, "rx_path": "whatsapp"})
    notify.prescription_arrived(channels.Channel("c", "r1", "P", None, "T", (), ("+919822222222",)), store, {"short_code": "K7M2P"}, "M", "Ravi")
    notify.tell_customer_update(channels.Channel("c", "r1", "P", None, "T", (), ()), store, {"caller_phone": "+919876543210", "short_code": "K7M2P"}, "ok")
    for key, name in notify.TEMPLATES.items():
        assert sent[name] == len(set(template_defs.variables(template_defs.DEFINITIONS[key]["body"]))), key


def test_submit_creates_only_the_missing_templates(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    created = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"name": "sarthi_order_alert", "language": "en", "status": "APPROVED"}]})
        body = __import__("json").loads(request.content)
        created.append(body)
        return httpx.Response(200, json={"id": "1", "status": "PENDING"})

    results = whatsapp_templates.submit("WABA1", httpx.Client(transport=httpx.MockTransport(handler)))
    assert results["sarthi_order_alert"] == "exists"
    assert len(created) == 5 and all(r == "created" for n, r in results.items() if n != "sarthi_order_alert")
    sample = created[0]
    assert sample["category"] == "UTILITY" and sample["language"] == "en"
    assert sample["components"][0]["example"]["body_text"] == [template_defs.DEFINITIONS[next(k for k, v in notify.TEMPLATES.items() if v == sample["name"])]["samples"]]


def test_a_rejected_submission_reports_metas_reason(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(400, json={"error": {"code": 100, "message": "Invalid parameter", "error_user_msg": "Body ends with a variable"}})

    results = whatsapp_templates.submit("WABA1", httpx.Client(transport=httpx.MockTransport(handler)))
    assert all(r.startswith("FAILED 100: Body ends with a variable") for r in results.values())

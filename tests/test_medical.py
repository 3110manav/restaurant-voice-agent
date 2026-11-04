"""The pharmacy safety rules: what is screened before the model, and what the model may not say."""
import pytest

from app.agent import guardrails as g
from app.agent import medical


@pytest.mark.parametrize(
    "text",
    [
        "I have chest pain and I feel dizzy",
        "my father can't breathe properly",
        "he is unconscious",
        "she took too many tablets",
        "bleeding won't stop",
        "सीने में दर्द हो रहा है",
        "saans nahi aa rahi",
    ],
)
def test_emergencies_are_caught(text):
    assert medical.screen_input(text) == "emergency"


@pytest.mark.parametrize(
    "text",
    [
        "how many tablets should I take",
        "what is the dose of paracetamol for a child",
        "can I take this with alcohol",
        "I am pregnant, can I use it",
        "is it safe for my 3 month old baby",
        "does it have side effects",
        "कितनी गोली लेनी है",
        "kitni baar khani hai",
    ],
)
def test_dose_and_safety_questions_go_to_the_pharmacist(text):
    assert medical.screen_input(text) == "advice"


@pytest.mark.parametrize(
    "text",
    [
        "do you have something for fever",
        "add a Dolo 650 and two ORS",
        "how long will the delivery take",
        "how many tablets are in a strip",  # product information, not dosing advice
        "that fits my budget",
        "I want a cough syrup",
        "बुखार की दवा चाहिए",
    ],
)
def test_ordinary_requests_are_not_screened(text):
    assert medical.screen_input(text) is None


@pytest.mark.parametrize(
    "reply, issue",
    [
        ("Take two tablets twice a day after food.", "dosage_advice"),
        ("Have one tablet every 6 hours.", "dosage_advice"),
        ("Use it for 5 days.", "dosage_advice"),
        ("You have a viral infection.", "diagnosis"),
        ("This will cure your cough.", "diagnosis"),
        ("It is probably an allergy.", "diagnosis"),
    ],
)
def test_replies_that_dose_or_diagnose_are_flagged(reply, issue):
    assert issue in medical.reply_issues(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "Dolo 650 is commonly used for fever and body ache. Our pharmacist will confirm.",
        "I've added two ORS sachets. Anything else?",
        "If you have liver problems, please ask our pharmacist first.",
        "That needs a prescription, and our pharmacist will check it before it goes out.",
    ],
)
def test_ordinary_shop_replies_pass(reply):
    assert medical.reply_issues(reply) == []


def test_the_guardrail_only_applies_to_a_pharmacy():
    facts = g.TurnFacts(user_text="x", medical=False)
    assert not [v for v in g.check_reply("Take two tablets twice a day.", facts) if v.kind == "dosage_advice"]
    facts = g.TurnFacts(user_text="x", medical=True)
    assert any(v.kind == "dosage_advice" for v in g.check_reply("Take two tablets twice a day.", facts))


def test_a_dose_that_survives_regeneration_becomes_the_pharmacist_line():
    kinds = [g.Violation("dosage_advice")]
    assert "pharmacist" in g.fallback_reply(kinds, "Take two tablets daily.", "en")
    assert g.fallback_reply(kinds, "x", "hi") != g.fallback_reply(kinds, "x", "en")

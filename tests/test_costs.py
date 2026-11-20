"""The per-call cost meter (app/voice/costs.py): the arithmetic, the price overrides, and that each hook counts
what is really billed."""
import pytest

from app.agent.graph import RestaurantOrderingAgent
from app.phone import repository
from app.phone.call import PhoneCall
from app.voice import costs
from app.voice.costs import CallCost


def one_minute(meter: CallCost) -> CallCost:
    meter.started, meter.ended = 0.0, 60.0
    return meter


@pytest.fixture(autouse=True)
def default_prices(monkeypatch):
    monkeypatch.delenv("COST_PRICES", raising=False)


def test_a_typical_sarvam_browser_minute():
    meter = one_minute(CallCost("browser", "sarvam", "saaras:v3"))
    meter.add_stt("saaras:v3", 60)  # ₹30/hour
    meter.add_tts("bulbul:v4-flash", 400)  # ₹20 per 10k characters
    meter.add_llm("openai/gpt-oss-120b", 32_000, 1_600)  # $0.15 / $0.60 per million, at ₹93 to the dollar
    report = meter.summary()
    assert report["inr"] == {"stt": 0.5, "tts": 0.8, "llm": 0.536, "livekit": 0.0}  # LiveKit is self-hosted
    assert report["total_inr"] == 1.84 and report["inr_per_min"] == 1.84
    assert report["unpriced"] == [] and report["minutes"] == 1.0


def test_livekit_cloud_and_server_costs_can_be_priced_in(monkeypatch):
    monkeypatch.setenv("COST_PRICES", '{"livekit_agent_per_min_usd": 0.01, "livekit_sip_per_min_usd": 0.004, "server_per_min_inr": 0.2}')
    assert one_minute(CallCost("browser")).summary()["inr"]["livekit"] == round(0.01 * 93 + 0.2, 3)
    assert one_minute(CallCost("phone")).summary()["inr"]["livekit"] == round(0.014 * 93 + 0.2, 3)


def test_cached_input_tokens_are_billed_at_the_cached_rate():
    meter = one_minute(CallCost("browser"))
    meter.add_llm_usage(
        "openai/gpt-oss-120b",
        {"input_tokens": 10_000, "output_tokens": 0, "input_token_details": {"cache_read": 8_000}},
    )
    assert meter.llm["openai/gpt-oss-120b"] == {"calls": 1, "input": 2_000, "cached": 8_000, "output": 0}
    assert meter.summary()["inr"]["llm"] == round((2_000 * 0.15 + 8_000 * 0.075) / 1e6 * 93, 3)


def test_prices_can_be_changed_without_a_deploy(monkeypatch):
    monkeypatch.setenv("COST_PRICES", '{"usd_inr": 100, "livekit_agent_per_min_usd": 0}')
    meter = one_minute(CallCost("browser"))
    meter.add_llm("openai/gpt-oss-120b", 1_000_000, 0)
    assert meter.summary()["inr"] == {"stt": 0.0, "tts": 0.0, "llm": 15.0, "livekit": 0.0}


def test_a_bad_override_falls_back_to_the_defaults(monkeypatch):
    monkeypatch.setenv("COST_PRICES", "not json")
    assert costs.prices()["usd_inr"] == costs.PRICES["usd_inr"]


def test_a_model_without_a_price_is_counted_and_flagged():
    meter = one_minute(CallCost("browser", "groq"))
    meter.add_tts("canopylabs/orpheus-v1-english", 500)
    report = meter.summary()
    assert report["unpriced"] == ["tts:canopylabs/orpheus-v1-english"]
    assert report["usage"]["tts_chars"] == {"canopylabs/orpheus-v1-english": 500}


def test_stt_is_counted_from_livekit_metrics():
    class Meta:
        model_name = None

    class STTMetrics:  # the shape of LiveKit's metrics event payload
        metadata = Meta()
        audio_duration = 12.5

    class TTSMetrics:
        characters_count = 999

    meter = CallCost("phone", "sarvam", stt_model="saaras:v3")
    meter.on_livekit_metrics(STTMetrics())
    meter.on_livekit_metrics(TTSMetrics())  # speech is counted where it's generated, not from metrics
    assert meter.stt_seconds == {"saaras:v3": 12.5} and meter.tts_chars == {}


def test_the_agent_counts_each_groq_reply():
    class Reply:
        usage_metadata = {"input_tokens": 3_000, "output_tokens": 150}

    agent = RestaurantOrderingAgent.__new__(RestaurantOrderingAgent)
    agent.model_name = "openai/gpt-oss-120b"
    agent._meter(Reply())  # no meter yet: nothing happens
    agent.cost_meter = CallCost("browser")
    agent._meter(Reply())
    agent._meter(Reply())
    assert agent.cost_meter.llm["openai/gpt-oss-120b"] == {"calls": 2, "input": 6_000, "cached": 0, "output": 300}


def test_speech_is_billed_only_when_it_is_really_generated(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    from app.voice import livekit_tts

    meter = CallCost("browser", "sarvam")
    tts = livekit_tts.SarthiTTS(persona="waiter", language="hi", sarvam_only=True, meter=meter)
    key = livekit_tts._cache_key("ठीक है।", "waiter", "hi", True, None)
    tts._count("ठीक है।", key)
    livekit_tts._PHRASE_CACHE[key] = b"audio"
    try:
        tts._count("ठीक है।", key)  # cached now: free
    finally:
        livekit_tts._PHRASE_CACHE.pop(key, None)
    assert meter.tts_chars == {"bulbul:v4-flash": len("ठीक है।")}


def test_english_on_the_groq_stack_is_billed_to_orpheus(monkeypatch):
    monkeypatch.setenv("SARTHI_SPEECH", "groq")
    from app.voice import livekit_tts

    assert livekit_tts.speech_model("Your order is placed.", "en", False) == "canopylabs/orpheus-v1-english"
    assert livekit_tts.speech_model("आपका ऑर्डर", "hi", False) == "bulbul:v4-flash"
    assert livekit_tts.speech_model("Your order is placed.", "en", True) == "bulbul:v4-flash"


def test_a_phone_call_saves_its_cost_with_its_log(monkeypatch):
    saved = {}
    monkeypatch.setattr(repository, "update_call", lambda call_id, **fields: saved.update(fields))
    call = PhoneCall.__new__(PhoneCall)
    call.closed, call.call_id, call.turns, call.metrics = False, "call-1", [], [{"role": "user"}]
    call.order = type("Order", (), {"order_id": "o1", "callback_reason": None})()
    call.cost = {"type": "cost", "total_inr": 3.1}
    call.close()
    assert saved["metrics"] == [{"role": "user"}, {"type": "cost", "total_inr": 3.1}]
    assert saved["outcome"] == "ordered"

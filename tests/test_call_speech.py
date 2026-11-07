"""What a live call depends on: the agent runs once per turn, a rate limit fails fast, and speech is Sarvam."""
import asyncio
import base64
import logging
import time
from types import SimpleNamespace

import groq
import httpx
import pytest

from app.agent import graph
from app.agent.graph import RestaurantOrderingAgent
from tests.test_agent_guardrails import Store


def _rate_limited_client(retry_after: str) -> tuple[groq.Groq, list[int]]:
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        return httpx.Response(429, headers={"retry-after": retry_after}, json={"error": {"message": "slow down"}})

    client = httpx.Client(
        transport=httpx.MockTransport(respond),
        event_hooks={"response": [graph._log_rate_limit, graph._no_long_retry_wait]},
    )
    return groq.Groq(api_key="test", max_retries=1, http_client=client), seen


def _ask(client: groq.Groq) -> None:
    client.chat.completions.create(model="m", messages=[{"role": "user", "content": "hi"}])


def test_a_long_rate_limit_wait_fails_at_once_and_is_logged(caplog):
    client, seen = _rate_limited_client("30")
    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="sarthi.agent"), pytest.raises(groq.RateLimitError):
        _ask(client)
    assert time.monotonic() - started < 2 and len(seen) == 1
    assert "429" in caplog.text and "retry-after=30" in caplog.text


def test_a_short_rate_limit_wait_still_gets_its_retry():
    client, seen = _rate_limited_client("0.01")
    with pytest.raises(groq.RateLimitError):
        _ask(client)
    assert len(seen) == 2


@pytest.mark.parametrize(
    ("live_call", "timeout", "retries", "effort"), [(True, 10.0, 1, "low"), (False, 30.0, 3, None)]
)
def test_only_live_calls_get_the_fast_settings(monkeypatch, live_call, timeout, retries, effort):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    agent = RestaurantOrderingAgent("s", Store(), persona="waiter", live_call=live_call)
    llm = agent.llm_with_tools.bound
    assert (llm.request_timeout, llm.max_retries, llm.reasoning_effort) == (timeout, retries, effort)


def _voice_modules(monkeypatch):
    pytest.importorskip("livekit.agents")
    pytest.importorskip("livekit.plugins.sarvam")
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    from app.voice import livekit_llm, livekit_phone

    return livekit_llm, livekit_phone


class FakeAgent:
    language = "hi"
    agent_name = "Kabir"
    cart: list = []
    service_log: list = []

    def __init__(self, fails: bool = False):
        self.sent = []
        self.fails = fails

    def send(self, text: str) -> str:
        self.sent.append(text)
        if self.fails:
            raise TimeoutError
        return "ठीक है।"


def test_a_split_sentence_does_not_run_the_agent_before_the_turn_is_over(monkeypatch):
    # Noise or a pause makes speech-to-text finish part of a sentence. By LiveKit's default the agent
    # would run on that part, then again on the whole, adding the first item to the cart twice.
    livekit_llm, livekit_phone = _voice_modules(monkeypatch)
    from livekit.agents import Agent, AgentSession
    from livekit.agents.voice.audio_recognition import _PreemptiveGenerationInfo as Info

    async def run() -> FakeAgent:
        fake = FakeAgent()
        llm = livekit_llm.SarthiLLM(fake, session_id="s", persona="waiter")
        async with AgentSession(llm=llm, turn_handling=livekit_phone.TURN_HANDLING) as session:
            await session.start(Agent(instructions="x"))
            session._activity.on_preemptive_generation(Info("दो नान", 1.0, time.time()))
            await asyncio.sleep(0.1)
        return fake

    assert asyncio.run(run()).sent == []


def test_a_failed_turn_on_a_call_still_says_something(monkeypatch):
    livekit_llm, _ = _voice_modules(monkeypatch)
    from livekit.agents.llm import ChatContext

    from app.agent import language as lang

    async def run() -> str:
        ctx = ChatContext.empty()
        ctx.add_message(role="user", content="दो नान दीजिए और एक दाल")
        llm = livekit_llm.SarthiLLM(FakeAgent(fails=True), session_id="s", persona="waiter")
        return "".join([chunk.delta.content async for chunk in llm.chat(chat_ctx=ctx)])

    assert asyncio.run(run()).endswith(lang.line("hi", "default"))


class FakeRoomCtx:
    def __init__(self):
        self.deleted = self.shut_down = False

    async def delete_room(self):
        self.deleted = True

    def shutdown(self, reason=""):
        self.shut_down = True


def test_a_real_session_hangs_up_after_the_goodbye_is_spoken(monkeypatch):
    livekit_llm, livekit_phone = _voice_modules(monkeypatch)
    from livekit.agents import Agent, AgentSession

    monkeypatch.setattr(livekit_phone, "HANG_UP_PAUSE", 0)

    class DoneAgent(FakeAgent):
        def conversation_over(self, user_text, reply):
            return True

    async def run() -> FakeRoomCtx:
        ctx = FakeRoomCtx()
        llm = livekit_llm.SarthiLLM(
            DoneAgent(), session_id="s", persona="waiter",
            on_goodbye=lambda: livekit_phone.hang_up_after_goodbye(ctx, session),
        )
        async with AgentSession(llm=llm, turn_handling=livekit_phone.TURN_HANDLING) as session:
            await session.start(Agent(instructions="x"))
            await session.run(user_input="thank you")
            await asyncio.sleep(0.1)
        return ctx

    ctx = asyncio.run(run())
    assert ctx.deleted and ctx.shut_down


def test_talking_over_the_goodbye_keeps_the_call_open(monkeypatch):
    _, livekit_phone = _voice_modules(monkeypatch)
    monkeypatch.setattr(livekit_phone, "HANG_UP_PAUSE", 0)

    async def run(interrupted: bool) -> FakeRoomCtx:
        ctx = FakeRoomCtx()
        callbacks = []
        speech = SimpleNamespace(add_done_callback=callbacks.append)
        livekit_phone.hang_up_after_goodbye(ctx, SimpleNamespace(current_speech=speech))
        assert not ctx.deleted  # never before the goodbye has been said
        callbacks[0](SimpleNamespace(interrupted=interrupted))
        await asyncio.sleep(0.01)
        return ctx

    assert not asyncio.run(run(True)).deleted
    assert asyncio.run(run(False)).deleted


def test_calls_filter_out_background_voices(monkeypatch):
    _, livekit_phone = _voice_modules(monkeypatch)
    from livekit.plugins import noise_cancellation

    browser = livekit_phone.room_options(telephony=False).audio_input.noise_cancellation
    phone = livekit_phone.room_options(telephony=True).audio_input.noise_cancellation
    assert browser == noise_cancellation.BVC() and phone == noise_cancellation.BVCTelephony()
    assert livekit_phone.TURN_HANDLING["interruption"]["mode"] == "adaptive"  # chatter doesn't cut the agent off


def test_turn_timings_are_read_from_a_conversation_item(monkeypatch):
    _, livekit_phone = _voice_modules(monkeypatch)
    item = SimpleNamespace(role="user", metrics={"transcription_delay": 0.25, "started_speaking_at": 5.0})
    assert livekit_phone._timings(item) == {"role": "user", "transcription_delay": 250}


def test_push_to_talk_hears_through_sarvam(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    from app.voice import stt

    calls = {}

    def transcribe(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(transcript=" दो नान ")

    monkeypatch.setattr(stt._client.speech_to_text, "transcribe", transcribe)
    assert stt.transcribe_bytes(b"audio", filename="clip.webm") == "दो नान"
    assert calls["file"] == ("clip.webm", b"audio")
    assert (calls["model"], calls["mode"], calls["language_code"]) == ("saaras:v3", "codemix", "unknown")


def test_push_to_talk_speaks_through_sarvam(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    from fastapi.testclient import TestClient

    from app import main

    guest = SimpleNamespace(persona="waiter", language="en", cart=[], service_log=[])
    monkeypatch.setattr(main, "get_or_create_session", lambda *a: guest)
    monkeypatch.setattr(main, "send_or_busy", lambda agent, text: "Sure.")
    monkeypatch.setattr(main, "transcribe_bytes", lambda data, filename: "one naan")
    monkeypatch.setattr(main, "synthesize_sarvam", lambda text, persona: b"wav:" + text.encode())

    response = TestClient(main.app).post(
        "/chat/voice", params={"session_id": "s", "persona": "waiter"}, files={"audio": ("a.webm", b"x")}
    )
    assert response.status_code == 200
    assert base64.b64decode(response.json()["reply_audio_wav_base64"]) == b"wav:Sure."

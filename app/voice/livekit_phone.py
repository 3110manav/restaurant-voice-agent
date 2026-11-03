"""A phone call inside the LiveKit worker. Exotel forwards the call to LiveKit over SIP, a dispatch rule
(deploy/sip/) puts it in a room named "call-...", and the worker comes here.

The caller is a SIP participant whose attributes say who called and which number they dialled, and the
dialled number picks the store. Speech is all Sarvam: Saaras hears code-mixed Hindi and English (and
detects which), and Bulbul speaks both. What happens in the call lives in app/phone/call.py.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

from livekit import rtc
from livekit.agents import Agent, AgentSession, JobContext
from livekit.agents.llm import LLM, ChatChunk, ChatContext, ChoiceDelta, LLMStream
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.agents.utils import shortuuid
from livekit.plugins import sarvam, silero

from app.agent import language as lang
from app.phone.call import PhoneCall, open_call
from app.voice.livekit_llm import _last_user_text
from app.voice.livekit_tts import build_speech, warm_phrases

logger = logging.getLogger("sarthi.livekit_phone")

ROOM_PREFIX = "call-"
ATTR_CALLER = "sip.phoneNumber"
ATTR_DIALLED = "sip.trunkPhoneNumber"
# saaras:v4 is the plugin's default; v3 is what we've priced, so moving is a deliberate test.
STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v3")
# LiveKit's default runs the LLM as soon as a transcript arrives, and again if the speaker carries on.
# Our "LLM" is the agent, whose tools really change the cart, so it must only run when the turn is over.
TURN_HANDLING = {"preemptive_generation": {"enabled": False}}
HANG_UP_PAUSE = 1.0  # seconds after the goodbye, so its last words reach the guest's speaker
_pending: set[asyncio.Task] = set()  # keeps a hang-up from being garbage collected before it runs


def build_stt() -> sarvam.STT:
    """Speech-to-text for every call, phone or browser: Saaras hears Hindi, English and a mix of both."""
    return sarvam.STT(language="unknown", model=STT_MODEL, mode="codemix")


def is_phone_room(room_name: str) -> bool:
    return room_name.startswith(ROOM_PREFIX)


class PhoneLLM(LLM):
    def __init__(self, call: PhoneCall, on_goodbye: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.call = call
        self.on_goodbye = on_goodbye
        self.acks = 0

    @property
    def model(self) -> str:
        return self.call.agent.agent_name

    @property
    def provider(self) -> str:
        return "sarthi"

    def chat(self, *, chat_ctx: ChatContext, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **_) -> PhoneLLMStream:
        return PhoneLLMStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class PhoneLLMStream(LLMStream):
    async def _run(self) -> None:
        text = _last_user_text(self._chat_ctx)
        if not text:
            return
        llm: PhoneLLM = self._llm  # type: ignore[assignment]
        agent = llm.call.agent
        # Say "ठीक है।" straight away (its audio is cached) while the model works on the real answer.
        ack = lang.pick_ack(text, lang.caller_language(text, agent.language), llm.acks)
        if ack:
            llm.acks += 1
            self._event_ch.send_nowait(ChatChunk(id=shortuuid(), delta=ChoiceDelta(role="assistant", content=f"{ack} ")))
        reply = await asyncio.get_running_loop().run_in_executor(None, llm.call.take_turn, text)
        self._event_ch.send_nowait(ChatChunk(id=shortuuid(), delta=ChoiceDelta(role="assistant", content=reply)))
        if llm.on_goodbye and agent.conversation_over(text, reply):
            llm.on_goodbye()


def hang_up_after_goodbye(ctx: JobContext, session: AgentSession) -> None:
    """Ends the call once the goodbye being spoken has finished, so nobody pays for an open line.
    If the guest talks over it they weren't done, so the call carries on."""
    speech = session.current_speech

    async def _hang_up() -> None:
        await asyncio.sleep(HANG_UP_PAUSE)
        logger.info("the conversation is over; hanging up")
        await ctx.delete_room()
        ctx.shutdown("goodbye")

    def _on_spoken(handle) -> None:
        if not handle.interrupted:
            _pending.add(task := asyncio.create_task(_hang_up()))
            task.add_done_callback(_pending.discard)

    if speech is None:
        logger.warning("no speech to wait for, so the call stays open")
        return
    speech.add_done_callback(_on_spoken)


def _timings(item) -> dict | None:
    """How long each stage took for one thing said, in milliseconds, for the test view."""
    report = getattr(item, "metrics", None) or {}
    stages = {
        key: round(report[key] * 1000)
        for key in ("transcription_delay", "end_of_turn_delay", "llm_node_ttft", "tts_node_ttfb", "e2e_latency")
        if key in report
    }
    return {"role": item.role, **stages} if stages else None


async def phone_entrypoint(ctx: JobContext) -> None:
    participant = await ctx.wait_for_participant(kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
    caller, dialled = participant.attributes.get(ATTR_CALLER), participant.attributes.get(ATTR_DIALLED)
    loop = asyncio.get_running_loop()

    try:
        call = await loop.run_in_executor(None, open_call, ctx.room.name, dialled, caller)
    except Exception:
        logger.exception("couldn't start the call")
        call = None
    if call is None:
        ctx.delete_room()  # hanging up beats silence: the caller can ring the store directly
        return

    session = AgentSession(
        stt=build_stt(),
        llm=PhoneLLM(call, on_goodbye=lambda: hang_up_after_goodbye(ctx, session)),
        # language=None: Hindi or English is read from each sentence's script, since a call can switch.
        tts=build_speech(call.persona, None, sarvam_only=True),
        vad=silero.VAD.load(),
        turn_handling=TURN_HANDLING,
    )

    @session.on("conversation_item_added")
    def _on_item(event) -> None:
        timings = _timings(event.item)
        if timings:
            call.add_metric(timings)

    async def _finish(_reason: str = "") -> None:
        await loop.run_in_executor(None, call.close)

    ctx.add_shutdown_callback(_finish)

    await session.start(Agent(instructions=call.agent.system_prompt), room=ctx.room)
    loop.run_in_executor(None, warm_phrases, call.persona, None, [*lang.all_acks("hi"), *lang.all_acks("en")], True)
    session.say(call.greeting, allow_interruptions=True)

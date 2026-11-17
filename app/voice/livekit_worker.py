"""LiveKit Agents worker: the realtime, interruptible voice layer for
Sarthi, running alongside (not instead of) the FastAPI backend and its
push-to-talk `/chat/voice` endpoint.

Run as its own long-lived process, separate from `uvicorn app.main:app`:

    python -m app.voice.livekit_worker dev     # connects to LiveKit Cloud for local dev
    python -m app.voice.livekit_worker start   # production

Needs LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in the environment
(see README's "Realtime voice (LiveKit)" section).

Routing: whatever creates the room names it "sarthi__{persona}__{session_id}"
(see _parse_room_name) so this worker knows which persona and which
session's cart/history to resume — reusing the exact same
RestaurantOrderingAgent, tools, and catalogs as the text and push-to-talk
paths via SarthiLLM (app/voice/livekit_llm.py). Silero VAD plus LiveKit's
own turn detection give barge-in (interrupting the agent mid-sentence) for
free, and background voice cancellation keeps other tables' voices out (see
room_options in app/voice/livekit_phone.py). Who hears and speaks follows SARTHI_SPEECH (app/voice/stack.py):
Groq's Whisper and Orpheus, or Sarvam's Saaras and Bulbul, through SarthiTTS (app/voice/livekit_tts.py). The LLM
is Groq either way.

Known limitation: this worker is a separate OS process from the FastAPI
app, so a realtime voice session keeps its own fresh in-memory cart rather
than reading the main API's. After every turn it pushes that cart to the
main API over HTTP (app/voice/cart_sync.py, via SarthiLLM) under the same
(session_id, persona) key the web app polls with GET /cart, so the UI
catches up one turn later — but a *simultaneous* text/push-to-talk session
for the same customer can still race with it (last write wins). Fully
unifying that needs session/cart state to move into Supabase (or another
shared store), same as the README's MemorySaver caveat.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging

from dotenv import load_dotenv

load_dotenv()

from livekit import agents  # noqa: E402
from livekit.agents import Agent, AgentServer, AgentSession, JobContext  # noqa: E402
from livekit.plugins import silero  # noqa: E402

from app.agent import language as lang  # noqa: E402
from app.agent.graph import ENABLED_PERSONAS, RestaurantOrderingAgent, persona_for  # noqa: E402
from app.customers.session import start_session  # noqa: E402
from app.menu.snapshot import LiveMenu, menu_cache  # noqa: E402
from app.voice.livekit_llm import SarthiLLM  # noqa: E402
from app.voice.livekit_phone import (  # noqa: E402
    TURN_HANDLING,
    _timings,
    hang_up_after_goodbye,
    is_phone_room,
    phone_entrypoint,
    room_options,
)
from app.voice.livekit_rooms import parse_room_name  # noqa: E402
from app.voice.livekit_tokens import AGENT_NAME  # noqa: E402
from app.voice.livekit_stack import build_stt, build_tts, warm  # noqa: E402
from app.voice.stack import speech_stack  # noqa: E402

logger = logging.getLogger("sarthi.livekit_worker")
logger.info("speech stack: %s", speech_stack())  # also rejects a mistyped SARTHI_SPEECH before any call

@functools.cache
def _menu_store_for(persona: str):
    """Kirana calls (and the waiter without a restaurant) read a local Chroma index, loaded on first
    use. Restaurant calls read their menus from Supabase and never touch it. Returns None when Chroma
    isn't installed, so the worker declines the call instead of crashing."""
    try:
        from app.rag.menu_store import store_for_persona
    except ImportError:
        return None
    return store_for_persona(persona)


def _log_turn_metrics(event) -> None:
    """One short line per stage of every turn, so a real call shows where its time goes:
    eou = the pause LiveKit waits to be sure the caller finished (plus the speech-to-text upload),
    llm = time until the agent's reply is ready, tts = time until the first audio of a sentence exists."""
    m = event.metrics
    kind = type(m).__name__
    if kind == "EOUMetrics":
        logger.info("latency eou_delay=%.2fs transcription_delay=%.2fs", m.end_of_utterance_delay, m.transcription_delay)
    elif kind == "LLMMetrics":
        logger.info("latency llm_ttft=%.2fs", m.ttft)
    elif kind == "TTSMetrics":
        logger.info("latency tts_ttfb=%.2fs audio=%.1fs", m.ttfb, m.audio_duration)
    elif kind == "STTMetrics":
        logger.info("latency stt_audio=%.1fs", m.audio_duration)


def _caller_phone(ctx: JobContext, meta: dict) -> tuple[str | None, bool]:
    """(number, verified). A real phone call carries its caller ID as a SIP attribute: verified. A number in the
    dispatch metadata came from the web page the call was started on: not verified (see start_session)."""
    for participant in ctx.room.remote_participants.values():
        number = (participant.attributes or {}).get("sip.phoneNumber")
        if number:
            return number, True
    return meta.get("phone"), False


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    if is_phone_room(ctx.room.name):
        await phone_entrypoint(ctx)
        return

    persona, session_id = parse_room_name(ctx.room.name)
    # The web app tells us which restaurant (and table) this call is for through the
    # dispatch metadata; without it this is a kirana (or standalone waiter) call.
    meta = json.loads(ctx.job.metadata or "{}")
    restaurant_slug, table_no = meta.get("restaurant"), meta.get("table_no")
    language = lang.normalize(meta.get("language"))
    speech = meta.get("speech")  # "groq" or "sarvam", settled by the API; absent means this worker's SARTHI_SPEECH
    logger.info(
        "starting realtime session: persona=%s session_id=%s restaurant=%s speech=%s",
        persona, session_id, restaurant_slug, speech or speech_stack(),
    )

    if restaurant_slug:
        menu = menu_cache.get(restaurant_slug)
        if menu is None:
            logger.error("restaurant %r not found; ending call", restaurant_slug)
            return
        persona = persona_for(menu.restaurant)
        # Who is calling: the web demo passes a number in the metadata; a real phone call carries the
        # caller ID as a SIP attribute on the caller's participant.
        caller, verified = _caller_phone(ctx, meta)
        agent = RestaurantOrderingAgent(
            session_id=f"livekit:{restaurant_slug}:{session_id}",
            menu_store=LiveMenu(restaurant_slug),
            persona=persona,
            restaurant=menu.restaurant,
            table_no=table_no,
            live_call=True,
            customer=start_session(menu.restaurant, caller, table_no, language, verified=verified),
        )
        agent.channel = "voice"
        agent.set_language(language)
        greeting = agent.opening_line(menu.restaurant["name"])
    else:
        if persona not in ENABLED_PERSONAS:
            logger.error("persona %r is not enabled; ending call", persona)
            return
        store = _menu_store_for(persona)
        if store is None:
            logger.error("persona %r needs the local menu index, which this worker doesn't have; ending call", persona)
            return
        agent = RestaurantOrderingAgent(session_id=f"livekit:{session_id}", menu_store=store, persona=persona, live_call=True)
        greeting = lang.greeting(language, agent.agent_name)

    agent.set_language(language)
    agent.speech_label = speech or speech_stack()  # shown against this call's turns in the owner's transcript

    session = AgentSession(
        stt=build_stt(language, speech),
        llm=SarthiLLM(
            agent, session_id=session_id, persona=persona, restaurant=restaurant_slug, table_no=table_no,
            on_goodbye=lambda: hang_up_after_goodbye(ctx, session), speech=speech,
        ),
        tts=build_tts(persona, language, speech=speech),
        vad=silero.VAD.load(),
        turn_handling=TURN_HANDLING,
    )

    session.on("metrics_collected", _log_turn_metrics)

    @session.on("conversation_item_added")
    def _on_item(event) -> None:
        timings = _timings(event.item)
        if timings:
            logger.info("turn timings in ms: %s", timings)

    await session.start(Agent(instructions=agent.system_prompt), room=ctx.room, room_options=room_options(telephony=False))
    # Pre-generate the acknowledgement phrases in the background so they play instantly.
    asyncio.get_running_loop().run_in_executor(None, warm, persona, language, lang.all_acks(language), None, speech)
    session.say(greeting, allow_interruptions=True)


if __name__ == "__main__":
    agents.cli.run_app(server)

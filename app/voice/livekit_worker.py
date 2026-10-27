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
free; Groq's Whisper handles STT, the same model the push-to-talk path uses.
TTS is SarthiTTS (app/voice/livekit_tts.py), wrapping the existing
English/Hindi routing rather than a second TTS integration.

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
import json
import logging

from dotenv import load_dotenv

load_dotenv()

from livekit import agents  # noqa: E402
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, tokenize  # noqa: E402
from livekit.agents import tts as lk_tts  # noqa: E402
from livekit.plugins import groq, silero  # noqa: E402

from app.agent import language as lang  # noqa: E402
from app.agent.graph import RestaurantOrderingAgent  # noqa: E402
from app.menu.snapshot import LiveMenu, menu_cache  # noqa: E402
from app.rag.menu_store import GROCERY_PATH, MenuStore  # noqa: E402
from app.voice.livekit_llm import SarthiLLM  # noqa: E402
from app.voice.livekit_rooms import parse_room_name  # noqa: E402
from app.voice.livekit_tts import SarthiTTS, warm_phrases  # noqa: E402

logger = logging.getLogger("sarthi.livekit_worker")

# Built once per worker process, same two catalogs as app/main.py, reused
# across every realtime session this process handles.
_food_menu_store = MenuStore()
_grocery_store = MenuStore(data_path=GROCERY_PATH, collection_name="grocery_catalog")


def _menu_store_for(persona: str) -> MenuStore:
    return _grocery_store if persona == "quick_commerce" else _food_menu_store


server = AgentServer()


@server.rtc_session(agent_name="sarthi-voice")
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    persona, session_id = parse_room_name(ctx.room.name)
    # The web app tells us which restaurant (and table) this call is for through the
    # dispatch metadata; without it this is a legacy four-persona call.
    meta = json.loads(ctx.job.metadata or "{}")
    restaurant_slug, table_no = meta.get("restaurant"), meta.get("table_no")
    language = lang.normalize(meta.get("language"))
    logger.info(
        "starting realtime session: persona=%s session_id=%s restaurant=%s", persona, session_id, restaurant_slug
    )

    if restaurant_slug:
        menu = menu_cache.get(restaurant_slug)
        if menu is None:
            logger.error("restaurant %r not found; ending call", restaurant_slug)
            return
        persona = "waiter"
        agent = RestaurantOrderingAgent(
            session_id=f"livekit:{restaurant_slug}:{session_id}",
            menu_store=LiveMenu(restaurant_slug),
            persona=persona,
            restaurant=menu.restaurant,
            table_no=table_no,
        )
        greeting = lang.greeting(language, agent.agent_name, menu.restaurant["name"])
    else:
        agent = RestaurantOrderingAgent(
            session_id=f"livekit:{session_id}", menu_store=_menu_store_for(persona), persona=persona
        )
        greeting = lang.greeting(language, agent.agent_name)

    agent.set_language(language)

    # Speak each sentence as soon as it is ready instead of waiting for a minimum length: this is what
    # lets the quick "Sure." play while the real answer is still being worked out (LiveKit's default
    # holds any sentence under 20 characters until the next one arrives).
    speech = lk_tts.StreamAdapter(
        tts=speech,
        sentence_tokenizer=tokenize.blingfire.SentenceTokenizer(
            min_sentence_len=1, stream_context_len=0, retain_format=True
        ),
    )

    session = AgentSession(
        stt=groq.STT(model="whisper-large-v3-turbo", language=language),
        llm=SarthiLLM(agent, session_id=session_id, persona=persona, restaurant=restaurant_slug, table_no=table_no),
        tts=speech,
        vad=silero.VAD.load(),
    )

    await session.start(Agent(instructions=agent.system_prompt), room=ctx.room)
    # Pre-generate the acknowledgement phrases in the background so they play instantly.
    asyncio.get_running_loop().run_in_executor(None, warm_phrases, persona, language, lang.all_acks(language))
    session.say(greeting, allow_interruptions=True)


if __name__ == "__main__":
    agents.cli.run_app(server)

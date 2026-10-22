"""API for both personas: text and voice in, text + spoken out.

POST /chat        {"session_id", "message", "persona"} -> reply + cart + service_log
POST /chat/voice   multipart: audio file + session_id + persona -> transcript,
                   reply, cart, service_log, and base64 WAV audio (English via
                   Orpheus/Groq, Hindi via Sarvam AI's Bulbul)
GET  /menu?persona -> the catalog for that persona (food menu, or the
                   separate grocery catalog for quick_commerce), for
                   browsing UIs (product grids)
POST /cart/add     {"session_id", "persona", "item_id", "quantity"} -> cart
POST /cart/remove  {"session_id", "persona", "item_id", "quantity"} -> cart
                   Direct cart mutation for UI actions like tapping "Add" on a
                   product card — deliberately bypasses the LLM: there's
                   nothing to interpret, so there's no reason to spend a Groq
                   call (or the latency) on it. The agent's own add_to_cart /
                   remove_from_cart tools still handle it when the customer
                   asks by voice or text instead of clicking.
GET  /cart         ?session_id&persona -> cart + service_log for that session,
                   for the web app to poll while a realtime voice call is
                   active (that agent instance lives in the separate LiveKit
                   worker process, not here — see /cart/sync below).
POST /cart/sync    {"session_id", "persona", "cart", "service_log"} -> cart.
                   Called by the LiveKit worker process after every realtime
                   voice turn to mirror its own in-memory cart into this
                   process's session, under the same (session_id, persona)
                   key the text/push-to-talk paths use — see
                   app/voice/cart_sync.py.
GET  /admin/orders, GET /admin/requests -> recent rows for the staff-facing
                   view (web/'s /admin page). Empty with configured=false
                   when Supabase isn't set up — see app/erp.py.
POST /admin/requests/{id}/resolve -> marks one request resolved.
POST /livekit/token -> {"session_id", "persona"} -> a room/token for the web
                   app's realtime "Start call" button, dispatching the
                   sarthi-voice worker into that room. configured=false with
                   no token when LiveKit isn't set up — see
                   app/voice/livekit_tokens.py.

Serves the frontend (app/static/) at "/".
"""
import base64

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

from pathlib import Path  # noqa: E402

from app import erp  # noqa: E402
from app.agent.graph import RestaurantOrderingAgent  # noqa: E402
from app.agent.tools import add_item_to_cart, remove_item_from_cart_by_id  # noqa: E402
from app.rag.menu_store import GROCERY_PATH, MenuStore  # noqa: E402
from app.voice import livekit_tokens  # noqa: E402
from app.voice.stt import transcribe_bytes  # noqa: E402
from app.voice.tts import synthesize  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Voice Ordering Agent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Two catalogs: the food menu (online/waiter/hotel room-service) and a
# separate grocery catalog for quick_commerce (shampoo, batteries, snacks,
# etc.) — see app/rag/menu_store.py for why they're kept as two collections.
food_menu_store = MenuStore()
grocery_store = MenuStore(data_path=GROCERY_PATH, collection_name="grocery_catalog")
sessions: dict[str, RestaurantOrderingAgent] = {}


def get_menu_store(persona: str) -> MenuStore:
    return grocery_store if persona == "quick_commerce" else food_menu_store


class ChatRequest(BaseModel):
    session_id: str
    message: str
    persona: str = "online"


class ChatResponse(BaseModel):
    reply: str
    cart: list[dict]
    service_log: list[dict]


class VoiceChatResponse(BaseModel):
    transcript: str
    reply: str
    cart: list[dict]
    service_log: list[dict]
    reply_audio_wav_base64: str | None = None


class MenuResponse(BaseModel):
    items: list[dict]


class CartMutationRequest(BaseModel):
    session_id: str
    persona: str = "online"
    item_id: str
    quantity: int = 1


class CartResponse(BaseModel):
    cart: list[dict]
    message: str


class SessionStateResponse(BaseModel):
    cart: list[dict]
    service_log: list[dict]


class CartSyncRequest(BaseModel):
    session_id: str
    persona: str = "online"
    cart: list[dict]
    service_log: list[dict] = []


class AdminOrdersResponse(BaseModel):
    configured: bool
    orders: list[dict]


class AdminRequestsResponse(BaseModel):
    configured: bool
    requests: list[dict]


class LiveKitTokenRequest(BaseModel):
    session_id: str
    persona: str = "online"


class LiveKitTokenResponse(BaseModel):
    configured: bool
    url: str | None = None
    token: str | None = None
    room: str | None = None


def get_or_create_session(session_id: str, persona: str) -> RestaurantOrderingAgent:
    key = f"{session_id}:{persona}"
    if key not in sessions:
        sessions[key] = RestaurantOrderingAgent(
            session_id=key, menu_store=get_menu_store(persona), persona=persona
        )
    return sessions[key]


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    agent = get_or_create_session(req.session_id, req.persona)
    reply = agent.send(req.message)
    return ChatResponse(reply=reply, cart=agent.cart, service_log=agent.service_log)


@app.post("/chat/voice", response_model=VoiceChatResponse)
async def chat_voice(session_id: str, persona: str, audio: UploadFile) -> VoiceChatResponse:
    agent = get_or_create_session(session_id, persona)

    audio_bytes = await audio.read()
    transcript = transcribe_bytes(audio_bytes, filename=audio.filename or "audio.webm")

    if not transcript:
        return VoiceChatResponse(transcript="", reply="", cart=agent.cart, service_log=agent.service_log)

    reply = agent.send(transcript)

    try:
        reply_audio_b64 = base64.b64encode(synthesize(reply, persona)).decode("ascii")
    except Exception:
        reply_audio_b64 = None  # TTS unavailable/blocked — client falls back to text only

    return VoiceChatResponse(
        transcript=transcript,
        reply=reply,
        cart=agent.cart,
        service_log=agent.service_log,
        reply_audio_wav_base64=reply_audio_b64,
    )


@app.get("/menu", response_model=MenuResponse)
def get_menu(persona: str = "online") -> MenuResponse:
    return MenuResponse(items=get_menu_store(persona).menu)


@app.post("/cart/add", response_model=CartResponse)
def cart_add(req: CartMutationRequest) -> CartResponse:
    agent = get_or_create_session(req.session_id, req.persona)
    item = get_menu_store(req.persona).get(req.item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"No menu item with id '{req.item_id}'")
    message = add_item_to_cart(agent.cart, item, req.quantity)
    return CartResponse(cart=agent.cart, message=message)


@app.post("/cart/remove", response_model=CartResponse)
def cart_remove(req: CartMutationRequest) -> CartResponse:
    agent = get_or_create_session(req.session_id, req.persona)
    message = remove_item_from_cart_by_id(agent.cart, req.item_id, req.quantity)
    return CartResponse(cart=agent.cart, message=message)


@app.get("/cart", response_model=SessionStateResponse)
def get_cart(session_id: str, persona: str = "online") -> SessionStateResponse:
    agent = get_or_create_session(session_id, persona)
    return SessionStateResponse(cart=agent.cart, service_log=agent.service_log)


@app.post("/cart/sync", response_model=SessionStateResponse)
def cart_sync(req: CartSyncRequest) -> SessionStateResponse:
    agent = get_or_create_session(req.session_id, req.persona)
    agent.cart[:] = req.cart
    agent.service_log[:] = req.service_log
    return SessionStateResponse(cart=agent.cart, service_log=agent.service_log)


@app.get("/admin/orders", response_model=AdminOrdersResponse)
def admin_orders() -> AdminOrdersResponse:
    return AdminOrdersResponse(configured=erp.is_configured(), orders=erp.list_orders())


@app.get("/admin/requests", response_model=AdminRequestsResponse)
def admin_requests() -> AdminRequestsResponse:
    return AdminRequestsResponse(configured=erp.is_configured(), requests=erp.list_requests())


@app.post("/admin/requests/{request_id}/resolve")
def admin_resolve_request(request_id: str) -> dict:
    updated = erp.resolve_request(request_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Request not found, or Supabase isn't configured")
    return updated


@app.post("/livekit/token", response_model=LiveKitTokenResponse)
async def livekit_token(req: LiveKitTokenRequest) -> LiveKitTokenResponse:
    if not livekit_tokens.is_configured():
        return LiveKitTokenResponse(configured=False)

    room = livekit_tokens.room_name_for(req.persona, req.session_id)
    await livekit_tokens.ensure_dispatch(room)
    identity = f"customer-{req.session_id[:8]}"
    token = livekit_tokens.mint_token(identity, room)
    return LiveKitTokenResponse(configured=True, url=livekit_tokens.LIVEKIT_URL, token=token, room=room)


@app.get("/health")
def health():
    return {"status": "ok"}

"""API for both personas: text and voice in, text + spoken out.

POST /chat        {"session_id", "message", "persona"} -> reply + cart + service_log
POST /chat/voice   multipart: audio file + session_id + persona -> transcript,
                   reply, cart, service_log, and base64 WAV audio (speech is
                   all Sarvam AI: Saaras hears, Bulbul speaks)
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
POST /table/open, GET /table/state, POST /table/send, POST /table/served,
POST /table/bill, POST /table/pay, POST /table/feedback, GET /table/suggestion,
POST /table/suggestion/dismiss -> the table QR pilot's guest flow: one table
                   session per guest (app/table/state.py) from the scan to
                   the bill: send what's new in the cart to the kitchen,
                   the bill with GST and a split, the UPI link, the rating.
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
import contextlib
import json
import logging
import threading

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

from pathlib import Path  # noqa: E402

from app import erp  # noqa: E402
from app.agent.graph import ENABLED_PERSONAS, AgentBusyError, RestaurantOrderingAgent  # noqa: E402
from app.agent.tools import add_item_to_cart, remove_item_from_cart_by_id  # noqa: E402
from app.menu import repository  # noqa: E402
from app.menu.credits import photo_credits  # noqa: E402
from app.menu.snapshot import LiveMenu, menu_cache  # noqa: E402
from app.owner_api import router as owner_router  # noqa: E402
from app.phone import outbox  # noqa: E402
from app.phone import upi  # noqa: E402
from app.phone.router import router as phone_router  # noqa: E402
from app.rag.menu_store import GROCERY_PATH, MenuStore  # noqa: E402
from app.table.service import unplaced  # noqa: E402
from app.table.state import TableState  # noqa: E402
from app.table.suggest import next_suggestion  # noqa: E402
from app.voice import livekit_tokens  # noqa: E402
from app.voice.stt import transcribe_bytes  # noqa: E402
from app.voice.tts import synthesize_sarvam  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"

logger = logging.getLogger("sarthi.api")


def _warm_menus() -> None:
    """Load every restaurant's menu into the cache so the first guest after a cold start does not
    wait for it (and the database connection is already open)."""
    try:
        for slug in repository.list_restaurant_slugs():
            menu_cache.get(slug)
        logger.info("menus warmed")
    except Exception:
        logger.warning("menu warm-up failed; menus load on first request instead", exc_info=True)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_warm_menus, daemon=True).start()  # never delays the server becoming ready
    stop_outbox = outbox.start()  # retries phone orders' WhatsApp messages
    yield
    stop_outbox.set()


app = FastAPI(title="Voice Ordering Agent", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(owner_router)
app.include_router(phone_router)

# Two catalogs: the food menu (waiter) and a separate grocery catalog for
# quick_commerce (shampoo, batteries, snacks, etc.) — see
# app/rag/menu_store.py for why they're kept as two collections.
food_menu_store = MenuStore()
grocery_store = MenuStore(data_path=GROCERY_PATH, collection_name="grocery_catalog")
sessions: dict[str, RestaurantOrderingAgent] = {}
# One table session per restaurant guest who scanned a table's QR code, keyed like `sessions`.
table_states: dict[str, TableState] = {}


def require_enabled(persona: str) -> None:
    """Hidden agents answer exactly like ones that don't exist."""
    if persona not in ENABLED_PERSONAS:
        raise HTTPException(status_code=404, detail=f"No agent '{persona}'")


def get_menu_store(persona: str, restaurant: str | None = None):
    if restaurant:
        return LiveMenu(restaurant)
    return grocery_store if persona == "quick_commerce" else food_menu_store


def live_restaurant(slug: str) -> dict:
    """A live restaurant's row from the menu cache, or a 404/503 the caller can raise as-is."""
    try:
        menu = menu_cache.get(slug)
    except RuntimeError as exc:  # Supabase not configured
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # e.g. the multi-restaurant migration hasn't been applied yet
        logging.getLogger("sarthi.api").exception("couldn't load restaurant %r", slug)
        raise HTTPException(status_code=503, detail="Restaurant data is unavailable right now") from exc
    if menu is None or menu.restaurant.get("status") != "live":
        raise HTTPException(status_code=404, detail=f"No restaurant '{slug}'")
    return menu.restaurant


class ChatRequest(BaseModel):
    session_id: str
    message: str
    persona: str = "waiter"
    restaurant: str | None = None  # a restaurant slug: talk to that restaurant's waiter
    table_no: str | None = None
    language: str = "en"  # the web app's English / हिन्दी toggle: "en" or "hi"


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
    persona: str = "waiter"
    item_id: str
    quantity: int = 1
    restaurant: str | None = None
    variant: str | None = None  # size/portion, for dishes that have them
    table_no: str | None = None
    suggested: bool = False  # added from the table page's suggestion card (counted as upsell)


class CartResponse(BaseModel):
    cart: list[dict]
    message: str


class SessionStateResponse(BaseModel):
    cart: list[dict]
    service_log: list[dict]


class CartSyncRequest(BaseModel):
    session_id: str
    persona: str = "waiter"
    restaurant: str | None = None
    table_no: str | None = None
    cart: list[dict]
    service_log: list[dict] = []
    placed_cart: list[dict] | None = None  # what the voice call already sent to the kitchen


class TableRequest(BaseModel):
    session_id: str
    restaurant: str
    table_no: str | None = None


class TableBillRequest(TableRequest):
    people: int = 1


class TablePayRequest(TableRequest):
    method: str  # "upi" or "counter"
    name: str | None = None
    phone: str | None = None
    offers_opt_in: bool = False


class TableFeedbackRequest(TableRequest):
    rating: int
    message: str | None = None


class TableDismissRequest(TableRequest):
    dish_id: str


class AdminOrdersResponse(BaseModel):
    configured: bool
    orders: list[dict]


class AdminRequestsResponse(BaseModel):
    configured: bool
    requests: list[dict]


class LiveKitTokenRequest(BaseModel):
    session_id: str
    persona: str = "waiter"
    restaurant: str | None = None
    table_no: str | None = None
    language: str = "en"


class LiveKitTokenResponse(BaseModel):
    configured: bool
    url: str | None = None
    token: str | None = None
    room: str | None = None


def get_or_create_session(
    session_id: str,
    persona: str,
    restaurant: str | None = None,
    table_no: str | None = None,
    language: str | None = None,
) -> RestaurantOrderingAgent:
    agent = _session(session_id, persona, restaurant, table_no)
    if language is not None:
        agent.set_language(language)  # the guest can flip the toggle at any message
    if restaurant and table_no:
        _attach_table(agent, restaurant, session_id, table_no)
    return agent


def _attach_table(
    agent: RestaurantOrderingAgent, restaurant: str, session_id: str, table_no: str | None
) -> TableState | None:
    """This guest's table session, opened the first time they are seen at a table."""
    state = table_states.get(agent.session_id)
    if state is None and table_no:
        state = TableState.open(live_restaurant(restaurant), session_id, table_no)
        table_states[agent.session_id] = state
    if state is not None:
        agent.on_round = state.record_round
    return state


def _session(
    session_id: str, persona: str, restaurant: str | None = None, table_no: str | None = None
) -> RestaurantOrderingAgent:
    if restaurant:
        # Restaurant mode: always the waiter persona, one cart per (restaurant, guest session).
        persona = "waiter"
        key = f"{restaurant}:{session_id}:{persona}"
        if key not in sessions:
            row = live_restaurant(restaurant)
            sessions[key] = RestaurantOrderingAgent(
                session_id=key,
                menu_store=LiveMenu(restaurant),
                persona=persona,
                restaurant=row,
                table_no=table_no,
            )
        return sessions[key]
    require_enabled(persona)
    key = f"{session_id}:{persona}"
    if key not in sessions:
        sessions[key] = RestaurantOrderingAgent(
            session_id=key, menu_store=get_menu_store(persona), persona=persona
        )
    return sessions[key]


def send_or_busy(agent: RestaurantOrderingAgent, text: str) -> str:
    try:
        return agent.send(text)
    except AgentBusyError as exc:
        raise HTTPException(
            status_code=429, detail="I'm handling a lot of requests right now — please try again in a few seconds."
        ) from exc


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    agent = get_or_create_session(req.session_id, req.persona, req.restaurant, req.table_no, req.language)
    reply = send_or_busy(agent, req.message)
    return ChatResponse(reply=reply, cart=agent.cart, service_log=agent.service_log)


@app.post("/chat/voice", response_model=VoiceChatResponse)
async def chat_voice(
    session_id: str,
    persona: str,
    audio: UploadFile,
    restaurant: str | None = None,
    table_no: str | None = None,
    language: str = "en",
) -> VoiceChatResponse:
    agent = get_or_create_session(session_id, persona, restaurant, table_no, language)
    persona = agent.persona

    audio_bytes = await audio.read()
    transcript = transcribe_bytes(audio_bytes, filename=audio.filename or "audio.webm")

    if not transcript:
        return VoiceChatResponse(transcript="", reply="", cart=agent.cart, service_log=agent.service_log)

    reply = send_or_busy(agent, transcript)

    try:
        reply_audio_b64 = base64.b64encode(synthesize_sarvam(reply, persona)).decode("ascii")
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
def get_menu(persona: str = "waiter", restaurant: str | None = None) -> MenuResponse:
    if restaurant:
        live_restaurant(restaurant)
    else:
        require_enabled(persona)
    return MenuResponse(items=get_menu_store(persona, restaurant).menu)


@app.get("/restaurants/{slug}")
def restaurant_info(slug: str) -> dict:
    """Public details for a restaurant's ordering page (never exposes owner data)."""
    r = live_restaurant(slug)
    keys = (
        "slug", "name", "cuisine", "tagline", "agent_name", "currency", "accent_color", "logo_url",
        "theme_mode", "corner_style", "heading_style", "gst_rate",
    )
    return {k: r.get(k) for k in keys}


@app.get("/restaurants/{slug}/photo-credits")
def restaurant_photo_credits(slug: str) -> dict:
    """The credit lines for the dish photos now showing (openly licensed photos must be credited)."""
    live_restaurant(slug)
    menu = menu_cache.get(slug)
    return {"credits": photo_credits(slug, menu.menu if menu else [])}


@app.post("/cart/add", response_model=CartResponse)
def cart_add(req: CartMutationRequest) -> CartResponse:
    agent = get_or_create_session(req.session_id, req.persona, req.restaurant, req.table_no)
    item = get_menu_store(req.persona, req.restaurant).get(req.item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"No menu item with id '{req.item_id}'")
    message = add_item_to_cart(agent.cart, item, req.quantity, req.variant)
    if req.suggested and (state := table_states.get(agent.session_id)):
        state.suggestion_added(req.item_id)
    return CartResponse(cart=agent.cart, message=message)


@app.post("/cart/remove", response_model=CartResponse)
def cart_remove(req: CartMutationRequest) -> CartResponse:
    agent = get_or_create_session(req.session_id, req.persona, req.restaurant, req.table_no)
    message = remove_item_from_cart_by_id(agent.cart, req.item_id, req.quantity, req.variant)
    return CartResponse(cart=agent.cart, message=message)


@app.get("/cart", response_model=SessionStateResponse)
def get_cart(session_id: str, persona: str = "waiter", restaurant: str | None = None) -> SessionStateResponse:
    agent = get_or_create_session(session_id, persona, restaurant)
    return SessionStateResponse(cart=agent.cart, service_log=agent.service_log)


@app.post("/cart/sync", response_model=SessionStateResponse)
def cart_sync(req: CartSyncRequest) -> SessionStateResponse:
    agent = get_or_create_session(req.session_id, req.persona, req.restaurant, req.table_no)
    agent.cart[:] = req.cart
    agent.service_log[:] = req.service_log
    if req.placed_cart is not None and unplaced(req.placed_cart, agent._placed_cart):
        agent.sync_placed(req.placed_cart)
    return SessionStateResponse(cart=agent.cart, service_log=agent.service_log)


# ------------------------------------------------------------- table QR pilot --


def _table(req: TableRequest) -> tuple[RestaurantOrderingAgent, TableState]:
    agent = get_or_create_session(req.session_id, "waiter", req.restaurant, req.table_no)
    state = _attach_table(agent, req.restaurant, req.session_id, req.table_no)
    if state is None:
        raise HTTPException(status_code=400, detail="Scan the QR code on your table to order from it.")
    return agent, state


def _table_view(agent: RestaurantOrderingAgent, state: TableState) -> dict:
    return {**state.view(), "unsent": unplaced(agent.cart, agent._placed_cart)}


@app.post("/table/open")
def table_open(req: TableRequest) -> dict:
    agent, state = _table(req)
    return _table_view(agent, state)


@app.get("/table/state")
def table_state(session_id: str, restaurant: str, table_no: str | None = None) -> dict:
    agent, state = _table(TableRequest(session_id=session_id, restaurant=restaurant, table_no=table_no))
    return _table_view(agent, state)


@app.post("/table/send")
def table_send(req: TableRequest) -> dict:
    """Sends what is new in the guest's cart to the kitchen, as one round."""
    agent, state = _table(req)
    lines = unplaced(agent.cart, agent._placed_cart)
    if not lines:
        raise HTTPException(status_code=409, detail="Nothing new to send. Add a dish first.")
    total = sum(line["price"] * line["quantity"] for line in lines)
    saved = erp.record_order(
        agent.session_id, agent.persona, lines, total, restaurant_id=state.restaurant_id, table_no=state.table_no
    )
    if saved is False:
        raise HTTPException(status_code=503, detail="Couldn't reach the kitchen, so nothing was sent. Please try again.")
    agent.mark_order_placed()  # records the round on the table session
    return {"round": state.rounds, "lines": lines, "table": _table_view(agent, state)}


@app.post("/table/served")
def table_served(req: TableRequest) -> dict:
    agent, state = _table(req)
    state.food_served()
    return _table_view(agent, state)


@app.post("/table/bill")
def table_bill(req: TableBillRequest) -> dict:
    """The table's bill so far, split `people` ways, with a UPI link for one share."""
    _, state = _table(req)
    if not state.ordered:
        raise HTTPException(status_code=409, detail="Nothing has been sent to the kitchen yet.")
    state.restaurant = live_restaurant(req.restaurant)  # the owner may have just changed GST or UPI
    bill = state.request_bill(req.people)
    r = state.restaurant
    upi_link = None
    if r.get("upi_id") and r.get("upi_payee_name") and bill["share"] > 0:
        reference = f"T{state.table_no or ''}{state.session_id[:6]}".upper()
        upi_link = upi.payment_uri(r, bill["share"], reference)
    return {**bill, "upi_link": upi_link, "payee": r.get("upi_payee_name") or r.get("name")}


def _indian_mobile(raw: str | None) -> str | None:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise HTTPException(status_code=422, detail="Enter a 10-digit mobile number, or leave it empty.")
    return digits


@app.post("/table/pay")
def table_pay(req: TablePayRequest) -> dict:
    """How the guest is paying. Staff confirm the money on the owner console's Tonight screen."""
    if req.method not in ("upi", "counter"):
        raise HTTPException(status_code=422, detail="method must be 'upi' or 'counter'")
    agent, state = _table(req)
    phone = _indian_mobile(req.phone)
    name = (req.name or "").strip()[:80] or None
    state.pay(req.method, name, phone, bool(req.offers_opt_in and phone))
    return _table_view(agent, state)


@app.post("/table/feedback")
def table_feedback(req: TableFeedbackRequest) -> dict:
    """The guest's rating. Everyone is offered the Google review link; a message goes to the owner
    privately as a table request."""
    if not 1 <= req.rating <= 5:
        raise HTTPException(status_code=422, detail="rating must be 1 to 5")
    agent, state = _table(req)
    state.restaurant = live_restaurant(req.restaurant)
    message = (req.message or "").strip()[:500] or None
    state.rate(req.rating, message)
    if message:
        erp.record_request(
            agent.session_id, agent.persona, "complaint", details=message, notes=f"Rated {req.rating} of 5",
            restaurant_id=state.restaurant_id, table_no=state.table_no,
        )
    return {"review_url": state.restaurant.get("google_review_url") or None}


@app.get("/table/suggestion")
def table_suggestion(session_id: str, restaurant: str, table_no: str | None = None) -> dict:
    agent, state = _table(TableRequest(session_id=session_id, restaurant=restaurant, table_no=table_no))
    menu = LiveMenu(restaurant)
    return {"suggestion": next_suggestion(state, menu.menu, menu.get, agent.cart)}


@app.post("/table/suggestion/dismiss")
def table_suggestion_dismiss(req: TableDismissRequest) -> dict:
    _, state = _table(req)
    state.suggestion_dismissed(req.dish_id)
    return {"ok": True}


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

    persona = "waiter" if req.restaurant else req.persona
    require_enabled(persona)
    meta = {"language": req.language}
    if req.restaurant:
        live_restaurant(req.restaurant)  # 404 for unknown/hidden restaurants before we spend a LiveKit call
        meta.update(restaurant=req.restaurant, table_no=req.table_no)
    metadata = json.dumps(meta)
    room = livekit_tokens.room_name_for(persona, req.session_id)
    await livekit_tokens.ensure_dispatch(room, metadata)
    identity = f"customer-{req.session_id[:8]}"
    token = livekit_tokens.mint_token(identity, room)
    return LiveKitTokenResponse(configured=True, url=livekit_tokens.LIVEKIT_URL, token=token, room=room)


@app.get("/health")
def health():
    return {"status": "ok"}

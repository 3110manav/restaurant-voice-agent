"""HTTP routes Sarvam Samvaad calls, and the browser's route to start a Samvaad call.

Samvaad's API tools POST here (see SARVAM_SETUP.md for each tool's configuration):

  POST /samvaad/start                  on_start hook: which store, greeting variables
  POST /samvaad/tools/{tool}           search_menu, get_item_details, add_to_cart, remove_from_cart, view_cart,
                                       set_order_details, read_back_order, checkout, request_callback
  POST /samvaad/end                    on_end hook / deployment webhook: closes the call's log

Every one needs `Authorization: Bearer <SAMVAAD_TOOL_TOKEN>` (stored in Samvaad's Secrets), because they can
place real orders. Each body carries Samvaad's `interaction_id`, plus `store_slug` so a tool call can find its
store even if the start hook was missed. Replies are JSON: `result` is for the agent to act on, `say` (when
present) is the exact sentence to speak, and `cart_summary` / `cart_total` can be saved into agent variables.

The browser side (web/src/components/voice/sarvam-call.tsx) uses Sarvam's web SDK, which first fetches a
signed websocket URL. It asks this API instead of Sarvam (GET /samvaad/browser/...), so the Sarvam API key
stays on the server; only the configured agent can be reached this way.
"""
import hmac
import json
import logging
import os

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, model_validator

from app.phone import repository
from app.samvaad.session import SamvaadSession, StoreNotFound, sessions

logger = logging.getLogger("sarthi.samvaad.router")

router = APIRouter(prefix="/samvaad", tags=["samvaad"])

SARVAM_RUNTIME = "https://apps.sarvam.ai/api/app-runtime/"


class ToolCall(BaseModel):
    """What any Samvaad tool sends. Everything is optional; which fields matter depends on the tool."""

    model_config = ConfigDict(extra="allow")

    # Samvaad's built-in Interaction ID. It is empty when a tool is tried with "Send" in the tool editor,
    # since there is no call yet, so a missing one falls back to an ID per caller (see _fill_interaction_id).
    interaction_id: str | None = None
    store_slug: str | None = None
    called_number: str | None = None
    caller: str | None = None
    language: str | None = None
    channel: str | None = None
    # tool arguments, filled in by Samvaad's LLM
    query: str | None = None
    name: str | None = None
    item_name: str | None = None
    quantity: int | str | None = None
    variant: str | None = None
    items: list | str | None = None
    order_type: str | None = None
    address: str | None = None
    whatsapp_number: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _fill_interaction_id(self) -> "ToolCall":
        if _blank(self.interaction_id):
            caller = _clean(self.caller) if isinstance(self.caller, str) else None
            self.interaction_id = f"no-interaction-id-{caller or 'unknown'}"
            logger.warning("Samvaad tool call without an interaction ID; using %s", self.interaction_id)
        return self


def _authorize(authorization: str | None) -> None:
    expected = os.environ.get("SAMVAAD_TOOL_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="SAMVAAD_TOOL_TOKEN isn't set on the API")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Bad tool token")


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and (not value.strip() or value.strip().startswith("@")))


def _clean(value: str | None) -> str | None:
    """Samvaad sends an unfilled variable as an empty string (or its own placeholder); treat both as absent."""
    return None if _blank(value) else value.strip()


def _session(call: ToolCall) -> SamvaadSession:
    try:
        return sessions.open(
            call.interaction_id,
            store=_clean(call.store_slug),
            called_number=_clean(call.called_number),
            caller=_clean(call.caller),
            language=_clean(call.language),
            channel=_clean(call.channel) or "phone",
        )
    except StoreNotFound as e:
        logger.error("Samvaad call %s: %s", call.interaction_id, e)
        raise HTTPException(status_code=404, detail="No store is set up for this call") from e
    except repository.NotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


def _quantity(value) -> int:
    try:
        return max(int(str(value).strip()), 1)
    except (TypeError, ValueError):
        return 1


def _items(call: ToolCall) -> list[dict]:
    """add_to_cart takes `items` (a list, or that list as JSON text) or one item in item_name/quantity/variant."""
    raw = call.items
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = [{"name": raw}]
    items = []
    for entry in raw or []:
        if isinstance(entry, str):
            entry = {"name": entry}
        if isinstance(entry, dict):
            items.append({"name": entry.get("name") or entry.get("item_name") or "",
                          "quantity": _quantity(entry.get("quantity")), "variant": entry.get("variant") or ""})
    name = _clean(call.item_name) or _clean(call.name)
    if name:
        items.append({"name": name, "quantity": _quantity(call.quantity), "variant": _clean(call.variant) or ""})
    return items


@router.post("/start")
def start(call: ToolCall, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    session = _session(call)
    return {**session.start_variables(), **session.snapshot()}


TOOLS = (
    "search_menu", "get_item_details", "add_to_cart", "remove_from_cart", "view_cart",
    "set_order_details", "read_back_order", "checkout", "request_callback",
)


@router.post("/tools/{tool}")
def run_tool(tool: str, call: ToolCall, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    if tool not in TOOLS:
        raise HTTPException(status_code=404, detail=f"Unknown tool {tool!r}")
    session = _session(call)
    lang = _clean(call.language)
    with session.lock:
        try:
            if tool == "search_menu":
                return session.search_menu(_clean(call.query) or _clean(call.name) or "", lang)
            if tool == "get_item_details":
                return session.item_details(_clean(call.name) or _clean(call.item_name) or "", lang)
            if tool == "add_to_cart":
                return session.add(_items(call), lang)
            if tool == "remove_from_cart":
                name = _clean(call.item_name) or _clean(call.name) or ""
                return session.remove(name, _quantity(call.quantity), _clean(call.variant) or "", lang)
            if tool == "view_cart":
                return session.view(lang)
            if tool == "set_order_details":
                return session.set_details(
                    _clean(call.order_type) or "", _clean(call.address) or "", _clean(call.whatsapp_number) or "", lang
                )
            if tool == "read_back_order":
                return session.read_back(lang)
            if tool == "checkout":
                return session.place(lang)
            return session.callback(_clean(call.reason) or "the guest asked", lang)
        except Exception:
            logger.exception("Samvaad tool %s failed on call %s", tool, call.interaction_id)
            # Something the agent can say, rather than an error it may read out or retry in a loop.
            return {"result": "Something went wrong on our side. Apologise briefly and offer to have the restaurant call back."}


@router.post("/end")
async def end(request: Request, authorization: str | None = Header(default=None)) -> dict:
    """Takes Samvaad's on_end tool body or its deployment webhook payload: anything with an interaction id."""
    _authorize(authorization)
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    interaction_id = (
        payload.get("interaction_id") or payload.get("attempt_id") or (payload.get("data") or {}).get("interaction_id")
    )
    session = sessions.pop(str(interaction_id)) if interaction_id else None
    if session is None:
        return {"closed": False}
    transcript = payload.get("transcript") or payload.get("call_transcript")
    extra = {k: payload[k] for k in ("call_length", "duration", "end_reason", "outcome") if k in payload}
    session.close(transcript, extra or None)
    return {"closed": True, "outcome": "ordered" if session.order.order_id else "not ordered"}


# ------------------------------------------------------------- browser side --


def _browser_agent() -> dict:
    return {
        "org_id": os.environ.get("SARVAM_ORG_ID", "").strip(),
        "workspace_id": os.environ.get("SARVAM_WORKSPACE_ID", "").strip(),
        "app_id": os.environ.get("SARVAM_APP_ID", "").strip(),
        "version": os.environ.get("SARVAM_APP_VERSION", "").strip() or None,
    }


@router.get("/browser/config")
def browser_config() -> dict:
    """What the browser SDK needs to name the agent (no secrets), and the stores a demo can call."""
    agent = _browser_agent()
    enabled = all(agent[k] for k in ("org_id", "workspace_id", "app_id")) and bool(os.environ.get("SARVAM_API_KEY"))
    stores = []
    if enabled:
        try:
            rows = repository._c().table("phone_stores").select("slug,name,business_type,agent_name").execute().data
            stores = [r for r in rows if r.get("business_type") == "restaurant"]
        except Exception:
            logger.warning("couldn't list stores for the Samvaad demo", exc_info=True)
    return {"enabled": enabled, **agent, "stores": stores}


@router.get("/browser/cart/{interaction_id:path}")  # Samvaad IDs contain "/"
def browser_cart(interaction_id: str) -> dict:
    """The live cart of a call in progress, for the page to show while the guest talks. Read-only, and only
    reachable with the interaction id, which Sarvam makes up per call and only that browser knows."""
    session = sessions.get(interaction_id)
    if session is None:
        return {"active": False, "cart": [], "cart_summary": "empty", "cart_total": "₹0", "order_placed": False}
    return {"active": True, "store_name": session.store["name"], **session.snapshot()}


@router.get("/browser/orgs/{org_id}/workspaces/{workspace_id}/apps/{app_id}/url")
def browser_signed_url(org_id: str, workspace_id: str, app_id: str, request: Request):
    """The SDK's signed-URL request, passed to Sarvam with our key. Only for the configured agent."""
    agent = _browser_agent()
    if (org_id, workspace_id, app_id) != (agent["org_id"], agent["workspace_id"], agent["app_id"]) or not agent["app_id"]:
        raise HTTPException(status_code=404, detail="Unknown agent")
    key = os.environ.get("SARVAM_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="SARVAM_API_KEY isn't set on the API")
    params = {k: v for k, v in request.query_params.items() if k in ("interaction_type", "version")}
    base = os.environ.get("SARVAM_APP_RUNTIME_URL", SARVAM_RUNTIME).rstrip("/") + "/"
    url = f"{base}orgs/{org_id}/workspaces/{workspace_id}/apps/{app_id}/url"
    try:
        response = httpx.get(url, params=params, headers={"X-API-Key": key}, timeout=15)
    except httpx.HTTPError as e:
        logger.warning("Sarvam signed URL request failed: %s", e)
        raise HTTPException(status_code=502, detail="Couldn't reach Sarvam") from e
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text[:300]}
    return JSONResponse(body, status_code=response.status_code)

"""Pushes the LiveKit worker's in-memory cart/service_log back to the main
API process after every realtime voice turn.

The worker (app/voice/livekit_worker.py) runs as its own OS process with its
own RestaurantOrderingAgent, so its cart isn't visible to the web app, which
reads cart state from the main API process (app/main.py's `sessions` dict).
This is the bridge: a best-effort HTTP call, under the same (session_id,
persona) key the text/push-to-talk paths use, so GET /cart there reflects
what was just ordered by voice.

Fire-and-forget: if the main API is slow or unreachable, the call itself
still succeeded from the customer's point of view (the worker's own cart has
it) — this only affects whether the web UI's cart display catches up.
"""
import os

import httpx

API_BASE_URL = os.environ.get("SARTHI_API_BASE_URL", "http://localhost:8000")


async def sync_cart(session_id: str, persona: str, cart: list[dict], service_log: list[dict]) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{API_BASE_URL}/cart/sync",
                json={
                    "session_id": session_id,
                    "persona": persona,
                    "cart": cart,
                    "service_log": service_log,
                },
            )
    except Exception:
        pass

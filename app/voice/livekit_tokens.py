"""Mints LiveKit access tokens and dispatches the realtime voice worker for
the web app's "Start call" feature — see POST /livekit/token in app/main.py.

Deliberately built on the lightweight `livekit-api` package (JWT + REST
calls only: aiohttp/protobuf/pyjwt, no onnxruntime or audio runtime), not
the full `livekit-agents` package that app/voice/livekit_worker.py needs —
that keeps the main API's dependencies (and Docker image) lean. See
requirements-livekit.txt for why those are kept separate.
"""
import os

from livekit import api

AGENT_NAME = "sarthi-voice"

LIVEKIT_URL = os.environ.get("LIVEKIT_URL")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET")


def is_configured() -> bool:
    return bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET)


def room_name_for(persona: str, session_id: str) -> str:
    """Matches app/voice/livekit_rooms.py's parse_room_name on the worker side."""
    return f"sarthi__{persona}__{session_id}"


async def ensure_dispatch(room: str, metadata: str = "") -> None:
    """Make sure the sarthi-voice worker is dispatched into `room`. `metadata`
    (a JSON string) reaches the worker as ctx.job.metadata — that's how it learns
    which restaurant and table the call is for.

    Best-effort: if a dispatch already exists for this room (e.g. the
    customer's page reconnects after a network blip), LiveKit's response is
    harmless to ignore rather than surfacing as an error to the customer.
    """
    lkapi = api.LiveKitAPI()
    try:
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room, metadata=metadata)
        )
    except Exception:
        pass
    finally:
        await lkapi.aclose()


def mint_token(identity: str, room: str) -> str:
    return (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )

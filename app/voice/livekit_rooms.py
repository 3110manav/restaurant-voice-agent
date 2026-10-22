"""Room-naming convention for realtime voice sessions, split out from
livekit_worker.py so it's testable without pulling in livekit-agents or
building both MenuStores (that module's other top-level work).
"""


def parse_room_name(room_name: str) -> tuple[str, str]:
    """"sarthi__{persona}__{session_id}" -> (persona, session_id).

    Falls back to the online persona, keyed by the raw room name, for a
    room that doesn't follow the convention (e.g. manual testing via the
    LiveKit Agents Playground).
    """
    parts = room_name.split("__", 2)
    if len(parts) == 3 and parts[0] == "sarthi":
        return parts[1], parts[2]
    return "online", room_name

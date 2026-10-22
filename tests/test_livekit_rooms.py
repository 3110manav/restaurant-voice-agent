"""Tests for the realtime-voice room-naming convention (no livekit-agents
or API keys needed — see app/voice/livekit_rooms.py for why this is split
out from livekit_worker.py)."""
from app.voice.livekit_rooms import parse_room_name


def test_parse_room_name_matches_convention():
    assert parse_room_name("sarthi__quick_commerce__abc123") == ("quick_commerce", "abc123")


def test_parse_room_name_session_id_can_contain_double_underscore():
    assert parse_room_name("sarthi__hotel__guest__42") == ("hotel", "guest__42")


def test_parse_room_name_falls_back_for_unrecognized_room():
    assert parse_room_name("some-random-playground-room") == ("online", "some-random-playground-room")

from app.agent.graph import _PERSONAS
from app.voice.voices import PERSONA_VOICES, voices_for

ORPHEUS_FEMALE = {"autumn", "diana", "hannah"}
ORPHEUS_MALE = {"austin", "daniel", "troy"}


def test_every_persona_has_english_and_hindi_voice():
    assert set(PERSONA_VOICES) == set(_PERSONAS)
    for voices in PERSONA_VOICES.values():
        assert set(voices) == {"en", "hi"}
        assert voices["en"] in ORPHEUS_FEMALE | ORPHEUS_MALE


def test_english_voice_gender_matches_agent_gender():
    assert voices_for("online")["en"] in ORPHEUS_FEMALE  # Meera
    assert voices_for("hotel")["en"] in ORPHEUS_FEMALE  # Ira
    assert voices_for("quick_commerce")["en"] in ORPHEUS_MALE  # Veer
    assert voices_for("waiter")["en"] in ORPHEUS_MALE  # Kabir


def test_unknown_persona_falls_back_to_online_voice():
    assert voices_for("nope") == PERSONA_VOICES["online"]

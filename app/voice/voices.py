"""Which TTS voice each persona speaks with. Pure data (no API clients) so
it's testable without keys.

Every agent speaks through Sarvam Bulbul v3's `shubh`. English voices are
Groq Orpheus's (autumn/diana/hannah are female, austin/daniel/troy male),
which only the legacy voice CLI still uses.
"""

SARVAM_VOICE = "shubh"

PERSONA_VOICES: dict[str, dict[str, str]] = {
    "online": {"en": "hannah", "hi": SARVAM_VOICE},          # Meera
    "quick_commerce": {"en": "austin", "hi": SARVAM_VOICE},  # Veer
    "waiter": {"en": "daniel", "hi": SARVAM_VOICE},          # Kabir
    "hotel": {"en": "diana", "hi": SARVAM_VOICE},            # Ira
}

DEFAULT_PERSONA = "online"


def voices_for(persona: str) -> dict[str, str]:
    return PERSONA_VOICES.get(persona, PERSONA_VOICES[DEFAULT_PERSONA])

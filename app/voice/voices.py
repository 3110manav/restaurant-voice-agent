"""Which TTS voice each persona speaks with, so an agent's voice matches its
name's gender. Pure data (no API clients) so it's testable without keys.

English voices are Groq Orpheus's (autumn/diana/hannah are female,
austin/daniel/troy male); Hindi voices are Sarvam Bulbul v3 speakers.
"""

PERSONA_VOICES: dict[str, dict[str, str]] = {
    "online": {"en": "hannah", "hi": "priya"},          # Meera, female
    "quick_commerce": {"en": "austin", "hi": "rohan"},  # Veer, male
    "waiter": {"en": "daniel", "hi": "kabir"},          # Kabir, male
    "hotel": {"en": "diana", "hi": "ritu"},             # Ira, female
}

DEFAULT_PERSONA = "online"


def voices_for(persona: str) -> dict[str, str]:
    return PERSONA_VOICES.get(persona, PERSONA_VOICES[DEFAULT_PERSONA])

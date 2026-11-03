"""Which TTS voice each persona speaks with. Pure data (no API clients) so
it's testable without keys.

Every agent speaks as Shubh on Sarvam Bulbul v4 Flash, whose voice IDs are
persona_language_style. "hi" reads purely Hindi sentences; "mixed" reads
everything with Latin letters, since Hindi replies keep dish names in English
and English replies are full of Indian dish names. "en" voices are Groq
Orpheus's (autumn/diana/hannah are female, austin/daniel/troy male), which
only the legacy voice CLI still uses.
"""

SARVAM_HINDI_VOICE = "shubh_hi_customer"
SARVAM_MIXED_VOICE = "shubh_enhi_banking"

PERSONA_VOICES: dict[str, dict[str, str]] = {
    "online": {"en": "hannah", "hi": SARVAM_HINDI_VOICE, "mixed": SARVAM_MIXED_VOICE},          # Meera
    "quick_commerce": {"en": "austin", "hi": SARVAM_HINDI_VOICE, "mixed": SARVAM_MIXED_VOICE},  # Veer
    "waiter": {"en": "daniel", "hi": SARVAM_HINDI_VOICE, "mixed": SARVAM_MIXED_VOICE},          # Kabir
    "hotel": {"en": "diana", "hi": SARVAM_HINDI_VOICE, "mixed": SARVAM_MIXED_VOICE},            # Ira
}

DEFAULT_PERSONA = "online"


def voices_for(persona: str) -> dict[str, str]:
    return PERSONA_VOICES.get(persona, PERSONA_VOICES[DEFAULT_PERSONA])

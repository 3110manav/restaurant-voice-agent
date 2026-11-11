"""Which speech models the agent hears and speaks with: one setting, SARTHI_SPEECH.

  groq    Groq's Whisper hears, Groq's Orpheus speaks English, and Sarvam's Bulbul speaks Hindi.
          The free-tier stack, and the default.
  sarvam  Sarvam's Saaras hears Hindi, English and a mix of both, and Bulbul speaks all of it.
          Built for Indian phone calls; needs SARVAM_API_KEY and uses Sarvam credits.

It decides push-to-talk (app/voice/stt.py, tts.py), the browser's realtime calls and phone calls
(app/voice/livekit_stack.py). Everything else is the same on both: the agent, its tools, the stores,
WhatsApp, the customers, the owner pages. So one codebase can run both ways, by environment alone.
"""
import os

STACKS = ("groq", "sarvam")
DEFAULT = "groq"


def speech_stack() -> str:
    """The stack in use. Read on each call, so a typo fails loudly instead of quietly picking one."""
    value = os.environ.get("SARTHI_SPEECH", DEFAULT).strip().lower() or DEFAULT
    if value not in STACKS:
        raise ValueError(f"SARTHI_SPEECH must be one of {', '.join(STACKS)}, not {value!r}")
    return value


def uses_sarvam() -> bool:
    return speech_stack() == "sarvam"

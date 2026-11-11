"""Which speech models the agent hears and speaks with: one setting, SARTHI_SPEECH.

  groq    Groq's Whisper hears, Groq's Orpheus speaks English, and Sarvam's Bulbul speaks Hindi.
          The free-tier stack, and the default.
  sarvam  Sarvam's Saaras hears Hindi, English and a mix of both, and Bulbul speaks all of it.
          Built for Indian phone calls; needs SARVAM_API_KEY and uses Sarvam credits.

It decides push-to-talk (app/voice/stt.py, tts.py), the browser's realtime calls and phone calls
(app/voice/livekit_stack.py). Everything else is the same on both: the agent, its tools, the stores,
WhatsApp, the customers, the owner pages. So one codebase can run both ways, by environment alone.

SARTHI_SPEECH is the deployment's default. With SARTHI_SPEECH_CHOICE=1 the web app's Groq / Sarvam switch may
override it for that guest's push-to-talk and browser calls (`resolve`). Without it a guest cannot spend Sarvam
credits, whatever they send. Phone calls have no switch and always use the default.
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


def choice_allowed() -> bool:
    """May a guest pick the stack from the web app? Off unless SARTHI_SPEECH_CHOICE is set, so a public
    site does not let anyone use up the Sarvam credits."""
    return os.environ.get("SARTHI_SPEECH_CHOICE", "").strip().lower() in ("1", "true", "yes", "on")


def resolve(requested: str | None) -> str:
    """The stack for one guest: what they asked for if that is a real stack and choosing is allowed, else the default."""
    asked = (requested or "").strip().lower()
    return asked if choice_allowed() and asked in STACKS else speech_stack()


def uses_sarvam(requested: str | None = None) -> bool:
    return resolve(requested) == "sarvam"

"""The realtime calls' speech models (browser calls in livekit_worker.py, phone calls in livekit_phone.py),
chosen by SARTHI_SPEECH. See app/voice/stack.py for what each stack is.

LiveKit carries the audio either way; only who hears and who speaks changes.
"""
import os

from livekit.agents import stt as lk_stt
from livekit.agents import tts as lk_tts
from livekit.plugins import groq, sarvam

from app.voice.livekit_tts import build_speech, warm_phrases
from app.voice.stack import uses_sarvam

# saaras:v4 is the plugin's default; v3 is what we've priced, so moving is a deliberate test.
SARVAM_STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v3")
GROQ_STT_MODEL = "whisper-large-v3-turbo"


def build_stt(language: str | None) -> lk_stt.STT:
    """Speech-to-text for a call. `language` is the conversation's ("en" or "hi") when it is fixed, as in a
    browser call; None on a phone call, where it can change and is heard from each sentence."""
    if uses_sarvam():
        # Saaras hears code-mixed Hindi and English and detects which, so it needs no language.
        return sarvam.STT(language="unknown", model=SARVAM_STT_MODEL, mode="codemix")
    if language:
        return groq.STT(model=GROQ_STT_MODEL, language=language)
    return groq.STT(model=GROQ_STT_MODEL, detect_language=True)


def build_tts(persona: str, language: str | None, sample_rate: int | None = None) -> lk_tts.StreamAdapter:
    """Text-to-speech for a call. `sample_rate` is 8000 on a phone line, which carries nothing more."""
    return build_speech(persona, language, sarvam_only=uses_sarvam(), sample_rate=sample_rate)


def warm(persona: str, language: str | None, phrases: list[str], sample_rate: int | None = None) -> None:
    """Pre-generate the short acknowledgement phrases so they play instantly."""
    warm_phrases(persona, language, phrases, uses_sarvam(), sample_rate)

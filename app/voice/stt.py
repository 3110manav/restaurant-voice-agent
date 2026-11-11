"""Speech-to-text for push-to-talk and the CLIs, on the stack chosen by SARTHI_SPEECH (app/voice/stack.py).

Groq's Whisper is told the conversation's language (the web app's English / हिन्दी toggle), so a short
or accented English clip can't be mis-detected as Hindi and written in Devanagari. Sarvam's Saaras, in
codemix mode, hears Hindi, English and a mix of the two whichever way the toggle is set; the toggle still
decides the language of the reply. Without a language (the legacy CLIs) Whisper auto-detects.
"""
import functools

from app.voice.stack import uses_sarvam

GROQ_MODEL = "whisper-large-v3-turbo"
SARVAM_MODEL = "saaras:v3"


# Without an explicit timeout, a stalled connection blocks forever with no visible error: bound it so a
# network hiccup fails loudly instead of hanging the caller. Each client is built on first use, so a
# deployment needs only the key of the stack it runs.
@functools.cache
def _groq():
    from groq import Groq

    return Groq(timeout=30.0, max_retries=1)  # reads GROQ_API_KEY from the environment


@functools.cache
def _sarvam():
    from sarvamai import SarvamAI

    return SarvamAI(timeout=30.0)  # reads SARVAM_API_KEY from the environment


def transcribe_bytes(data: bytes, filename: str = "audio.wav", language: str | None = None) -> str:
    if uses_sarvam():
        result = _sarvam().speech_to_text.transcribe(
            file=(filename, data), model=SARVAM_MODEL, mode="codemix", language_code="unknown"
        )
        return result.transcript.strip()
    options = {"language": language} if language else {}
    result = _groq().audio.transcriptions.create(
        file=(filename, data), model=GROQ_MODEL, response_format="text", **options
    )
    return str(result).strip()


def transcribe(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        return transcribe_bytes(f.read(), filename=audio_path)

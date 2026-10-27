"""Speech-to-text via Groq's hosted Whisper.

The conversation's language (the web app's English / हिन्दी toggle) is passed to Whisper, so a short
or accented English clip can't be mis-detected as Hindi and written in Devanagari. Without a language
(the legacy CLIs) Whisper auto-detects.
"""
from groq import Groq

# Without an explicit timeout, a stalled connection blocks forever with no
# visible error — bound it so a network hiccup fails loudly instead of
# hanging the CLI.
_client = Groq(timeout=30.0, max_retries=1)  # reads GROQ_API_KEY from the environment

MODEL = "whisper-large-v3-turbo"


def transcribe_bytes(data: bytes, filename: str = "audio.wav", language: str | None = None) -> str:
    options = {"language": language} if language else {}
    result = _client.audio.transcriptions.create(
        file=(filename, data),
        model=MODEL,
        response_format="text",
        **options,
    )
    return str(result).strip()


def transcribe(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        return transcribe_bytes(f.read(), filename=audio_path)

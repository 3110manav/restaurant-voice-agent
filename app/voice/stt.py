"""Speech-to-text via Groq's hosted Whisper.

No language is forced — Whisper auto-detects, and handles Hindi and
Hindi/English code-switching reasonably well out of the box.
"""
from groq import Groq

# Without an explicit timeout, a stalled connection blocks forever with no
# visible error — bound it so a network hiccup fails loudly instead of
# hanging the CLI.
_client = Groq(timeout=30.0, max_retries=1)  # reads GROQ_API_KEY from the environment

MODEL = "whisper-large-v3-turbo"


def transcribe_bytes(data: bytes, filename: str = "audio.wav") -> str:
    result = _client.audio.transcriptions.create(
        file=(filename, data),
        model=MODEL,
        response_format="text",
    )
    return str(result).strip()


def transcribe(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        return transcribe_bytes(f.read(), filename=audio_path)

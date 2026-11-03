"""Speech-to-text via Sarvam's Saaras, for push-to-talk and the CLIs.

Codemix mode hears Hindi, English and a mix of the two, so a guest can speak either way whatever the
web app's English / हिन्दी toggle says. The toggle still decides the language of the reply.
"""
from sarvamai import SarvamAI

# Without an explicit timeout, a stalled connection blocks forever with no
# visible error — bound it so a network hiccup fails loudly instead of
# hanging the CLI.
_client = SarvamAI(timeout=30.0)  # reads SARVAM_API_KEY from the environment

MODEL = "saaras:v3"


def transcribe_bytes(data: bytes, filename: str = "audio.wav") -> str:
    result = _client.speech_to_text.transcribe(
        file=(filename, data),
        model=MODEL,
        mode="codemix",
        language_code="unknown",
    )
    return result.transcript.strip()


def transcribe(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        return transcribe_bytes(f.read(), filename=audio_path)

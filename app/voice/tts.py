"""Text-to-speech: Groq's Orpheus for English, Sarvam AI's Bulbul for Hindi.

`synthesize()` picks the voice from the conversation's language when the caller knows it
(the web app's English / हिन्दी toggle), and otherwise from the script of the text. Orpheus (English) requires a one-time terms
acceptance in the Groq console: console.groq.com/playground?model=
canopylabs%2Forpheus-v1-english

sounddevice/soundfile (local speaker playback) are imported lazily inside
speak() rather than at module level: the hosted server only ever calls
synthesize() and ships the bytes to a client, so it should never need a
system audio library that's only relevant to the local CLIs.
"""
import base64

from groq import Groq
from sarvamai import SarvamAI

from app.agent.language import use_hindi_voice
from app.voice.voices import voices_for

_groq_client = Groq(timeout=30.0, max_retries=1)
_sarvam_client = SarvamAI(timeout=30.0)  # reads SARVAM_API_KEY from the environment

ENGLISH_MODEL = "canopylabs/orpheus-v1-english"
ENGLISH_DEFAULT_VOICE = "hannah"

HINDI_MODEL = "bulbul:v3"
HINDI_DEFAULT_VOICE = "shubh"
HINDI_LANGUAGE_CODE = "hi-IN"


def _synthesize_english(text: str, voice: str = ENGLISH_DEFAULT_VOICE) -> bytes:
    response = _groq_client.audio.speech.create(
        model=ENGLISH_MODEL,
        voice=voice,
        input=text,
        response_format="wav",
    )
    return response.read()


def _synthesize_hindi(text: str, voice: str = HINDI_DEFAULT_VOICE) -> bytes:
    result = _sarvam_client.text_to_speech.convert(
        text=text,
        language_code=HINDI_LANGUAGE_CODE,
        model=HINDI_MODEL,
        speaker=voice,
        output_audio_codec="wav",
    )
    return base64.b64decode(result.audios[0])


def synthesize(text: str, persona: str = "online", language: str | None = None) -> bytes:
    """Synthesize speech in the conversation's language (or, if none is given, the language
    the text is written in), using the persona's own voice (see app/voice/voices.py)."""
    voices = voices_for(persona)
    if use_hindi_voice(text, language):
        return _synthesize_hindi(text, voices["hi"])
    return _synthesize_english(text, voices["en"])


def speak(text: str, persona: str = "online") -> None:
    """Synthesize and play immediately through local speakers (blocks until
    playback finishes). CLI-only — the hosted server never calls this."""
    import io

    import sounddevice as sd
    import soundfile as sf

    audio_bytes = synthesize(text, persona)
    data, samplerate = sf.read(io.BytesIO(audio_bytes))
    sd.play(data, samplerate)
    sd.wait()

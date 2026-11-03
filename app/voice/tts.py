"""Text-to-speech: Sarvam AI's Bulbul v4 Flash for calls and push-to-talk. The legacy voice CLI still
reads English through Groq's Orpheus.

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
import re

from groq import Groq
from sarvamai import SarvamAI

from app.agent.language import has_devanagari, use_hindi_voice
from app.voice.voices import voices_for

_groq_client = Groq(timeout=30.0, max_retries=1)
_sarvam_client = SarvamAI(timeout=30.0)  # reads SARVAM_API_KEY from the environment

ENGLISH_MODEL = "canopylabs/orpheus-v1-english"
ENGLISH_DEFAULT_VOICE = "hannah"

SARVAM_MODEL = "bulbul:v4-flash"
HINDI_LANGUAGE_CODE = "hi-IN"
ENGLISH_INDIA_LANGUAGE_CODE = "en-IN"


def group_digits(text: str) -> str:
    """12050 -> 12,050 and 100000 -> 1,00,000. Bulbul reads numbers whole when they're grouped the Indian way."""

    def grouped(match: re.Match) -> str:
        digits = match.group()
        head, tail = digits[:-3], digits[-3:]
        pairs = re.findall(r"\d{1,2}(?=(?:\d{2})*$)", head)
        return ",".join([*pairs, tail])

    return re.sub(r"(?<![\d,.])\d{4,}(?![\d,]|\.\d)", grouped, text)


def sarvam_request(text: str, persona: str = "online", sample_rate: int | None = None) -> dict:
    """What to ask Bulbul for, chosen from the sentence's script so a call can switch language. A mixed
    sentence is read with Hindi's conventions for numbers."""
    voices = voices_for(persona)
    if not has_devanagari(text):
        voice, code = voices["mixed"], ENGLISH_INDIA_LANGUAGE_CODE
    else:
        voice, code = (voices["mixed"] if re.search(r"[A-Za-z]", text) else voices["hi"]), HINDI_LANGUAGE_CODE
    request = {
        "text": group_digits(text),
        "language_code": code,
        "model": SARVAM_MODEL,
        "speaker": voice,
        "output_audio_codec": "wav",
    }
    return {**request, "speech_sample_rate": sample_rate} if sample_rate else request


def _synthesize_english(text: str, voice: str = ENGLISH_DEFAULT_VOICE) -> bytes:
    response = _groq_client.audio.speech.create(
        model=ENGLISH_MODEL,
        voice=voice,
        input=text,
        response_format="wav",
    )
    return response.read()


def synthesize(text: str, persona: str = "online", language: str | None = None) -> bytes:
    """Synthesize speech in the conversation's language (or, if none is given, the language
    the text is written in), using the persona's own voice (see app/voice/voices.py)."""
    if use_hindi_voice(text, language):
        return synthesize_sarvam(text, persona)
    return _synthesize_english(text, voices_for(persona)["en"])


def synthesize_sarvam(text: str, persona: str = "online", sample_rate: int | None = None) -> bytes:
    """The whole clip in one go. Live calls stream instead (app/voice/livekit_tts.py) so speech starts sooner."""
    result = _sarvam_client.text_to_speech.convert(**sarvam_request(text, persona, sample_rate))
    return base64.b64decode(result.audios[0])


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

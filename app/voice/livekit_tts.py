"""Wraps app.voice.tts.synthesize() (English via Groq's Orpheus, Hindi via
Sarvam's Bulbul) as a LiveKit Agents `tts.TTS`, so the realtime voice
pipeline reuses the exact same, already-tested TTS routing as the
push-to-talk and CLI paths — no second TTS integration to maintain, and no
official LiveKit plugin needed for Sarvam.

synthesize() returns a complete WAV file's bytes (not a stream), so this is
a non-streaming TTS: one `ChunkedStream._run()` call, one `push()`, one
`flush()`. `AudioEmitter` decodes whatever the WAV's actual sample rate is
(Orpheus and Sarvam needn't agree) and resamples to SAMPLE_RATE below —
see livekit.agents.tts.tts.AudioEmitter.initialize / the codecs decoder
path for the non-raw-pcm case.
"""
from __future__ import annotations

import asyncio

from livekit.agents import APIConnectOptions, utils
from livekit.agents.tts import TTS, AudioEmitter, ChunkedStream, TTSCapabilities
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from app.voice.tts import synthesize

SAMPLE_RATE = 48000
NUM_CHANNELS = 1


# Audio for short phrases that repeat (acknowledgements, the greeting), so they play at once instead of
# waiting on speech generation. Bounded: the oldest entry goes when it is full.
_PHRASE_CACHE: dict[tuple[str, str, str], bytes] = {}
_PHRASE_CACHE_MAX = 64
_PHRASE_MAX_CHARS = 60


def speak_audio(text: str, persona: str, language: str) -> bytes:
    key = (persona, language, text.strip())
    cached = _PHRASE_CACHE.get(key)
    if cached is not None:
        return cached
    audio = synthesize(text, persona, language)
    if len(key[2]) <= _PHRASE_MAX_CHARS:
        if len(_PHRASE_CACHE) >= _PHRASE_CACHE_MAX:
            _PHRASE_CACHE.pop(next(iter(_PHRASE_CACHE)))
        _PHRASE_CACHE[key] = audio
    return audio


def warm_phrases(persona: str, language: str, phrases: list[str]) -> None:
    """Generate (and cache) the audio for `phrases` ahead of time. Blocking; run it in a thread."""
    for phrase in phrases:
        try:
            speak_audio(phrase, persona, language)
        except Exception:  # a failed warm-up only means that phrase is generated when first needed
            pass


class SarthiTTS(TTS):
    def __init__(self, persona: str = "online", language: str = "en") -> None:
        super().__init__(
            capabilities=TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        self._persona = persona
        self._language = language

    @property
    def model(self) -> str:
        return "sarthi-tts"

    @property
    def provider(self) -> str:
        return "sarthi"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> SarthiChunkedStream:
        return SarthiChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class SarthiChunkedStream(ChunkedStream):
    async def _run(self, output_emitter: AudioEmitter) -> None:
        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(
            None, speak_audio, self._input_text, self._tts._persona, self._tts._language  # type: ignore[attr-defined]
        )

        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            mime_type="audio/wav",
        )
        output_emitter.push(wav_bytes)
        output_emitter.flush()

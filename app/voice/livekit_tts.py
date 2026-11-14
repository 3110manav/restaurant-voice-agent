"""Wraps app.voice.tts as a LiveKit Agents `tts.TTS`, so realtime calls reuse
the same speech code as the push-to-talk and CLI paths. Calls pass
sarvam_only=True: Sarvam's Bulbul speaks both Hindi and Indian English.

Each sentence is one `ChunkedStream._run()` call and one `flush()`, and
Sarvam's chunks are pushed as they arrive, so speech starts before the
sentence is finished. `AudioEmitter` decodes whatever the WAV's actual sample rate is
(Orpheus and Sarvam needn't agree) and resamples to SAMPLE_RATE below —
see livekit.agents.tts.tts.AudioEmitter.initialize / the codecs decoder
path for the non-raw-pcm case.
"""
from __future__ import annotations

import asyncio

from livekit.agents import APIConnectOptions, utils
from livekit.agents import tokenize
from livekit.agents import tts as lk_tts
from livekit.agents.tts import TTS, AudioEmitter, ChunkedStream, TTSCapabilities
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from sarvamai import AsyncSarvamAI

from app.voice.tts import sarvam_request, synthesize, synthesize_sarvam

SAMPLE_RATE = 48000
NUM_CHANNELS = 1


# Audio for short phrases that repeat (acknowledgements, the greeting), so they play at once instead of
# waiting on speech generation. Bounded: the oldest entry goes when it is full.
_PHRASE_CACHE: dict[tuple[str, str, bool, int | None, str], bytes] = {}
_PHRASE_CACHE_MAX = 64
_PHRASE_MAX_CHARS = 60


def _cache_key(text: str, persona: str, language: str | None, sarvam_only: bool, sample_rate: int | None) -> tuple:
    return (persona, language or "script", sarvam_only, sample_rate, text.strip())


def _remember(key: tuple, audio: bytes) -> None:
    if len(key[-1]) <= _PHRASE_MAX_CHARS:
        if len(_PHRASE_CACHE) >= _PHRASE_CACHE_MAX:
            _PHRASE_CACHE.pop(next(iter(_PHRASE_CACHE)))
        _PHRASE_CACHE[key] = audio


def speak_audio(
    text: str, persona: str, language: str | None, sarvam_only: bool = False, sample_rate: int | None = None
) -> bytes:
    key = _cache_key(text, persona, language, sarvam_only, sample_rate)
    cached = _PHRASE_CACHE.get(key)
    if cached is not None:
        return cached
    audio = synthesize_sarvam(text, persona, sample_rate) if sarvam_only else synthesize(text, persona, language)
    _remember(key, audio)
    return audio


def warm_phrases(
    persona: str, language: str | None, phrases: list[str], sarvam_only: bool = False, sample_rate: int | None = None
) -> None:
    """Generate (and cache) the audio for `phrases` ahead of time. Blocking; run it in a thread."""
    for phrase in phrases:
        try:
            speak_audio(phrase, persona, language, sarvam_only, sample_rate)
        except Exception:  # a failed warm-up only means that phrase is generated when first needed
            pass


class SarthiTTS(TTS):
    def __init__(
        self,
        persona: str = "online",
        language: str | None = "en",
        sarvam_only: bool = False,
        sample_rate: int | None = None,  # what to ask Bulbul for; None takes its default
    ) -> None:
        super().__init__(
            capabilities=TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        self._persona = persona
        self._language = language
        self._sarvam_only = sarvam_only
        self._request_rate = sample_rate
        self._sarvam = AsyncSarvamAI(timeout=30.0) if sarvam_only else None

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
        tts: SarthiTTS = self._tts  # type: ignore[assignment]
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            mime_type="audio/wav",
        )
        if tts._sarvam_only:
            await self._stream_sarvam(tts, output_emitter)
        else:
            wav_bytes = await asyncio.get_running_loop().run_in_executor(
                None, speak_audio, self._input_text, tts._persona, tts._language
            )
            output_emitter.push(wav_bytes)
        output_emitter.flush()

    async def _stream_sarvam(self, tts: SarthiTTS, output_emitter: AudioEmitter) -> None:
        """Play each chunk as it arrives, so the first word doesn't wait for the whole sentence."""
        key = _cache_key(self._input_text, tts._persona, tts._language, True, tts._request_rate)
        cached = _PHRASE_CACHE.get(key)
        if cached is not None:
            output_emitter.push(cached)
            return
        request = sarvam_request(self._input_text, tts._persona, tts._request_rate)
        chunks = []
        async for chunk in tts._sarvam.text_to_speech.convert_stream(**request):
            chunks.append(chunk)
            output_emitter.push(chunk)
        _remember(key, b"".join(chunks))


def build_speech(
    persona: str, language: str | None, sarvam_only: bool = False, sample_rate: int | None = None
) -> lk_tts.StreamAdapter:
    """The call's text-to-speech: Sarthi's voices behind an adapter that speaks each sentence as soon
    as it is ready. LiveKit's default holds any sentence under 20 characters until the next one
    arrives, which would stop the quick "Sure." from playing while the real answer is worked out."""
    return lk_tts.StreamAdapter(
        tts=SarthiTTS(persona=persona, language=language, sarvam_only=sarvam_only, sample_rate=sample_rate),
        sentence_tokenizer=tokenize.blingfire.SentenceTokenizer(
            min_sentence_len=1, stream_context_len=0, retain_format=True
        ),
    )

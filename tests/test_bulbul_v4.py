"""Bulbul v4 Flash: the right Shubh voice per sentence, numbers grouped for it, and speech streamed on calls."""
import asyncio
import io
import wave

import pytest


@pytest.fixture
def tts(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    from app.voice import tts

    return tts


@pytest.mark.parametrize(
    ("text", "voice", "code"),
    [
        ("दो नान जोड़ दिए।", "shubh_hi_customer", "hi-IN"),
        ("2 Butter Naan जोड़ दिए।", "shubh_enhi_banking", "hi-IN"),
        ("Two butter naan added.", "shubh_enhi_banking", "en-IN"),
    ],
)
def test_the_voice_follows_the_sentences_script(tts, text, voice, code):
    request = tts.sarvam_request(text, "waiter")
    assert (request["speaker"], request["language_code"], request["model"]) == (voice, code, "bulbul:v4-flash")
    assert "temperature" not in request  # v4 ignores it


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("कुल 1280 रुपये", "कुल 1,280 रुपये"),
        ("12050 rupees", "12,050 rupees"),
        ("100000 rupees", "1,00,000 rupees"),
        ("Total 560 rupees", "Total 560 rupees"),
        ("already 1,280 rupees", "already 1,280 rupees"),
        ("ending 3 2 1 0", "ending 3 2 1 0"),
        ("1250.50 rupees", "1250.50 rupees"),
    ],
)
def test_numbers_are_grouped_the_indian_way(tts, text, said):
    assert tts.group_digits(text) == said


def test_a_phone_call_asks_for_phone_quality_audio(tts):
    assert tts.sarvam_request("Sure.", "waiter", 8000)["speech_sample_rate"] == 8000
    assert "speech_sample_rate" not in tts.sarvam_request("Sure.", "waiter")


def _wav_bytes() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\0\0" * 12000)
    return out.getvalue()


def test_a_call_streams_speech_and_then_reuses_short_phrases(tts, monkeypatch):
    pytest.importorskip("livekit.agents")
    from app.voice import livekit_tts as lt

    monkeypatch.setattr(lt, "_PHRASE_CACHE", {})
    requests = []

    async def convert_stream(**request):
        requests.append(request)
        audio = _wav_bytes()
        for start in range(0, len(audio), 4096):
            yield audio[start : start + 4096]

    async def speak(speech: lt.SarthiTTS) -> float:
        seconds = 0.0
        async with speech.synthesize("ठीक है।") as stream:
            async for event in stream:
                seconds += event.frame.duration
        return seconds

    async def run() -> tuple[float, float]:
        speech = lt.SarthiTTS("waiter", None, sarvam_only=True)
        monkeypatch.setattr(speech._sarvam.text_to_speech, "convert_stream", convert_stream)
        return await speak(speech), await speak(speech)

    first, second = asyncio.run(run())
    assert first == pytest.approx(0.5, abs=0.05) and second == pytest.approx(first)
    assert len(requests) == 1 and requests[0]["speaker"] == "shubh_hi_customer"

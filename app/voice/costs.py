"""What one realtime call (LiveKit + Groq + Sarvam) cost, measured while it happens.

Every billable thing is counted where it is really spent, so the numbers are usage, not guesses:
  - speech-to-text: audio seconds LiveKit's STT metrics report (Sarvam streams the whole call)
  - text-to-speech: characters actually sent to Sarvam or Groq; a cached phrase costs nothing
  - LLM: Groq's own token counts on every reply (input, output, cached input)
  - hosting: LiveKit is self-hosted, so there is no per-minute platform fee by default. Servers are a fixed
    monthly cost; to spread them over calls, set server_per_min_inr (monthly server bill / monthly call minutes).
    For LiveKit Cloud instead, set livekit_agent_per_min_usd 0.01 and livekit_sip_per_min_usd 0.004.
Telephony (Exotel) and GST are not included.

Prices are list prices as of November 2026, in rupees, and can be changed without a deploy:
COST_PRICES is a JSON object overriding any key of PRICES (e.g. {"usd_inr": 93, "server_per_min_inr": 0.15}).
A model with no price is still counted, and reported under "unpriced".
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

logger = logging.getLogger("sarthi.voice.costs")

PRICES: dict[str, float] = {
    "usd_inr": 93.0,
    # speech-to-text, per hour of audio
    "stt_per_hour_inr:saaras:v3": 30.0,
    "stt_per_hour_inr:saaras:v4": 30.0,
    "stt_per_hour_usd:whisper-large-v3-turbo": 0.04,
    # text-to-speech, per 10,000 characters
    "tts_per_10k_chars_inr:bulbul:v4-flash": 20.0,
    # LLM, per million tokens (cached input is billed at the cached rate instead of the input rate)
    "llm_input_per_m_usd:openai/gpt-oss-120b": 0.15,
    "llm_cached_per_m_usd:openai/gpt-oss-120b": 0.075,
    "llm_output_per_m_usd:openai/gpt-oss-120b": 0.60,
    # Self-hosted LiveKit: no per-minute fee. LiveKit Cloud would be 0.01 (agent) and 0.004 (SIP).
    "livekit_agent_per_min_usd": 0.0,
    "livekit_sip_per_min_usd": 0.0,
    # Our own servers (LiveKit, SIP, worker, API), spread per call minute. 0 until there is a real bill to divide.
    "server_per_min_inr": 0.0,
}


def prices() -> dict[str, float]:
    """PRICES with COST_PRICES applied. A bad override is ignored (and logged), never fatal on a call."""
    merged = dict(PRICES)
    raw = os.environ.get("COST_PRICES", "").strip()
    if raw:
        try:
            merged.update({k: float(v) for k, v in json.loads(raw).items()})
        except (ValueError, TypeError, AttributeError):
            logger.warning("COST_PRICES isn't a JSON object of numbers; using the default prices")
    return merged


def _price_inr(table: dict, kind: str, model: str) -> float | None:
    """A per-unit price in rupees for `kind` (e.g. "stt_per_hour") and `model`, or None if not priced."""
    if f"{kind}_inr:{model}" in table:
        return table[f"{kind}_inr:{model}"]
    if f"{kind}_usd:{model}" in table:
        return table[f"{kind}_usd:{model}"] * table["usd_inr"]
    return None


class CallCost:
    """The meter for one call. Thread-safe: speech runs in executors while LiveKit events arrive."""

    def __init__(self, channel: str, speech: str = "", stt_model: str = "unknown-stt", call_id: str | None = None):
        self.channel = channel  # "browser" or "phone"
        self.speech = speech  # "sarvam" or "groq"
        self.stt_model = stt_model  # for STT metrics that don't name their model
        self.call_id = call_id
        self.started = time.monotonic()
        self.ended: float | None = None
        self.stt_seconds: dict[str, float] = {}
        self.tts_chars: dict[str, int] = {}
        self.llm: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------- counting --

    def add_stt(self, model: str, seconds: float) -> None:
        if seconds > 0:
            with self._lock:
                self.stt_seconds[model] = self.stt_seconds.get(model, 0.0) + seconds

    def add_tts(self, model: str, characters: int) -> None:
        if characters > 0:
            with self._lock:
                self.tts_chars[model] = self.tts_chars.get(model, 0) + characters

    def add_llm(self, model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> None:
        with self._lock:
            row = self.llm.setdefault(model, {"calls": 0, "input": 0, "cached": 0, "output": 0})
            row["calls"] += 1
            row["input"] += max(input_tokens - cached_tokens, 0)
            row["cached"] += cached_tokens
            row["output"] += output_tokens

    def add_llm_usage(self, model: str, usage: dict | None) -> None:
        """LangChain's usage_metadata from one Groq reply."""
        if not usage:
            return
        cached = (usage.get("input_token_details") or {}).get("cache_read") or 0
        self.add_llm(model, usage.get("input_tokens") or 0, usage.get("output_tokens") or 0, cached)

    def on_livekit_metrics(self, metrics) -> None:
        """LiveKit's metrics_collected event payload: only speech-to-text audio is counted from here (text-to-
        speech is counted where it is really generated, so cache hits stay free)."""
        if type(metrics).__name__ == "STTMetrics":
            model = getattr(getattr(metrics, "metadata", None), "model_name", None) or self.stt_model
            self.add_stt(model, float(getattr(metrics, "audio_duration", 0.0) or 0.0))

    def finish(self) -> None:
        if self.ended is None:
            self.ended = time.monotonic()

    # ------------------------------------------------------------ reporting --

    @property
    def minutes(self) -> float:
        return ((self.ended or time.monotonic()) - self.started) / 60

    def summary(self) -> dict:
        """What the call used and cost, in rupees, by part. Rounded for people, not for accounting."""
        table = prices()
        usd = table["usd_inr"]
        parts: dict[str, float] = {"stt": 0.0, "tts": 0.0, "llm": 0.0, "livekit": 0.0}
        unpriced: list[str] = []
        with self._lock:
            stt, tts, llm = dict(self.stt_seconds), dict(self.tts_chars), {k: dict(v) for k, v in self.llm.items()}

        for model, seconds in stt.items():
            rate = _price_inr(table, "stt_per_hour", model)
            if rate is None:
                unpriced.append(f"stt:{model}")
            else:
                parts["stt"] += seconds / 3600 * rate
        for model, chars in tts.items():
            rate = _price_inr(table, "tts_per_10k_chars", model)
            if rate is None:
                unpriced.append(f"tts:{model}")
            else:
                parts["tts"] += chars / 10_000 * rate
        for model, row in llm.items():
            rates = [_price_inr(table, f"llm_{k}_per_m", model) for k in ("input", "cached", "output")]
            if rates[0] is None or rates[2] is None:
                unpriced.append(f"llm:{model}")
                continue
            cached_rate = rates[1] if rates[1] is not None else rates[0]
            parts["llm"] += (row["input"] * rates[0] + row["cached"] * cached_rate + row["output"] * rates[2]) / 1e6

        minutes = self.minutes
        parts["livekit"] = minutes * (table["livekit_agent_per_min_usd"] * usd + table["server_per_min_inr"])
        if self.channel == "phone":
            parts["livekit"] += minutes * table["livekit_sip_per_min_usd"] * usd

        total = sum(parts.values())
        return {
            "type": "cost",
            "channel": self.channel,
            "speech": self.speech,
            "minutes": round(minutes, 2),
            "inr": {k: round(v, 3) for k, v in parts.items()},
            "total_inr": round(total, 2),
            "inr_per_min": round(total / minutes, 2) if minutes > 0 else None,
            "usage": {
                "stt_seconds": {k: round(v, 1) for k, v in stt.items()},
                "tts_chars": tts,
                "llm_tokens": llm,
            },
            "unpriced": unpriced,
            "excludes": "telephony and GST",
        }

    def log(self) -> dict:
        report = self.summary()
        logger.info(
            "call cost: %s %s, %.2f min, Rs %.2f (Rs %s/min) stt=%.2f tts=%.2f llm=%.2f livekit=%.2f%s",
            report["channel"], report["speech"], report["minutes"], report["total_inr"], report["inr_per_min"],
            report["inr"]["stt"], report["inr"]["tts"], report["inr"]["llm"], report["inr"]["livekit"],
            f" unpriced={report['unpriced']}" if report["unpriced"] else "",
        )
        return report

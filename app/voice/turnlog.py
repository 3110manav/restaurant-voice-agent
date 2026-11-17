"""An optional record of each spoken turn: what the agent heard and what it answered.

Off unless SARTHI_LOG_TURNS=1. When something goes wrong on a call ("it understood the wrong thing", "it made
something up"), this is what shows whether the words were heard wrongly or answered wrongly, and on which speech
stack (SARTHI_SPEECH, app/voice/stack.py).

One line per turn, to the process's normal log, so it appears wherever that is read:
  - the voice worker: LiveKit Cloud (`lk agent logs`, or the agent's Logs page in the LiveKit dashboard)
  - push-to-talk, on the API: the Render service's Logs tab
Nothing is stored in the database. Transcripts hold names and addresses, so phone-number-like digit runs are masked
and each side is clipped; turn it off again when you are done.
"""
import logging
import os
import re

logger = logging.getLogger("sarthi.turns")
_DIGIT_RUNS = re.compile(r"\d[\d\s-]{6,}\d")
_LIMIT = 280


def enabled() -> bool:
    return os.environ.get("SARTHI_LOG_TURNS", "").strip().lower() in ("1", "true", "yes", "on")


def _clip(text: str | None) -> str:
    masked = _DIGIT_RUNS.sub("<digits>", (text or "").strip())
    return masked if len(masked) <= _LIMIT else masked[:_LIMIT] + "..."


def _visible() -> None:
    # Under uvicorn nothing is set up to print our INFO lines; the worker's logging already is.
    if not logging.getLogger().handlers and not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def log_turn(
    channel: str, speech: str, language: str, heard: str, reply: str, ms: float, session_id: str | None = None
) -> None:
    """`channel` is "browser-call" or "push-to-talk"; `speech` is "groq" or "sarvam"."""
    if not enabled():
        return
    _visible()
    logger.info(
        "turn | %s | speech=%s lang=%s | %d ms | session=%s | heard=%r | reply=%r",
        channel, speech, language, ms, (session_id or "-")[:8], _clip(heard), _clip(reply),
    )

"""When a phone store takes orders (phone_stores.opening_hours, migration 011).

    {"daily": [["11:00", "23:30"]], "mon": []}

Times are Indian time. A closing time earlier than the opening time runs past midnight ("19:00"-"01:00"). A day not
listed uses "daily"; an empty list means shut that day. A store without hours is always open, so nothing changes
until an owner sets them.
"""
from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _clock(text: str) -> time:
    hours, minutes = str(text).strip().split(":")
    return time(int(hours) % 24, int(minutes))


def _sittings(hours: dict, day: datetime) -> list[tuple[datetime, datetime]]:
    """The open periods that start on this calendar day, as datetimes (a late close lands on the next day)."""
    spans = hours.get(DAYS[day.weekday()], hours.get("daily", []))
    periods = []
    for span in spans or []:
        try:
            start, end = _clock(span[0]), _clock(span[1])
        except (ValueError, IndexError, TypeError):
            continue
        opens = datetime.combine(day.date(), start, IST)
        closes = datetime.combine(day.date(), end, IST)
        if closes <= opens:
            closes += timedelta(days=1)
        periods.append((opens, closes))
    return periods


def is_open(store: dict, now: datetime | None = None) -> bool:
    hours = store.get("opening_hours")
    if not hours:
        return True
    now = (now or datetime.now(IST)).astimezone(IST)
    # Yesterday's late sitting may still be running after midnight.
    return any(opens <= now < closes for day in (now - timedelta(days=1), now) for opens, closes in _sittings(hours, day))


def next_opening(store: dict, now: datetime | None = None) -> datetime | None:
    hours = store.get("opening_hours")
    if not hours:
        return None
    now = (now or datetime.now(IST)).astimezone(IST)
    upcoming = [opens for offset in range(8) for opens, _ in _sittings(hours, now + timedelta(days=offset)) if opens > now]
    return min(upcoming) if upcoming else None


def closed_message(store: dict, now: datetime | None = None) -> tuple[str, str]:
    """What to tell a caller when the store is shut, in Hindi and English."""
    now = (now or datetime.now(IST)).astimezone(IST)
    opens = next_opening(store, now)
    name = store["name"]
    if opens is None:
        return f"माफ़ कीजिए, {name} अभी ऑर्डर नहीं ले रहा है।", f"Sorry, {name} isn't taking orders right now."
    clock = opens.strftime("%I:%M").lstrip("0").replace(":00", "")
    if opens.date() == now.date():
        when_hi, when_en = f"आज {clock} बजे", f"today at {opens.strftime('%I:%M %p').lstrip('0')}"
    elif opens.date() == now.date() + timedelta(days=1):
        when_hi, when_en = f"कल {clock} बजे", f"tomorrow at {opens.strftime('%I:%M %p').lstrip('0')}"
    else:
        when_hi, when_en = f"{opens.strftime('%A')} को {clock} बजे", f"on {opens.strftime('%A at %I:%M %p')}"
    return (
        f"माफ़ कीजिए, {name} अभी बंद है। हम {when_hi} खुलेंगे, तब ऑर्डर कर दीजिए।",
        f"Sorry, {name} is closed right now. We open {when_en}; please order then.",
    )


def parse(text: str) -> list[list[str]]:
    """'11:00-23:30' or '12:00-15:30, 19:00-01:00' -> [["11:00", "23:30"], ...]; 'closed' -> []."""
    text = text.strip().lower()
    if text in ("", "closed", "shut"):
        return []
    spans = []
    for part in text.split(","):
        start, end = (p.strip() for p in part.split("-"))
        _clock(start), _clock(end)  # raises on a bad time
        spans.append([start, end])
    return spans

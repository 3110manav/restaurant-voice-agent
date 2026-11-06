"""The table QR pilot's arithmetic, free of I/O so it is easy to test: which cart lines are new
since the last round sent to the kitchen, the bill, the turn tracker's stages, the owner's
Tonight view and the monthly report.

A table session's five moments are seated, first order, food served, bill asked and paid. The
four waits between them are the turn tracker's stages.
"""
import math
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))  # pilot restaurants report in Indian time
LONG_WAIT_MINUTES = 25  # waiting this long for food marks the table on the Tonight screen

STAGES = (
    ("seated_to_ordered", "seated_at", "first_order_at"),
    ("ordered_to_food", "first_order_at", "food_served_at"),
    ("food_to_bill", "food_served_at", "bill_requested_at"),
    ("bill_to_paid", "bill_requested_at", "paid_at"),
)
MOMENTS = ("seated_at", "first_order_at", "food_served_at", "bill_requested_at", "paid_at")


# --------------------------------------------------------------- cart lines --


def line_key(line: dict) -> tuple[str, str]:
    return line["id"], (line.get("variant") or "").strip().lower()


def unplaced(cart: list[dict], placed: list[dict]) -> list[dict]:
    """The part of `cart` the kitchen hasn't been sent yet: new dishes, and extra quantity of
    dishes already sent. Removing a dish after it was sent doesn't take it back from the kitchen."""
    sent: dict[tuple[str, str], int] = {}
    for line in placed:
        sent[line_key(line)] = sent.get(line_key(line), 0) + int(line["quantity"])
    fresh = []
    for line in cart:
        key = line_key(line)
        already = sent.get(key, 0)
        quantity = int(line["quantity"]) - already
        sent[key] = max(already - int(line["quantity"]), 0)
        if quantity > 0:
            fresh.append({**line, "quantity": quantity})
    return fresh


def merge_lines(ordered: list[dict], lines: list[dict]) -> list[dict]:
    merged = [dict(line) for line in ordered]
    for line in lines:
        for existing in merged:
            if line_key(existing) == line_key(line):
                existing["quantity"] = int(existing["quantity"]) + int(line["quantity"])
                break
        else:
            merged.append(dict(line))
    return merged


def lines_total(lines: list[dict]) -> float:
    return float(sum(float(line["price"]) * int(line["quantity"]) for line in lines))


# ---------------------------------------------------------------------- bill --


def bill(lines: list[dict], gst_rate: float, people: int) -> dict:
    """The table's bill: every round sent to the kitchen, GST on top, and each person's share
    when split equally (rounded up to the rupee, so the shares never fall short)."""
    people = min(max(int(people or 1), 1), 50)
    subtotal = lines_total(lines)
    gst = round(subtotal * float(gst_rate) / 100)
    total = subtotal + gst
    return {
        "lines": [
            {
                "id": line["id"],
                "name": line["name"],
                "variant": line.get("variant"),
                "quantity": int(line["quantity"]),
                "price": float(line["price"]),
                "line_total": float(line["price"]) * int(line["quantity"]),
            }
            for line in lines
        ],
        "subtotal": subtotal,
        "gst_rate": float(gst_rate),
        "gst": float(gst),
        "total": float(total),
        "people": people,
        "share": float(math.ceil(total / people)) if total else 0.0,
    }


# ------------------------------------------------------------- turn tracker --


def parse_time(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def minutes_between(row: dict, start: str, end: str) -> float | None:
    a, b = parse_time(row.get(start)), parse_time(row.get(end))
    if a is None or b is None or b < a:
        return None
    return (b - a).total_seconds() / 60


def _average(values: list[float]) -> int | None:
    return round(sum(values) / len(values)) if values else None


def stage_averages(rows: list[dict]) -> dict:
    averages = {name: _average([m for r in rows if (m := minutes_between(r, a, b)) is not None]) for name, a, b in STAGES}
    averages["turn"] = _average([m for r in rows if (m := minutes_between(r, "seated_at", "paid_at")) is not None])
    return averages


def table_state(row: dict, now: datetime) -> str:
    if row.get("paid_at"):
        return "paid"
    if row.get("bill_requested_at"):
        return "bill"
    if row.get("food_served_at"):
        return "eating"
    if row.get("first_order_at"):
        ordered = parse_time(row["first_order_at"])
        return "long" if ordered and (now - ordered).total_seconds() / 60 >= LONG_WAIT_MINUTES else "food"
    return "ordering"


def tonight(rows: list[dict], now: datetime) -> dict:
    """The owner's live view: every table still open, and tonight's average waits."""
    tables = []
    for row in rows:
        if row.get("status") == "closed" or row.get("paid_at"):
            continue
        seated = parse_time(row.get("seated_at"))
        tables.append(
            {
                "id": row["id"],
                "table_no": row.get("table_no"),
                "state": table_state(row, now),
                "minutes": round((now - seated).total_seconds() / 60) if seated else None,
                "amount": lines_total(row.get("ordered") or []),
                "rounds": int(row.get("rounds") or 0),
                "payment_method": row.get("payment_method"),
            }
        )
    tables.sort(key=lambda t: (_table_sort_key(t["table_no"]), -(t["minutes"] or 0)))
    return {"tables": tables, "averages": stage_averages(rows), "sessions": len(rows)}


def _table_sort_key(table_no) -> tuple[int, str]:
    text = str(table_no or "")
    return (int(text), "") if text.isdigit() else (10**6, text)


# ------------------------------------------------------------ monthly report --


def month_bounds(month: str | None, now: datetime) -> tuple[datetime, datetime, str]:
    """`YYYY-MM` (Indian time) as a [start, end) pair in UTC; this month when absent or invalid."""
    local = now.astimezone(IST)
    year, mon = local.year, local.month
    if month:
        try:
            year, mon = (int(part) for part in month.split("-", 1))
            if not 1 <= mon <= 12:
                raise ValueError
        except ValueError:
            year, mon = local.year, local.month
    start = datetime(year, mon, 1, tzinfo=IST)
    end = datetime(year + (mon == 12), mon % 12 + 1, 1, tzinfo=IST)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc), f"{year:04d}-{mon:02d}"


def report(rows: list[dict], orders: int, customers: list[dict], start: datetime, end: datetime, baseline: int | None) -> dict:
    """What Sarthi did for the restaurant in one month, from that month's table sessions."""
    served = [r for r in rows if r.get("first_order_at")]
    ratings = [int(r["rating"]) for r in rows if r.get("rating")]
    new_customers = [
        c for c in customers if (seen := parse_time(c.get("first_seen_at"))) is not None and start <= seen < end
    ]
    averages = stage_averages(rows)
    return {
        "tables_served": len(served),
        "table_orders": orders,
        "upsell_total": float(sum(float(r.get("upsell_total") or 0) for r in rows)),
        "averages": averages,
        "baseline_turn_minutes": baseline,
        "turn_saved_minutes": (baseline - averages["turn"]) if baseline and averages["turn"] is not None else None,
        "new_customers": len(new_customers),
        "new_customers_opted_in": sum(1 for c in new_customers if c.get("offers_opt_in")),
        "ratings": len(ratings),
        "average_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "complaints": sum(1 for r in rows if r.get("feedback")),
    }

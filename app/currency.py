"""Single place that decides how a price is written, so changing currency
again is a one-file edit on the backend (web/src/lib/utils.ts has the
frontend's counterpart)."""

CURRENCY_SYMBOL = "₹"


def format_price(amount: float) -> str:
    return f"{CURRENCY_SYMBOL}{amount:,.0f}"

"""In-restaurant service tools for the waiter persona.

These cover the ambient requests a physical waiter handles beyond taking
an order: bringing items, flagging a problem with food, getting the bill,
or just calling a human over. Each call appends to a per-session service
log (closed over like the cart) and, when Supabase is configured, also
persists to the `requests` table (see app/erp.py) for a staff-facing view.
"""
from langchain_core.tools import tool

from app import erp
from app.currency import format_price

ServiceRequest = dict  # {"type": str, "details": str, "notes": str}


def build_service_tools(
    service_log: list[ServiceRequest],
    session_id: str = "",
    persona: str = "",
    restaurant_id: str | None = None,
    table_no: str | None = None,
    cart: list[dict] | None = None,
    events: list[dict] | None = None,
) -> list:
    """`cart` lets the bill request say the table's total; `events` records what happened so simple
    turns can be answered in code (app/agent/replies.py)."""

    def note(event: dict) -> None:
        if events is not None:
            events.append(event)

    def _log(request_type: str, details: str = "", notes: str = "") -> None:
        service_log.append({"type": request_type, "details": details, "notes": notes})
        erp.record_request(
            session_id, persona, request_type, details, notes, restaurant_id=restaurant_id, table_no=table_no
        )

    @tool
    def request_item(item: str, notes: str = "") -> str:
        """Bring a non-menu item: water, napkins, cutlery, a highchair, condiments. Not for menu
        food or drinks (use add_to_cart).
        """
        _log("item_request", item, notes)
        note({"type": "item_request", "item": item})
        return f"Got it, bringing {item} right away."

    @tool
    def flag_issue(item: str, issue: str) -> str:
        """Report a problem with food or service already served: wrong item, cold, too spicy,
        undercooked. Goes to the kitchen and staff.
        """
        _log("issue", item, issue)
        note({"type": "issue", "item": item})
        return f"Sorry about that — letting the kitchen know about the {item} ({issue}) now."

    @tool
    def request_bill() -> str:
        """Request the bill/check for the table."""
        _log("bill_request")
        total = sum(line["price"] * line["quantity"] for line in cart) if cart else 0
        note({"type": "bill", "total": total or None})
        if total:
            return f"Sure, I'll bring the bill over shortly. The table's total is {format_price(total)}: tell the guest the total."
        return "Sure, I'll bring the bill over shortly."

    @tool
    def call_staff(reason: str = "") -> str:
        """Call a staff member over for anything else: a question or complaint that isn't a
        specific item, food issue or the bill.
        """
        _log("call_staff", reason)
        note({"type": "staff"})
        return "Someone will be right with you."

    return [request_item, flag_issue, request_bill, call_staff]

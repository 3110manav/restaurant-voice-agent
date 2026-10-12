"""In-restaurant service tools for the waiter persona.

These cover the ambient requests a physical waiter handles beyond taking
an order: bringing items, flagging a problem with food, getting the bill,
or just calling a human over. Each call appends to a per-session service
log (closed over like the cart) and, when Supabase is configured, also
persists to the `requests` table (see app/erp.py) for a staff-facing view.
"""
from langchain_core.tools import tool

from app import erp

ServiceRequest = dict  # {"type": str, "details": str, "notes": str}


def build_service_tools(service_log: list[ServiceRequest], session_id: str = "", persona: str = "") -> list:
    def _log(request_type: str, details: str = "", notes: str = "") -> None:
        service_log.append({"type": request_type, "details": details, "notes": notes})
        erp.record_request(session_id, persona, request_type, details, notes)

    @tool
    def request_item(item: str, notes: str = "") -> str:
        """Request a non-menu item a waiter would normally bring: water, napkins,
        extra cutlery, a highchair, condiments, etc. Not for ordering food or
        drinks off the menu — use add_to_cart for that.
        """
        _log("item_request", item, notes)
        return f"Got it, bringing {item} right away."

    @tool
    def flag_issue(item: str, issue: str) -> str:
        """Flag a problem with food or service already served: wrong item, food
        is cold, too spicy, undercooked, needs reheating, etc. Routes to the
        kitchen/staff.
        """
        _log("issue", item, issue)
        return f"Sorry about that — letting the kitchen know about the {item} ({issue}) now."

    @tool
    def request_bill() -> str:
        """Request the bill/check for the table."""
        _log("bill_request")
        return "Sure, I'll bring the bill over shortly."

    @tool
    def call_staff(reason: str = "") -> str:
        """Call a human staff member over for anything that isn't a specific
        item, food issue, or the bill — e.g. a general question or complaint.
        """
        _log("call_staff", reason)
        return "Someone will be right with you."

    return [request_item, flag_issue, request_bill, call_staff]

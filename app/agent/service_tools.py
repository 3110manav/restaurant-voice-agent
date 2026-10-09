"""In-restaurant service tools for the waiter persona.

These cover the ambient requests a physical waiter handles beyond taking
an order: bringing items, flagging a problem with food, getting the bill,
or just calling a human over. Each call appends to a per-session service
log (closed over like the cart) — a real deployment would surface that
log on a staff-facing dashboard; that's out of scope here.
"""
from langchain_core.tools import tool

ServiceRequest = dict  # {"type": str, "details": str}


def build_service_tools(service_log: list[ServiceRequest]) -> list:
    @tool
    def request_item(item: str, notes: str = "") -> str:
        """Request a non-menu item a waiter would normally bring: water, napkins,
        extra cutlery, a highchair, condiments, etc. Not for ordering food or
        drinks off the menu — use add_to_cart for that.
        """
        service_log.append({"type": "item_request", "details": item, "notes": notes})
        return f"Got it, bringing {item} right away."

    @tool
    def flag_issue(item: str, issue: str) -> str:
        """Flag a problem with food or service already served: wrong item, food
        is cold, too spicy, undercooked, needs reheating, etc. Routes to the
        kitchen/staff.
        """
        service_log.append({"type": "issue", "details": item, "notes": issue})
        return f"Sorry about that — letting the kitchen know about the {item} ({issue}) now."

    @tool
    def request_bill() -> str:
        """Request the bill/check for the table."""
        service_log.append({"type": "bill_request", "details": "", "notes": ""})
        return "Sure, I'll bring the bill over shortly."

    @tool
    def call_staff(reason: str = "") -> str:
        """Call a human staff member over for anything that isn't a specific
        item, food issue, or the bill — e.g. a general question or complaint.
        """
        service_log.append({"type": "call_staff", "details": reason, "notes": ""})
        return "Someone will be right with you."

    return [request_item, flag_issue, request_bill, call_staff]

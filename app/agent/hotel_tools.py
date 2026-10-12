"""Hotel front-desk / in-room service tools for the hotel persona.

Room-service food ordering reuses the ordering tools from tools.py (same
pattern as the waiter persona) — these cover everything else a hotel
front desk handles: housekeeping, reporting a room problem, starting
checkout, or calling staff over for anything else. Each call appends to
a per-session service log (closed over like the cart) and, when Supabase
is configured, also persists to the `requests` table (see app/erp.py) for
a staff-facing view.
"""
from langchain_core.tools import tool

from app import erp

ServiceRequest = dict  # {"type": str, "details": str, "notes": str}


def build_hotel_tools(service_log: list[ServiceRequest], session_id: str = "", persona: str = "") -> list:
    def _log(request_type: str, details: str = "", notes: str = "") -> None:
        service_log.append({"type": request_type, "details": details, "notes": notes})
        erp.record_request(session_id, persona, request_type, details, notes)

    @tool
    def request_housekeeping(item: str, notes: str = "") -> str:
        """Request a housekeeping item or service: extra towels, fresh linens,
        room cleaning, a wake-up call, an iron, extra pillows, toiletries, etc.
        Not for food or drinks — use add_to_cart for room service orders.
        """
        _log("housekeeping", item, notes)
        return f"Got it, sending housekeeping for {item} shortly."

    @tool
    def report_issue(issue: str) -> str:
        """Report a problem with the room: AC not working, no hot water, a
        noise complaint, something broken, etc. Routes to maintenance/front desk.
        """
        _log("issue", issue)
        return f"Sorry about that — I've let the team know: {issue}."

    @tool
    def request_checkout(room_number: str = "") -> str:
        """Start the checkout process for the guest's room."""
        _log("checkout_request", room_number)
        return "Sure, I'll get your checkout started — the front desk will confirm shortly."

    @tool
    def call_staff(reason: str = "") -> str:
        """Call the front desk over for anything else that doesn't fit the
        other tools — a general question, request, or complaint.
        """
        _log("call_staff", reason)
        return "Someone from the front desk will be with you shortly."

    return [request_housekeeping, report_issue, request_checkout, call_staff]

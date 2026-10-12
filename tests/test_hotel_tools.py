"""Tests for the hotel persona's service tools (no LLM/API calls needed)."""
from app.agent.hotel_tools import build_hotel_tools


def make_tools():
    service_log = []
    tools = {t.name: t for t in build_hotel_tools(service_log)}
    return service_log, tools


def test_request_housekeeping_logs_request():
    service_log, tools = make_tools()
    tools["request_housekeeping"].invoke({"item": "extra towels", "notes": "room 204"})
    assert service_log == [{"type": "housekeeping", "details": "extra towels", "notes": "room 204"}]


def test_report_issue_logs_issue():
    service_log, tools = make_tools()
    tools["report_issue"].invoke({"issue": "AC not working"})
    assert service_log == [{"type": "issue", "details": "AC not working", "notes": ""}]


def test_request_checkout_logs_request():
    service_log, tools = make_tools()
    result = tools["request_checkout"].invoke({"room_number": "204"})
    assert service_log == [{"type": "checkout_request", "details": "204", "notes": ""}]
    assert "checkout" in result.lower()


def test_call_staff_logs_request():
    service_log, tools = make_tools()
    tools["call_staff"].invoke({"reason": "need directions"})
    assert service_log == [{"type": "call_staff", "details": "need directions", "notes": ""}]

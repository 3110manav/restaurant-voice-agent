"""Opening hours: no new order while the store is shut, and the caller is told when it opens."""
from datetime import datetime

from app.phone import hours

IST = hours.IST
STORE = {"name": "Borivali Biryani Centre", "opening_hours": {"daily": [["12:00", "15:30"], ["19:00", "01:00"]], "mon": []}}


def at(day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 11, day, hh, mm, tzinfo=IST)  # 23 Nov 2026 is a Monday


def test_a_store_without_hours_is_always_open():
    assert hours.is_open({"name": "x"}) and hours.is_open({"name": "x", "opening_hours": None})


def test_open_and_closed_through_the_day():
    assert hours.is_open(STORE, at(22, 13))          # Sunday lunch
    assert not hours.is_open(STORE, at(22, 17))      # between sittings
    assert hours.is_open(STORE, at(22, 23, 59))      # the late sitting runs past midnight...
    assert hours.is_open(STORE, at(23, 0, 30))       # ...into Monday, though Monday itself is shut
    assert not hours.is_open(STORE, at(23, 13))      # Monday: closed


def test_the_caller_hears_when_it_opens():
    hindi, english = hours.closed_message(STORE, at(22, 17))
    assert "आज 7 बजे" in hindi and "today at 7:00 PM" in english
    hindi, english = hours.closed_message(STORE, at(23, 13))  # Monday shut: Tuesday noon
    assert "कल 12 बजे" in hindi and "tomorrow" in english


def test_hours_are_written_the_way_an_owner_says_them():
    assert hours.parse("11:00-23:30") == [["11:00", "23:30"]]
    assert hours.parse("12:00-15:30, 19:00-01:00") == [["12:00", "15:30"], ["19:00", "01:00"]]
    assert hours.parse("closed") == []

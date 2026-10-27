"""Replies the waiter writes in code instead of asking the model.

After most order and service actions the model's second call only restates what the tool just did
("Added a Large Margherita and a Garlic Bread"). That call costs about 0.7s and a lot of tokens, and
can restate it wrongly. So when every action of a turn succeeded and was one of the simple ones
(add, remove, checkout, bring an item, flag a problem, call staff, the bill), the tools record what
happened as events and `compose` turns them into the reply, in English or Hindi. Anything unusual
(a dish that needs a size, an ambiguous name, an unavailable dish, a question) still goes to the model.

The waiter does not talk money unprompted: confirmations carry no prices, and only the bill
request says the total.
"""
import re

from app.agent.language import normalize

FAST_TOOLS = {"add_to_cart", "remove_from_cart", "checkout", "request_item", "flag_issue", "request_bill", "call_staff"}

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> str:
    """1280 -> "one thousand two hundred eighty" (spoken amounts read better as words)."""
    n = int(round(n))
    if n < 0 or n >= 100000:
        return str(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + (f" {_ONES[n % 10]}" if n % 10 else "")
    if n < 1000:
        return f"{_ONES[n // 100]} hundred" + (f" {number_words(n % 100)}" if n % 100 else "")
    return f"{number_words(n // 1000)} thousand" + (f" {number_words(n % 1000)}" if n % 1000 else "")


# ------------------------------------------------------------ which requests the events must cover

_PHRASES = {
    "service": re.compile(
        r"\b(water|napkins?|tissues?|cutlery|fork|spoon|knife|straw|ketchup|highchair|high chair|plate|glass|salt|"
        r"pepper|toothpick|paani|pani)\b|पानी|नैपकिन|चम्मच|टिशू",
        re.I,
    ),
    "bill": re.compile(r"\b(bill|check please|the check)\b|बिल", re.I),
    "remove": re.compile(r"\b(remove|cancel|take (it |that )?off|delete)\b|हटा", re.I),
    "checkout": re.compile(
        r"\b(check ?out|place (the |my |our )?order|that'?s (all|it|everything)|that is (all|it|everything)|"
        r"done ordering|confirm (the |my |our )?order)\b|बस इतना|ऑर्डर कर दो|ऑर्डर कन्फ़र्म",
        re.I,
    ),
    # A clear order verb. A dish named in the message also counts (see requested_groups), so "can we
    # have the bill" is not mistaken for an order.
    "order": re.compile(r"\b(add|order (a|an|one|two|three|\d)|i want|we want|i'?ll (have|take)|we'?ll (have|take)|chahiye)\b|चाहिए|जोड़|डाल", re.I),
}
_EVENT_GROUP = {
    "added": "order",
    "removed": "remove",
    "checkout": "checkout",
    "checkout_held": "checkout",
    "bill": "bill",
    "item_request": "service",
    "issue": "service",
    "staff": "service",
}


def requested_groups(text: str, dish_names: tuple[str, ...] | list[str] = ()) -> set[str]:
    """The kinds of request a guest's message seems to contain (an order, a service item, the bill...)."""
    cleaned = _PHRASES["checkout"].sub(" ", text)  # "place the order" is not an order for food
    found = {name for name, pattern in _PHRASES.items() if pattern.search(cleaned)}
    if _PHRASES["checkout"].search(text):
        found.add("checkout")
    lowered = text.lower()
    if any(name and name in lowered for name in dish_names):
        found.add("order")
    return found


def covers_request(events: list[dict], user_text: str, dish_names: tuple[str, ...] | list[str] = ()) -> bool:
    """Did the actions taken cover every kind of request in the message? If the guest asked for
    water and to add a naan but only one happened, the model must carry on, so no shortcut."""
    done = {_EVENT_GROUP[e["type"]] for e in events if e["type"] in _EVENT_GROUP}
    return requested_groups(user_text, dish_names) <= done


# ------------------------------------------------------------ the sentences

def _quantity(n: int, language: str) -> str:
    return str(n) if language == "hi" or n > 20 else number_words(n)


def _label(line: dict) -> str:
    return f"{line['variant']} {line['name']}" if line.get("variant") else line["name"]


def _join(parts: list[str], language: str) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    word = "और" if language == "hi" else "and"
    return f"{', '.join(parts[:-1])} {word} {parts[-1]}"


def _added(event: dict, language: str) -> str:
    items = _join([f"{_quantity(l['quantity'], language)} {_label(l)}" for l in event["lines"]], language)
    return f"{items} जोड़ दिया गया है।" if language == "hi" else f"Added {items}."


def _removed(event: dict, language: str) -> str:
    label = _label(event)
    if event["remaining"] > 0:
        n = _quantity(event["remaining"], language)
        return f"{label} अब {n} रह गया है।" if language == "hi" else f"Updated {label}, now {n}."
    return f"{label} हटा दिया गया है।" if language == "hi" else f"Removed {label}."


def _offer(event: dict, language: str) -> str:
    hi = language == "hi"
    if event["kind"] == "dessert":
        names = (" या " if hi else " or ").join(event["desserts"])
        return f"ऑर्डर देने से पहले, मीठे में {names} लेंगे?" if hi else f"Before I place your order, would you like to end with {names}?"
    drinks = " या ".join(event["drinks"]) if hi else " or ".join(event["drinks"])
    sides = event["sides"][0] if event["sides"] else None
    if hi:
        if drinks and sides:
            return f"साथ में {drinks} लेंगे, या {sides} भी?"
        return f"साथ में {drinks} लेंगे?" if drinks else f"साथ में {sides} भी लेंगे?"
    if drinks and sides:
        return f"Would you like {drinks} with that, or maybe some {sides} on the side?"
    return f"Would you like {drinks} with that?" if drinks else f"Would you like some {sides} on the side?"


def compose(events: list[dict], language: str) -> str | None:
    """The reply for a turn made only of simple, successful actions, or None to let the model write it."""
    language = normalize(language)
    hi = language == "hi"
    if not events or any(e["type"] == "problem" for e in events):
        return None
    parts: list[str] = []
    asked_something = False
    for e in events:
        kind = e["type"]
        if kind == "added":
            parts.append(_added(e, language))
        elif kind == "removed":
            parts.append(_removed(e, language))
        elif kind == "offer":
            parts.append(_offer(e, language))
            asked_something = True
        elif kind == "checkout_held":
            pass  # the dessert offer that follows is the reply
        elif kind == "checkout":
            parts.append("आपका ऑर्डर दे दिया गया है, धन्यवाद!" if hi else "Your order is placed. Thank you!")
        elif kind == "bill":
            total = e.get("total")
            if total:
                amount = f"{round(total)} रुपये" if hi else f"{number_words(total)} rupees"
                parts.append(f"आपका कुल {amount} हुआ। बिल अभी लाते हैं।" if hi else f"Your total comes to {amount}. I'll bring the bill over.")
            else:
                parts.append("बिल अभी लाते हैं।" if hi else "I'll bring the bill over right away.")
        elif kind == "item_request":
            parts.append(f"ठीक है, {e['item']} अभी लाते हैं।" if hi else f"Sure, {e['item']} is on its way.")
        elif kind == "issue":
            parts.append(
                f"माफ़ कीजिए, किचन को {e['item']} के बारे में बता दिया है।"
                if hi
                else f"Sorry about that, I've let the kitchen know about the {e['item']}."
            )
        elif kind == "staff":
            parts.append("कोई अभी आपके पास आता है।" if hi else "Someone will be right with you.")
    if not parts:
        return None
    if events[-1]["type"] == "added" and not asked_something:
        parts.append("और कुछ?" if hi else "Anything else?")
    return " ".join(parts)

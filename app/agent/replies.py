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

from app.agent.language import line as lang_line, normalize

FAST_TOOLS = {
    "add_to_cart", "remove_from_cart", "checkout", "request_item", "flag_issue", "request_bill", "call_staff",
    "save_delivery_details", "choose_pickup", "choose_prescription_path",
}

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
    # Answers to a question the shop asked ("I want to pick it up", "I want to talk to the pharmacist") are not new orders.
    "details_saved": "order",
    "pickup_chosen": "order",
    "rx_path_chosen": "order",
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


def _spoken_name(name: str) -> str:
    """"Dolo 650 Tablet (strip of 15)" is read as "Dolo 650 Tablet": the pack detail is for the screen, not the ear."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip() or name


def _label(line: dict) -> str:
    name = _spoken_name(line["name"])
    return f"{line['variant']} {name}" if line.get("variant") else name


def _join(parts: list[str], language: str) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    word = "और" if language == "hi" else "and"
    return f"{', '.join(parts[:-1])} {word} {parts[-1]}"


def _added(event: dict, language: str) -> str:
    hi = language == "hi"
    # One of something is just its name; more than one says how many ("Done, two Dolo 650 and an ORS").
    items = _join([(_label(l) if l["quantity"] == 1 else f"{_quantity(l['quantity'], language)} {_label(l)}") for l in event["lines"]], language)
    text = f"हो गया, {items} जोड़ दिया।" if hi else f"Done, {items}."
    if any(l.get("rx") for l in event["lines"]):  # a pharmacy item that needs a prescription
        text += (
            " इसके लिए पर्चा चाहिए, भेजने से पहले हमारे फार्मासिस्ट उसे देख लेंगे।"
            if hi
            else " That one needs a prescription, and our pharmacist will check it before it goes out."
        )
    return text


def spoken_digits(number: str | None) -> str:
    """+919876543210 -> "9 8 7 6 5, 4 3 2 1 0": a phone number, said in two groups of five."""
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    if len(digits) > 10:
        digits = digits[-10:]  # drop the country code: it is said in India without it
    if len(digits) != 10:
        return " ".join(digits)
    return f"{' '.join(digits[:5])}, {' '.join(digits[5:])}"


def _placed(event: dict, language: str) -> str:
    """The order-placed line. Stores say the total and where it is going: "All set! That's fifty four rupees,
    coming to you in Bandra West." """
    hi = language == "hi"
    total, area, kind = event.get("total"), event.get("area"), event.get("fulfilment")
    money = ""
    if event.get("say_total") and total:
        money = f"कुल {round(total)} रुपये" if hi else f"That's {number_words(total)} rupees"
    if kind == "delivery":
        where = (f"{area} में भेज रहे हैं" if area else "आपके पते पर भेज रहे हैं") if hi else (f"coming to you in {area}" if area else "coming to your address")
    elif kind == "pickup":
        where = "आप आकर ले सकते हैं" if hi else "ready for you to pick up"
    else:
        where = ""
    detail = ", ".join(x for x in (money, where) if x)
    if detail:
        text = ("हो गया!" if hi else "All set!") + f" {detail}{'।' if hi else '.'}"
    else:  # a guest at a table: say plainly that the kitchen has it
        text = "हो गया, ऑर्डर किचन में चला गया है।" if hi else "All set, your order is in."
    alerted, number, where_chat = event.get("wa_alerted"), event.get("wa_number"), event.get("wa_channel")
    if event.get("rx_path") == "whatsapp":
        if where_chat != "whatsapp" and number:
            # A phone call or the website: the customer is not in a WhatsApp chat with the shop yet, so tell them
            # where to send the photo. Messaging the shop first also opens the chat for the order updates.
            text += (
                f" कृपया पर्चे की फोटो दुकान के व्हाट्सऐप नंबर {spoken_digits(number)} पर भेज दीजिए, फार्मासिस्ट देखकर ऑर्डर कन्फ़र्म करेंगे।"
                if hi
                else f" Please send a clear photo of the prescription to the shop's WhatsApp number, {spoken_digits(number)}, and our pharmacist will check it and confirm the order."
            )
        else:
            text += (
                " पर्चे की साफ़ फोटो व्हाट्सऐप पर भेज दीजिए, फार्मासिस्ट देखकर ऑर्डर कन्फ़र्म करेंगे।"
                if hi
                else " Please send a clear photo of the prescription on WhatsApp, and our pharmacist will check it and confirm the order."
            )
    elif event.get("rx_path") == "pharmacist":
        text += " हमारे फार्मासिस्ट आपको जल्दी कॉल करेंगे।" if hi else " Our pharmacist will call you shortly."
    elif alerted and kind in ("delivery", "pickup"):
        text += " मैंने आपका ऑर्डर दुकान को व्हाट्सऐप पर भेज दिया है।" if hi else " I've sent your order to the shop on WhatsApp."
    return text + (" धन्यवाद!" if hi else " Thanks!")


def _removed(event: dict, language: str) -> str:
    label = _label(event)
    if event["remaining"] > 0:
        n = _quantity(event["remaining"], language)
        return f"ठीक है, {label} अब {n} रह गया।" if language == "hi" else f"Done, {label} is now {n}."
    return f"ठीक है, {label} हटा दिया।" if language == "hi" else f"Done, removed {label}."


def _offer(event: dict, language: str) -> str:
    hi = language == "hi"
    if event["kind"] == "dessert":
        names = (" या " if hi else " or ").join(event["desserts"])
        return f"ऑर्डर देने से पहले, मीठे में {names} लेंगे?" if hi else f"Before I place it, would you like {names} to finish?"
    drinks = " या ".join(event["drinks"]) if hi else " or ".join(event["drinks"])
    sides = event["sides"][0] if event["sides"] else None
    if hi:
        if drinks and sides:
            return f"साथ में {drinks} लेंगे, या {sides} भी?"
        return f"साथ में {drinks} लेंगे?" if drinks else f"साथ में {sides} भी लेंगे?"
    if drinks and sides:
        return f"Want {drinks} with that, or some {sides} on the side?"
    return f"Want {drinks} with that?" if drinks else f"Want some {sides} on the side?"


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
            pass  # the offer, or the request for the delivery details, that follows is the reply
        elif kind == "details_saved":
            # Read back exactly what was saved (code, not the model, so a name is never misspelt).
            first = (e.get("name") or "").split(" ")[0]
            if hi:
                parts.append(f"धन्यवाद{' ' + first if first else ''}। पता: {e['line']}। क्या यह सही है?")
            else:
                parts.append(f"Thanks{', ' + first if first else ''}. Got it: {e['line']}. Is that right?")
            asked_something = True
        elif kind == "pickup_chosen":
            parts.append("ठीक है, आप खुद आकर ले लेंगे। ऑर्डर दे दें?" if hi else "Got it, you'll pick it up. Shall I place it?")
            asked_something = True
        elif kind == "rx_choice_needed":
            parts.append(lang_line(language, "rx_choice"))
            asked_something = True
        elif kind == "rx_path_chosen":
            if any(x["type"] in ("checkout", "checkout_held") for x in events):
                continue  # the order is placed (or the next question asked) in the same turn
            if e["path"] == "whatsapp":
                parts.append("ठीक है, पर्चा व्हाट्सऐप पर भेजना है। ऑर्डर दे दें?" if hi else "Got it, prescription on WhatsApp. Shall I place it?")
            else:
                parts.append("ठीक है, फार्मासिस्ट आपको कॉल करेंगे। ऑर्डर दे दें?" if hi else "Got it, our pharmacist will call you. Shall I place it?")
            asked_something = True
        elif kind == "details_needed":
            parts.append(lang_line(language, "details"))
            asked_something = True
        elif kind == "checkout":
            parts.append(_placed(e, language))
        elif kind == "bill":
            total = e.get("total")
            if total:
                amount = f"{round(total)} रुपये" if hi else f"{number_words(total)} rupees"
                parts.append(f"कुल {amount} हुआ। बिल अभी लाते हैं।" if hi else f"That's {amount}. I'll bring the bill right over.")
            else:
                parts.append("बिल अभी लाते हैं।" if hi else "I'll bring the bill right over.")
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

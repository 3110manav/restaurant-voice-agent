"""A kirana and a pharmacy end to end, with a scripted stand-in for the LLM (no API calls):
recognising a caller, collecting an address only when it's needed, prescription items, and the
medical safety rules."""
import pytest
from langchain_core.messages import AIMessage

import app.erp as erp
from app.agent.graph import RestaurantOrderingAgent, persona_for
from app.customers import session as cs
from app.customers.session import CustomerContext, CustomerSession


def item(i, name, category, price, **extra):
    return {"id": i, "name": name, "category": category, "price": price, "spice_level": None, "description": "",
            "long_description": "", "ingredients": [], "allergens": [], "tags": [], "variants": [],
            "is_available": True, "sort_order": 0, **extra}


GROCERY = [
    item("g1", "Lifebuoy Soap", "Personal Care", 40.0, brand="Lifebuoy"),
    item("g2", "Duracell AA Batteries", "Household", 90.0, brand="Duracell"),
]
MEDS = [
    item("m1", "Dolo 650 Tablet", "Fever and Pain", 32.0, generic_name="Paracetamol", strength="650 mg",
         uses=["fever", "headache"], symptoms=["fever", "headache"], rx_required=False, precautions="Check with a doctor if you have liver disease."),
    item("m2", "Azithral 500 Tablet", "Prescription Medicines", 120.0, generic_name="Azithromycin", strength="500 mg",
         uses=["bacterial throat infection"], symptoms=[], rx_required=True, schedule="H1"),
]


class Store:
    def __init__(self, menu, categories):
        self.menu, self.categories = menu, categories

    def get(self, i):
        return next((d for d in self.menu if d["id"] == i), None)

    def find_by_name(self, name):
        return next((d for d in self.menu if d["name"].lower().startswith(name.strip().lower())), None)


class ScriptedLLM:
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def invoke(self, messages, *a, **k):
        self.seen.append(list(messages))
        return self.replies.pop(0)


def call(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


KNOWN = CustomerContext.from_row({
    "customer": {"id": "c1", "name": "Meera", "language": "en", "phone": "+919876543210"},
    "address": {"id": "a1", "line": "12 Palm Road, Andheri West", "area": "Andheri West", "landmark": None, "pincode": None},
    "order_count": 2,
    "last_order": {"items": [{"name": "Lifebuoy Soap", "quantity": 2}]},
})


@pytest.fixture
def recorded(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    log = {"orders": [], "requests": [], "announced": []}
    monkeypatch.setattr(erp, "record_order", lambda *a, **k: log["orders"].append((a, k)) or {"id": "o1"})
    monkeypatch.setattr("app.whatsapp.notify.order_placed", lambda store, order: log["announced"].append((store, order)))
    monkeypatch.setattr(erp, "record_request", lambda *a, **k: log["requests"].append((a, k)))
    monkeypatch.setattr(cs.repository, "save_details", lambda *a: ("c9", "a9"))
    return log


def make(kind, context=None, phone="+919876543210"):
    menu, cats = (GROCERY, ["Personal Care", "Household"]) if kind == "kirana" else (MEDS, ["Fever and Pain", "Prescription Medicines"])
    row = {"id": "r1", "name": "Test Store", "business_type": kind, "agent_name": "Shubh"}
    customer = CustomerSession("r1", phone, context or CustomerContext(), delivery_required=True)
    return RestaurantOrderingAgent("s1", Store(menu, cats), persona=persona_for(row), restaurant=row, customer=customer)


def test_stores_use_the_store_persona_and_restaurants_the_waiter():
    assert persona_for({"business_type": "kirana"}) == "store" == persona_for({"business_type": "pharmacy"})
    assert persona_for({"business_type": "restaurant"}) == "waiter" == persona_for({})


def test_a_store_has_no_waiter_tools_and_no_cross_selling(recorded):
    agent = make("kirana")
    names = {t.name for t in agent.tools}
    assert "request_bill" not in names and "call_staff" not in names and {"save_delivery_details", "choose_pickup"} <= names
    assert agent.sales is None


def test_a_new_customer_is_asked_for_an_address_before_the_order_is_placed(recorded):
    agent = make("kirana")
    agent.llm_with_tools = ScriptedLLM(
        call("add_to_cart", {"items": [{"name": "Lifebuoy", "quantity": 2}]}),
        call("checkout", {}),
        call("save_delivery_details", {"name": "Ravi", "address": "4 MG Road, Bandra West, Mumbai", "area": "Bandra West"}),
        call("checkout", {}),
    )
    assert "Done, two Lifebuoy Soap" in agent.send("two lifebuoy soaps")
    held = agent.send("that's all, place the order")
    assert "name and delivery address" in held and recorded["orders"] == []  # held: nothing placed
    # the read-back is composed in code from what was saved, with no second model call
    assert agent.send("I'm Ravi, 4 MG Road Bandra West Mumbai") == "Thanks, Ravi. Got it: 4 MG Road, Bandra West, Mumbai. Is that right?"
    placed = agent.send("yes")
    assert "All set" in placed and "eighty rupees" in placed and "Bandra West" in placed
    (_, kw), = recorded["orders"]
    assert kw["extra"]["fulfilment"] == "delivery" and kw["extra"]["customer_id"] == "c9"
    assert kw["extra"]["address_snapshot"]["area"] == "Bandra West"


def test_a_returning_customer_is_never_asked_for_an_address(recorded):
    agent = make("kirana", KNOWN)
    assert "NEVER ask for it" in agent.system_prompt and "Andheri West" in agent.system_prompt
    agent.llm_with_tools = ScriptedLLM(
        call("add_to_cart", {"items": [{"name": "Lifebuoy", "quantity": 2}]}),
        call("checkout", {}),
    )
    agent.send("same as last time")
    placed = agent.send("that's all, place the order")
    assert "All set" in placed and "Andheri West" in placed and "name and delivery address" not in placed
    (_, kw), = recorded["orders"]
    assert kw["extra"]["customer_id"] == "c1" and kw["extra"]["address_snapshot"]["area"] == "Andheri West"


def test_the_opening_line_greets_a_known_caller_by_name(recorded):
    assert make("kirana", KNOWN).opening_line("Test Store").startswith("Welcome back Meera!")
    assert make("kirana").opening_line("Test Store").startswith("Namaste! Welcome to Test Store")


def test_pickup_places_the_order_without_an_address(recorded):
    agent = make("kirana")
    agent.llm_with_tools = ScriptedLLM(
        call("add_to_cart", {"items": [{"name": "Duracell", "quantity": 1}]}),
        call("choose_pickup", {}),
        call("checkout", {}),
    )
    agent.send("a pack of duracell batteries")
    assert "Shall I place it?" in agent.send("I'll pick it up")
    placed = agent.send("yes place it")
    assert "pick up" in placed
    assert recorded["orders"][0][1]["extra"]["fulfilment"] == "pickup"


def test_an_address_taken_this_turn_cannot_be_placed_until_the_customer_confirms(recorded):
    agent = make("kirana")
    agent.llm_with_tools = ScriptedLLM(
        call("add_to_cart", {"items": [{"name": "Lifebuoy", "quantity": 1}]}),
        # the model saves the address and tries to place the order in the same turn
        AIMessage(content="", tool_calls=[
            {"name": "save_delivery_details", "args": {"name": "Ravi", "address": "4 MG Road, Bandra West, Mumbai"}, "id": "a"},
            {"name": "checkout", "args": {}, "id": "b"},
        ]),
        call("checkout", {}),
    )
    agent.send("a lifebuoy soap")
    reply = agent.send("place the order, I'm Ravi, 4 MG Road Bandra West Mumbai")
    assert "Is that right?" in reply and recorded["orders"] == []
    assert "All set" in agent.send("yes")  # the next message is the confirmation
    assert len(recorded["orders"]) == 1


def test_an_incomplete_address_is_not_accepted(recorded):
    agent = make("kirana")
    out = next(t for t in agent.tools if t.name == "save_delivery_details").invoke({"name": "Ravi", "address": "Bandra"})
    assert "incomplete" in out and not agent.customer.delivery_ready()


# ----------------------------------------------------------------------------------- pharmacy --


def test_an_emergency_never_reaches_the_model_and_alerts_the_staff(recorded):
    agent = make("pharmacy")
    agent.llm_with_tools = ScriptedLLM()  # any model call would raise
    reply = agent.send("my mother has chest pain")
    assert "one one two" in reply
    (args, kw), = recorded["requests"]
    assert args[2] == "medical_emergency" and kw["restaurant_id"] == "r1"


def test_a_dose_question_is_left_to_the_pharmacist(recorded):
    agent = make("pharmacy")
    agent.llm_with_tools = ScriptedLLM()
    assert "pharmacist" in agent.send("how many Dolo should I take")
    assert recorded["requests"][0][0][2] == "pharmacist_callback"


def test_the_screening_only_runs_for_a_pharmacy(recorded):
    agent = make("kirana")
    agent.llm_with_tools = ScriptedLLM(AIMessage(content="Sure, what would you like?"))
    assert agent.send("how many should I take") == "Sure, what would you like?"


def test_a_reply_that_gives_a_dose_is_regenerated(recorded):
    agent = make("pharmacy")
    agent.llm_with_tools = ScriptedLLM(
        AIMessage(content="Dolo 650 works well, take two tablets twice a day."),
        AIMessage(content="Dolo 650 is commonly used for fever. Our pharmacist will confirm."),
    )
    reply = agent.send("do you have something for fever")
    assert "twice a day" not in reply and "pharmacist" in reply
    assert "dose or a schedule" in str(agent.llm_with_tools.seen[1][-1].content)


def test_a_symptom_search_shows_what_an_item_is_used_for_but_no_dose(recorded):
    agent = make("pharmacy")
    agent.menu_store.search = lambda q, k=4: [MEDS[0], MEDS[1]]
    out = next(t for t in agent.tools if t.name == "search_menu").invoke({"query": "fever"})
    assert "commonly used for fever, headache" in out and "NEEDS A PRESCRIPTION" in out
    assert "Contains Paracetamol 650 mg" in out


def test_a_prescription_order_asks_how_to_check_it_before_it_is_placed(recorded):
    agent = make("pharmacy", KNOWN)
    agent.llm_with_tools = ScriptedLLM(
        call("add_to_cart", {"items": [{"name": "Azithral", "quantity": 1}]}),
        call("checkout", {}),
        call("choose_prescription_path", {"path": "whatsapp"}),
    )
    added = agent.send("add an Azithral 500")
    assert "needs a prescription" in added.lower() and agent.cart[0]["rx"] is True
    asked = agent.send("that's all, place the order")
    assert "WhatsApp" in asked and "pharmacist" in asked and recorded["orders"] == []  # held for the choice
    placed = agent.send("I'll send it on whatsapp")
    assert "Please send a clear photo of the prescription on WhatsApp" in placed
    extra = recorded["orders"][0][1]["extra"]
    assert extra["needs_pharmacist"] and extra["rx_path"] == "whatsapp" and extra["status"] == "awaiting_prescription"
    assert len(extra["short_code"]) == 5 and agent.cart == []  # the cart starts fresh


def test_choosing_the_pharmacist_marks_the_order_as_waiting_for_a_call(recorded):
    agent = make("pharmacy", KNOWN)
    agent.llm_with_tools = ScriptedLLM(
        call("add_to_cart", {"items": [{"name": "Azithral", "quantity": 1}]}),
        call("checkout", {}),
        call("choose_prescription_path", {"path": "pharmacist"}),
    )
    agent.send("add an Azithral 500")
    agent.send("that's all")  # held: asks how the prescription will be checked
    placed = agent.send("I want to talk to the pharmacist first")  # the answer places the order they already asked for
    assert "pharmacist will call you" in placed
    assert recorded["orders"][0][1]["extra"]["status"] == "awaiting_pharmacist"


def test_an_ordinary_order_skips_the_prescription_question_and_tells_the_shop(recorded):
    agent = make("pharmacy", KNOWN)
    agent.llm_with_tools = ScriptedLLM(call("add_to_cart", {"items": [{"name": "Dolo", "quantity": 2}]}), call("checkout", {}))
    agent.send("two dolo 650")
    placed = agent.send("that's all")
    assert "All set" in placed and "prescription" not in placed.lower()
    import time
    for _ in range(100):  # the shop is told from a background thread
        if recorded["announced"]:
            break
        time.sleep(0.02)
    (store, order), = recorded["announced"]
    assert store["id"] == "r1" and len(order["code"]) == 5 and order["rx_path"] is None and order["order_id"] == "o1"
    assert order["lines"][0]["quantity"] == 2 and order["channel"] == "web" and order["phone_verified"] is False


def test_a_second_order_in_the_same_chat_does_not_repeat_the_first(recorded):
    agent = make("kirana", KNOWN)
    agent.llm_with_tools = ScriptedLLM(
        call("add_to_cart", {"items": [{"name": "Lifebuoy", "quantity": 1}]}), call("checkout", {}),
        call("add_to_cart", {"items": [{"name": "Duracell", "quantity": 1}]}), call("checkout", {}),
    )
    agent.send("a soap")
    agent.send("place it")
    agent.send("and a pack of batteries")
    agent.send("place it")
    first, second = recorded["orders"]
    assert [l["name"] for l in first[0][2]] == ["Lifebuoy Soap"]
    assert [l["name"] for l in second[0][2]] == ["Duracell AA Batteries"]  # not both


def test_the_closing_line_says_the_order_was_sent_to_the_shop_on_whatsapp(recorded):
    from app.agent import replies
    events = [{"type": "checkout", "total": 64.0, "say_total": True, "fulfilment": "delivery", "area": "Bandra",
               "rx_path": None, "wa_alerted": True, "wa_number": "+919000011111", "wa_channel": "voice"}]
    assert "I've sent your order to the shop on WhatsApp." in replies.compose(events, "en")
    events[0]["wa_alerted"] = False  # no token or no recipient: never claim it
    assert "WhatsApp" not in replies.compose(events, "en")


def test_on_a_call_the_prescription_goes_to_the_shops_number_and_in_a_whatsapp_chat_it_goes_here():
    from app.agent import replies
    base = {"type": "checkout", "total": 120.0, "say_total": True, "fulfilment": "delivery", "area": None,
            "rx_path": "whatsapp", "wa_alerted": True, "wa_number": "+919000011111"}
    call = replies.compose([{**base, "wa_channel": "voice"}], "en")
    assert "WhatsApp number, 9 0 0 0 0, 1 1 1 1 1," in call
    chat = replies.compose([{**base, "wa_channel": "whatsapp"}], "en")
    assert "on WhatsApp" in chat and "9 0 0 0 0" not in chat


def test_a_phone_number_is_spoken_in_two_groups_of_five():
    from app.agent.replies import spoken_digits
    assert spoken_digits("+919876543210") == "9 8 7 6 5, 4 3 2 1 0"
    assert spoken_digits("9876543210") == "9 8 7 6 5, 4 3 2 1 0"

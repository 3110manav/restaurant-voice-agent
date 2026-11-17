"""Replies seen going wrong on a real call: a pizza offered garlic naan and masala chai, and "sushi" called missing
when the menu has a Sushi section."""
from app.agent import salesflow, tools

DISHES = [
    {"id": "p1", "name": "Four Cheese Pizza", "category": "Pizza", "veg": True},
    {"id": "m1", "name": "Paneer Tikka", "category": "Starters", "veg": True, "spice_level": "medium"},
    {"id": "n1", "name": "Garlic Naan", "category": "Breads", "veg": True},
    {"id": "r1", "name": "Jeera Rice", "category": "Rice", "veg": True},
    {"id": "d1", "name": "Mango Lassi", "category": "Drinks", "veg": True},
    {"id": "d2", "name": "Masala Chai", "category": "Drinks", "veg": True},
    {"id": "d3", "name": "Cola", "category": "Drinks", "veg": True},
    {"id": "s1", "name": "California Roll", "category": "Sushi", "veg": True, "is_available": True},
    {"id": "s2", "name": "Spicy Tuna Roll", "category": "Sushi", "veg": False, "is_available": True},
    {"id": "s3", "name": "Salmon Nigiri", "category": "Sushi", "veg": False, "is_available": False},
]
BY_ID = {d["id"]: d for d in DISHES}


def offer(cart_ids):
    cart = [{"id": i, "name": BY_ID[i]["name"], "quantity": 1, "price": 100} for i in cart_ids]
    added = [BY_ID[i] for i in cart_ids]
    return salesflow.first_order_offer(salesflow.SalesState(), DISHES, BY_ID.get, cart, added)


def test_a_pizza_is_not_offered_indian_breads_or_drinks():
    # On this menu those are the only breads and drinks but the cola: the cola is fine, the rest is not.
    result = offer(["p1"])
    assert result is not None and result.drinks == ["Cola"] and result.sides == []


def test_nothing_is_offered_rather_than_something_that_does_not_go():
    only_indian = [d for d in DISHES if d["id"] not in ("d3",)]
    cart = [{"id": "p1", "name": "Four Cheese Pizza", "quantity": 1, "price": 100}]
    assert salesflow.first_order_offer(salesflow.SalesState(), only_indian, BY_ID.get, cart, [BY_ID["p1"]]) is None


def test_an_indian_dish_still_gets_its_bread_and_lassi():
    result = offer(["m1"])
    assert result is not None
    assert "Mango Lassi" in result.drinks and result.sides == ["Garlic Naan"]
    assert "Cola" in result.drinks or len(result.drinks) == 2


def test_a_menu_with_no_recognisable_cuisine_keeps_the_old_behaviour():
    plain = [{"id": "a", "name": "House Special", "category": "Mains", "veg": True},
             {"id": "b", "name": "Fresh Juice", "category": "Drinks", "veg": True},
             {"id": "c", "name": "Side Salad", "category": "Sides", "veg": True}]
    by = {d["id"]: d for d in plain}
    result = salesflow.first_order_offer(salesflow.SalesState(), plain, by.get, [{"id": "a", "name": "House Special", "quantity": 1, "price": 1}], [plain[0]])
    assert result is not None and result.drinks == ["Fresh Juice"] and result.sides == ["Side Salad"]


def test_the_table_pages_suggestion_card_follows_the_same_rule():
    cart = [{"id": "p1", "name": "Four Cheese Pizza", "quantity": 1, "price": 100}]
    names = [d["name"] for d in salesflow.pick(DISHES, BY_ID.get, cart, "drink", 3)]
    assert "Mango Lassi" not in names and "Masala Chai" not in names and "Cola" in names


class Menu:
    menu = DISHES
    categories = ["Pizza", "Starters", "Breads", "Rice", "Drinks", "Sushi"]

    def find_by_name(self, name):
        return next((d for d in DISHES if d["name"].lower() == name.lower()), None)


def test_naming_a_menu_section_lists_its_dishes_instead_of_saying_it_is_missing():
    item, message = tools._resolve(Menu(), "sushi")
    assert item is None
    assert "section of the menu" in message and "California Roll" in message and "Spicy Tuna Roll" in message
    assert "Salmon Nigiri" not in message  # not available right now
    assert "never say the restaurant doesn't have it" in message
    assert tools._resolve(Menu(), "pizzas")[1].startswith("'pizzas' is a section")


def test_a_word_that_is_neither_a_dish_nor_a_section_is_still_not_found():
    item, message = tools._resolve(Menu(), "unicorn steak")
    assert item is None and "Couldn't find" in message


# ---- seen on the Saffron Table call: hesitation answered as a request, an invented "Jain", a dosa offered naan

import pytest  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from app.agent import guardrails as g  # noqa: E402
from app.agent import language as lang  # noqa: E402


@pytest.mark.parametrize("heard", ["Um.", "And. Um.", "Uh... hmm", "um uh er", "हम्म", "And. Okay. Um.", "Hmm, okay..."])
def test_hesitation_sounds_get_no_answer(heard):
    verdict = g.check_input(heard)
    assert verdict.reply == "" and verdict.reason == "noise" and g.is_noise(heard)


@pytest.mark.parametrize("heard", ["I want a dosa", "Okay add it", "And a lassi", "no", "that's all", "Okay", "Um okay add a lassi"])
def test_real_requests_are_not_mistaken_for_hesitation(heard):
    assert not g.is_noise(heard) and g.check_input(heard).reply is None


def test_a_bare_okay_is_an_acknowledgement_only_when_nothing_was_asked():
    assert g.is_bare_ack("Okay") and g.is_bare_ack("alright")
    assert not g.is_bare_ack("okay add a dosa") and not g.is_bare_ack("Um.")


@pytest.fixture
def agent(monkeypatch):
    from app.agent import graph
    from tests.test_agent_guardrails import Store

    monkeypatch.setenv("GROQ_API_KEY", "test")
    return graph.RestaurantOrderingAgent("s1", Store(), persona="waiter", restaurant={"id": "r1", "name": "T", "cuisine": "Indian"})


def test_an_okay_after_a_statement_is_met_with_silence_but_after_a_question_it_is_an_answer(agent):
    from tests.test_agent_guardrails import ScriptedLLM

    agent.llm_with_tools = ScriptedLLM(AIMessage(content="Your dosa is coming. Enjoy!"), AIMessage(content="Added the lassi."))
    agent.send("is the dosa crisp")  # something to say
    assert agent.send("Okay") == "" and len(agent.llm_with_tools.seen) == 1  # no model call for it
    agent.llm_with_tools = ScriptedLLM(AIMessage(content="Want a lassi with that?"), AIMessage(content="Added the lassi."))
    agent.send("is it spicy")
    assert agent.send("Okay") == "Added the lassi."  # it answered a question, so it goes through


def test_a_dietary_claim_the_tools_did_not_return_is_caught():
    none_returned = g.TurnFacts(user_text="something cheese and jain", tool_calls=[("search_menu", "Four Cheese Pizza: cheese")])
    for claim in ("Both are suitable for Jain preferences.", "That one is vegan.", "It is gluten free and halal."):
        assert "unbacked_diet" in [v.kind for v in g.check_reply(claim, none_returned)], claim
    listed = g.TurnFacts(user_text="anything vegan", tool_calls=[("search_menu", "Veg Burger [vegan, bestseller]")])
    assert g.check_reply("The Veg Burger is vegan.", listed) == []
    assert g.check_reply("Do you want the Jain version?", none_returned) == []  # a question is not a claim
    assert g.check_reply("We don't have a Jain option.", none_returned) == []  # neither is a refusal


def test_an_unbacked_dietary_claim_ends_in_checking_with_the_kitchen():
    facts = g.TurnFacts(user_text="jain?", tool_calls=[])
    text = g.fallback_reply(g.check_reply("Yes, that is Jain.", facts), "Yes, that is Jain.", "en")
    assert text == lang.line("en", "diet") and "kitchen" in text and lang.has_devanagari(lang.line("hi", "diet"))


SOUTH = [
    {"id": "d1", "name": "Plain Dosa", "category": "South Indian", "veg": True},
    {"id": "n1", "name": "Garlic Naan", "category": "Breads", "veg": True},
    {"id": "l1", "name": "Mango Lassi", "category": "Drinks", "veg": True},
    {"id": "c1", "name": "Masala Chai", "category": "Drinks", "veg": True},
    {"id": "p1", "name": "Paneer Tikka", "category": "Starters", "veg": True},
]


def test_a_dosa_is_not_offered_naan_but_still_gets_a_lassi_or_chai():
    by = {d["id"]: d for d in SOUTH}
    result = salesflow.first_order_offer(salesflow.SalesState(), SOUTH, by.get, [{"id": "d1", "name": "Plain Dosa", "quantity": 1, "price": 1}], [by["d1"]])
    assert result is not None and result.sides == []
    assert set(result.drinks) == {"Mango Lassi", "Masala Chai"}


def test_a_north_indian_dish_still_gets_naan():
    by = {d["id"]: d for d in SOUTH}
    result = salesflow.first_order_offer(salesflow.SalesState(), SOUTH, by.get, [{"id": "p1", "name": "Paneer Tikka", "quantity": 1, "price": 1}], [by["p1"]])
    assert result is not None and result.sides == ["Garlic Naan"]

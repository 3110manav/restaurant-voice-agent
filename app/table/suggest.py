"""The table page's suggestion card: one dish at a time, picked by the same rules as the waiter's
spoken offers (app/agent/salesflow.py), so the card and the waiter never disagree.

While ordering, a drink and then a side for a cart with food in it. After a round has gone to the
kitchen, a dessert to finish. No more than MAX_SUGGESTIONS cards a session, and never a dish the
guest already turned down.
"""
from app.agent import salesflow
from app.table.state import MAX_SUGGESTIONS, TableState

_REASONS = {
    "drink": "A cold drink goes well with this.",
    "side": "{name} goes well with your order.",
    "dessert": "Something sweet to finish?",
}


def next_suggestion(state: TableState, menu: list[dict], menu_by_id, cart: list[dict]) -> dict | None:
    if len(state.suggestions_shown) >= MAX_SUGGESTIONS:
        return None
    everything = cart + state.ordered
    roles = {salesflow.role_of(d) for d in (menu_by_id(line["id"]) for line in everything) if d}
    cart_roles = {salesflow.role_of(d) for d in (menu_by_id(line["id"]) for line in cart) if d}
    wanted = []
    if "food" in cart_roles:
        wanted += [r for r in ("drink", "side") if r not in roles]
    elif state.rounds > 0 and "dessert" not in roles and roles & {"food", "side"}:
        wanted.append("dessert")
    for role in wanted:
        for dish in salesflow.pick(menu, menu_by_id, everything, role, limit=4):
            if dish["id"] not in state.suggestions_shown:
                return {
                    "id": dish["id"],
                    "name": dish["name"],
                    "price": float(dish["price"]),
                    "role": role,
                    "reason": _REASONS[role].format(name=dish["name"]),
                }
    return None

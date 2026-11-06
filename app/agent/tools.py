"""Tool definitions for the ordering agent.

Tools are built per-session via `build_tools`, closing over that session's
cart (a plain list) and a menu store — either the legacy JSON-catalog MenuStore
or a restaurant's LiveMenu (app/menu/snapshot.py). Closing over the cart —
rather than threading session_id through every tool call — keeps the tool
signatures simple, which matters because the LLM has to fill them in.

Cart lines are {"id", "name", "price", "quantity"} plus an optional "variant"
(a size/portion such as "Large" or "Half"); a line's identity is (id, variant),
so a Regular and a Large of the same pizza are separate lines.
"""
import random

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app import erp
from app.customers.session import CustomerSession
from app.agent.salesflow import SalesState, dessert_offer, first_order_offer
from app.currency import format_price

CartItem = dict

# More than this on one line is almost certainly a mis-hearing (or a prank); a person confirms it.
MAX_LINE_QUANTITY = 20


class OrderLine(BaseModel):
    name: str = Field(description="item name as said")
    quantity: int = Field(default=1)
    variant: str = Field(default="", description="size or portion, if chosen")


_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: it gets read aloud and typed on a phone


def _order_code() -> str:
    return "".join(random.choices(_CODE_ALPHABET, k=5))


def _cart_total(cart: list[CartItem]) -> float:
    return sum(line["price"] * line["quantity"] for line in cart)


def _item_descriptor(item: dict, prices: bool = True) -> str:
    """Build a short "(price, extra bits)" fragment for an item, adapting to
    whichever optional fields its catalog has — food items carry veg/spice
    info, grocery items carry a brand instead, some dishes come in sizes.
    With prices=False the model isn't shown any, so it can't read one out unasked."""
    variants = item.get("variants") or []
    if variants:
        sizes = ", ".join(f"{v['name']} {format_price(v['price'])}" if prices else v["name"] for v in variants)
        bits = [f"sizes: {sizes}"]
    else:
        bits = [format_price(item["price"])] if prices else []
    if "veg" in item:
        bits.append("veg" if item["veg"] else "non-veg")
    if item.get("spice_level") and item["spice_level"] != "none":
        bits.append(f"spice: {item['spice_level']}")
    if item.get("brand"):
        bits.append(f"brand: {item['brand']}")
    if item.get("is_available") is False:
        bits.append("currently unavailable")
    return ", ".join(bits)


def _medicine_note(item: dict) -> str:
    """For pharmacy items: what it contains and what it is commonly used for, from the catalog only."""
    if not item.get("generic_name") and not item.get("uses"):
        return ""
    bits = []
    if item.get("generic_name"):
        bits.append(f"Contains {item['generic_name']}" + (f" {item['strength']}" if item.get("strength") else ""))
    if item.get("uses"):
        bits.append("commonly used for " + ", ".join(item["uses"]))
    if item.get("rx_required"):
        bits.append("NEEDS A PRESCRIPTION: the pharmacist verifies it before it goes out")
    return "; ".join(bits)


def _line_label(line: dict) -> str:
    return f"{line['name']} ({line['variant']})" if line.get("variant") else line["name"]


def _pick_variant(variants: list[dict], requested: str | None) -> dict | None:
    """The variant the customer meant, or None if they didn't say / it's unclear.
    A dish with exactly one variant needs no answer."""
    if len(variants) == 1:
        return variants[0]
    if not requested or not requested.strip():
        return None
    want = requested.strip().lower()
    for v in variants:
        if v["name"].lower() == want:
            return v
    partial = [v for v in variants if v["name"].lower().startswith(want) or want in v["name"].lower()]
    return partial[0] if len(partial) == 1 else None


def add_item_to_cart(
    cart: list[CartItem], item: dict, quantity: int = 1, variant: str | None = None, with_prices: bool = True
) -> str:
    """Add `quantity` of an already-resolved menu `item` dict to `cart`.

    Shared by the LLM-facing add_to_cart tool (resolves by name) and the
    direct /cart/add API route (resolves by id) so both paths merge
    quantities into the same cart the same way.
    """
    if quantity < 1:
        return "Quantity must be at least 1."
    if quantity > MAX_LINE_QUANTITY:
        return f"{quantity} of one item is more than I can take by voice. Ask the customer to confirm the number, up to {MAX_LINE_QUANTITY}."
    if item.get("is_available") is False:
        return f"{item['name']} isn't available right now."

    variants = item.get("variants") or []
    chosen_name = None
    price = item["price"]
    if variants:
        chosen = _pick_variant(variants, variant)
        if chosen is None:
            options = ", ".join(f"{v['name']} {format_price(v['price'])}" if with_prices else v["name"] for v in variants)
            return f"{item['name']} comes in: {options}. Ask the customer which one they want."
        chosen_name, price = chosen["name"], chosen["price"]

    for line in cart:
        if line["id"] == item["id"] and line.get("variant") == chosen_name:
            if line["quantity"] + quantity > MAX_LINE_QUANTITY:
                return f"That would be more than {MAX_LINE_QUANTITY} of {_line_label(line)}. Ask the customer to confirm the number."
            line["quantity"] += quantity
            return f"Updated {_line_label(line)} to {line['quantity']} in the cart."
    line = {"id": item["id"], "name": item["name"], "price": price, "quantity": quantity}
    if chosen_name:
        line["variant"] = chosen_name
    if item.get("rx_required"):
        line["rx"] = True  # a prescription medicine: the pharmacist verifies before dispatch
    cart.append(line)
    note = " It needs a prescription: tell the customer the pharmacist will verify it before it goes out." if line.get("rx") else ""
    return f"Added {quantity} x {_line_label(line)} to the cart.{note}"


def remove_item_from_cart_by_id(
    cart: list[CartItem], item_id: str, quantity: int = 1, variant: str | None = None
) -> str:
    """Remove `quantity` of the cart line with the given item id (and variant,
    when the dish has sizes).

    Used by the direct /cart/remove API route — the LLM-facing
    remove_from_cart tool matches by name instead, since that's what the
    customer says out loud.
    """
    for line in cart:
        if line["id"] == item_id and (variant is None or line.get("variant") == variant):
            line["quantity"] -= quantity
            if line["quantity"] <= 0:
                cart.remove(line)
                return f"Removed {_line_label(line)} from the cart."
            return f"Updated {_line_label(line)} to {line['quantity']} in the cart."
    return f"'{item_id}' isn't in the cart."


def _resolve(menu_store, name: str) -> tuple[dict | None, str | None]:
    """(dish, None) when `name` clearly means one dish, else (None, a message for
    the agent — either the candidates to ask the customer about, or not-found)."""
    item = menu_store.find_by_name(name)
    if item:
        return item, None
    candidates = getattr(menu_store, "candidates", None)
    if candidates:
        options = candidates(name)
        if options:
            names = ", ".join(d["name"] for d in options)
            return None, f"'{name}' could mean: {names}. Ask the customer which one they want."
    return None, f"Couldn't find '{name}' on the menu. Try searching for it first."


def build_tools(
    cart: list[CartItem],
    menu_store,
    session_id: str = "",
    persona: str = "",
    restaurant_id: str | None = None,
    table_no: str | None = None,
    sales: SalesState | None = None,
    events: list[dict] | None = None,
    price_ok=None,
    customer: CustomerSession | None = None,
    say_total: bool = False,
    on_order=None,
    shop_whatsapp=None,
) -> list:
    """`events`, when given, collects what each action did, so simple turns can be answered in code
    (app/agent/replies.py). `price_ok()` says whether the guest has asked about prices this turn; if it
    returns False the tools hide prices from the model (the waiter only talks money when asked).
    `customer` is the live caller state (see app/customers/session.py): with it, checkout holds until a
    delivery order has an address, and the tools to save one exist. `say_total` makes stores (not
    restaurants) tell the total when the order is placed. `on_order(order)` is called once an order is
    placed, to tell the shop (see app/whatsapp/notify.py). `shop_whatsapp()` says what the closing line may claim
    about WhatsApp: {"alerted": the shop really will be messaged, "number": its WhatsApp number, "channel": where
    this conversation is happening}."""

    def prices() -> bool:
        return True if price_ok is None else bool(price_ok())

    def note(event: dict) -> None:
        if events is not None:
            events.append(event)

    @tool
    def search_menu(query: str) -> str:
        """Search the menu by description, ingredient, dietary need or mood. Use it for
        recommendations and "what do you have for..." questions.
        """
        matches = menu_store.search(query)
        if not matches:
            return "No matching items found."
        lines = []
        for item in matches:
            line = f"- {item['name']} ({_item_descriptor(item, prices())}): {item['description']}"
            if _medicine_note(item):
                line += f" [{_medicine_note(item)}]"
            lines.append(line)
        return "\n".join(lines)

    @tool
    def get_item_details(name: str) -> str:
        """Price, sizes, spice level and availability for one named item. For "what is it" or
        "how does it taste", use explain_dish instead when it's available.
        """
        item, problem = _resolve(menu_store, name)
        if problem:
            return problem
        lines = [f"{item['name']} - {_item_descriptor(item)}", item["description"]]
        if item.get("ingredients"):
            lines.append(f"Ingredients: {', '.join(item['ingredients'])}")
        if item.get("allergens"):
            lines.append(f"Contains: {', '.join(item['allergens'])}")
        if item.get("brand"):
            lines.append(f"Brand: {item['brand']}")
        if _medicine_note(item):
            lines.append(_medicine_note(item) + ".")
        if item.get("precautions"):
            lines.append(f"Precaution: {item['precautions']}")
        return "\n".join(lines)

    @tool
    def add_to_cart(items: list[OrderLine]) -> str:
        """Add everything the customer just asked for in ONE call, each item with its quantity
        (and size or portion, if it has one). Names must be real menu items. If an item has sizes
        and none was chosen, leave variant empty and the result says what to ask. The result
        includes the cart and total, so don't call view_cart after.
        """
        results, added = [], []
        lines_added, problem = [], False
        for line in items:
            item, issue = _resolve(menu_store, line.name)
            if issue:
                results.append(issue)
                problem = True
                continue
            chosen = _pick_variant(item.get("variants") or [], line.variant or None) if item.get("variants") else None
            message = add_item_to_cart(cart, item, line.quantity, line.variant or None, with_prices=prices())
            results.append(message)
            if message.startswith(("Added", "Updated")):
                added.append(item)
                lines_added.append(
                    {"name": item["name"], "variant": chosen["name"] if chosen else None, "quantity": line.quantity,
                     "rx": bool(item.get("rx_required"))}
                )
            else:
                problem = True
        if added:
            summary = ", ".join(f"{line['quantity']}x {_line_label(line)}" for line in cart)
            results.append(f"Cart: {summary}." + (f" Total: {format_price(_cart_total(cart))}." if prices() else ""))
            note({"type": "added", "lines": lines_added})
            if sales is not None:
                offer = first_order_offer(sales, menu_store.menu, menu_store.get, cart, added)
                if offer:
                    results.append(offer.hint)
                    note(offer.event)
        if problem:
            note({"type": "problem"})
        return "\n".join(results)

    @tool
    def remove_from_cart(name: str, quantity: int = 1, variant: str = "") -> str:
        """Remove an item, or some of it, from the cart. Pass variant if the cart holds several sizes."""
        wanted = name.strip().lower()
        for line in cart:
            if wanted not in (line["name"].lower(), _line_label(line).lower()):
                continue
            if variant and line.get("variant", "").lower() != variant.strip().lower():
                continue
            line["quantity"] -= quantity
            remaining = max(line["quantity"], 0)
            note({"type": "removed", "name": line["name"], "variant": line.get("variant"), "remaining": remaining})
            if line["quantity"] <= 0:
                cart.remove(line)
                return f"Removed {_line_label(line)} from the cart."
            return f"Updated {_line_label(line)} to {line['quantity']} in the cart."
        note({"type": "problem"})
        return f"'{name}' isn't in the cart."

    @tool
    def view_cart() -> str:
        """Show the current cart contents and running total."""
        if not cart:
            return "The cart is empty."
        if not prices():
            return "\n".join(f"- {line['quantity']} x {_line_label(line)}" for line in cart)
        lines = [
            f"- {line['quantity']} x {_line_label(line)} ({format_price(line['price'] * line['quantity'])})"
            for line in cart
        ]
        return "\n".join(lines) + f"\nTotal: {format_price(_cart_total(cart))}"

    @tool
    def checkout() -> str:
        """Finalize the order. Only call this after the customer explicitly confirms they're done ordering."""
        if not cart:
            note({"type": "problem"})
            return "Can't check out — the cart is empty."
        if sales is not None:
            offer = dessert_offer(sales, menu_store.menu, menu_store.get, cart)
            if offer:
                note({"type": "checkout_held"})
                note(offer.event)
                return f"Order not placed yet. {offer.hint}"
        if customer is not None and customer.awaiting_confirm:
            # The address was taken this turn: it is read back (in code) and the customer's next message confirms it.
            note({"type": "checkout_held"})
            return "Order not placed yet: the customer has not confirmed the address or pickup. Wait for their yes."
        if customer is not None and customer.rx_path is None and any(line.get("rx") for line in cart):
            customer.checkout_pending = True
            note({"type": "checkout_held"})
            note({"type": "rx_choice_needed"})
            return (
                "Order not placed yet: it has a prescription medicine. Ask the customer whether they would like to "
                "send a photo of the prescription on WhatsApp, or talk to the pharmacist first. Then call "
                "choose_prescription_path with 'whatsapp' or 'pharmacist'."
            )
        if customer is not None and not customer.delivery_ready():
            customer.checkout_pending = True
            note({"type": "checkout_held"})
            note({"type": "details_needed"})
            return (
                "Order not placed yet: it needs a delivery address. Ask the customer for their name and full "
                "delivery address (house or flat, street, area, a landmark), or whether they will pick it up. Then "
                "call save_delivery_details (or choose_pickup), read the address back once, and wait for them to confirm."
            )
        total = _cart_total(cart)
        summary = ", ".join(f"{line['quantity']}x {_line_label(line)}" for line in cart)
        extra = customer.order_fields() if customer is not None else {}
        rx = any(line.get("rx") for line in cart)
        code = _order_code()
        extra["short_code"] = code
        if rx:
            extra["needs_pharmacist"] = True
            if customer is not None and customer.rx_path:
                extra["status"] = "awaiting_prescription" if customer.rx_path == "whatsapp" else "awaiting_pharmacist"
        row = erp.record_order(
            session_id, persona, list(cart), total, restaurant_id=restaurant_id, table_no=table_no, extra=extra
        )
        address = (customer.current_address() or {}) if customer is not None else {}
        wa = (shop_whatsapp() if shop_whatsapp is not None and customer is not None else None) or {}
        note(
            {"type": "checkout", "total": total, "say_total": say_total, "fulfilment": extra.get("fulfilment"),
             "area": address.get("area") or None, "rx_path": extra.get("rx_path"), "code": code,
             "wa_alerted": bool(wa.get("alerted")), "wa_number": wa.get("number"), "wa_channel": wa.get("channel")}
        )
        if on_order is not None:
            on_order(
                {
                    "code": code,
                    "order_id": (row or {}).get("id"),
                    "lines": [dict(line) for line in cart],
                    "total": total,
                    "fulfilment": extra.get("fulfilment"),
                    "address": address.get("line"),
                    "customer_name": customer.display_name() if customer is not None else None,
                    "phone": customer.phone if customer is not None else None,
                    "phone_verified": bool(customer is not None and customer.phone_verified),
                    "rx_path": extra.get("rx_path"),
                }
            )
        cart.clear()  # the order is placed: the next one starts from an empty cart
        if customer is not None:
            customer.checkout_pending = False
            customer.rx_path = None
        told = say_total or prices()
        return f"Order placed: {summary}." + (f" Total: {format_price(total)}." if told else "") + " Thank you!"

    tools = [search_menu, get_item_details, add_to_cart, remove_from_cart, view_cart, checkout]

    if customer is not None:

        @tool
        def save_delivery_details(name: str, address: str, area: str = "", landmark: str = "", pincode: str = "") -> str:
            """Save the customer's name and delivery address once they have told you. address is the full
            address as said (house or flat, street, area); area is just the locality ("Andheri West");
            landmark and pincode only if given. Never invent a part they did not say."""
            full = " ".join(address.split())
            if len(full) < 12 or not any(ch.isalpha() for ch in full):
                return "That address looks incomplete. Ask for the house or flat number, street and area."
            digits = "".join(ch for ch in pincode if ch.isdigit())
            customer.save_details(
                name.strip() or None,
                {"line": full, "area": area.strip(), "landmark": landmark.strip(), "pincode": digits if len(digits) == 6 else ""},
            )
            note({"type": "details_saved", "name": customer.display_name(), "line": full})
            return (
                f"Saved. Read the address back to the customer in one short sentence ({full}) and ask them to confirm "
                "it. Once they confirm, place the order with checkout; if they correct it, call this again."
            )

        @tool
        def choose_pickup() -> str:
            """The customer will collect the order from the store instead of having it delivered."""
            customer.choose_pickup()
            note({"type": "pickup_chosen"})
            return "Noted: pickup from the store. Place the order with checkout once they confirm."

        @tool
        def choose_prescription_path(path: str) -> str:
            """The customer's choice for a prescription medicine: path is "whatsapp" (they will send a photo of
            the prescription on WhatsApp) or "pharmacist" (they want to talk to the pharmacist first)."""
            chosen = path.strip().lower()
            if chosen not in ("whatsapp", "pharmacist"):
                return "path must be 'whatsapp' or 'pharmacist'. Ask the customer which they prefer."
            customer.choose_rx_path(chosen)
            note({"type": "rx_path_chosen", "path": chosen})
            if customer.checkout_pending:
                # They had already asked to place the order; this answer was the missing piece, so place it now.
                return checkout.invoke({})
            return f"Noted: {chosen}. Place the order with checkout when they are ready."

        tools += [save_delivery_details, choose_pickup, choose_prescription_path]

    if restaurant_id is not None:

        @tool
        def explain_dish(name: str) -> str:
            """Explain one dish like a good waiter: what it is, taste and feel, how it's served,
            what's in it, allergens. Use it for "what is X", "is it spicy", "what's in it". Answer
            from the result only and add nothing it doesn't say.
            """
            item, problem = _resolve(menu_store, name)
            if problem:
                return problem
            lines = [f"{item['name']} — {_item_descriptor(item, prices())}"]
            if item.get("long_description"):
                lines.append(item["long_description"])
            else:
                lines.append(item["description"])
                lines.append(
                    "(The kitchen hasn't written detailed notes for this dish. Share only what "
                    "is written here and offer to check with the staff for more.)"
                )
            if item.get("ingredients"):
                lines.append(f"Ingredients: {', '.join(item['ingredients'])}")
            if item.get("allergens"):
                lines.append(f"Allergens: {', '.join(item['allergens'])}")
            return "\n".join(lines)

        tools.append(explain_dish)

    return tools

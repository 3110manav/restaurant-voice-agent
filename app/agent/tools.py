"""Tool definitions for the ordering agent.

Tools are built per-session via `build_tools`, closing over that session's
cart (a plain list) and a shared MenuStore. Closing over the cart — rather
than threading session_id through every tool call — keeps the tool
signatures simple, which matters because the LLM has to fill them in.
"""
from langchain_core.tools import tool

from app import erp
from app.currency import format_price
from app.rag.menu_store import MenuStore

CartItem = dict  # {"id": str, "name": str, "price": float, "quantity": int}


def _item_descriptor(item: dict) -> str:
    """Build a short "(price, extra bits)" fragment for an item, adapting to
    whichever optional fields its catalog has — food items carry veg/spice
    info, grocery items carry a brand instead."""
    bits = [format_price(item["price"])]
    if "veg" in item:
        bits.append("veg" if item["veg"] else "non-veg")
    if item.get("spice_level"):
        bits.append(f"spice: {item['spice_level']}")
    if item.get("brand"):
        bits.append(f"brand: {item['brand']}")
    return ", ".join(bits)


def add_item_to_cart(cart: list[CartItem], item: dict, quantity: int = 1) -> str:
    """Add `quantity` of an already-resolved menu `item` dict to `cart`.

    Shared by the LLM-facing add_to_cart tool (resolves by name) and the
    direct /cart/add API route (resolves by id) so both paths merge
    quantities into the same cart the same way.
    """
    if quantity < 1:
        return "Quantity must be at least 1."
    for line in cart:
        if line["id"] == item["id"]:
            line["quantity"] += quantity
            return f"Updated {item['name']} to {line['quantity']} in the cart."
    cart.append({"id": item["id"], "name": item["name"], "price": item["price"], "quantity": quantity})
    return f"Added {quantity} x {item['name']} to the cart."


def remove_item_from_cart_by_id(cart: list[CartItem], item_id: str, quantity: int = 1) -> str:
    """Remove `quantity` of the cart line with the given item id.

    Used by the direct /cart/remove API route — the LLM-facing
    remove_from_cart tool matches by name instead, since that's what the
    customer says out loud.
    """
    for line in cart:
        if line["id"] == item_id:
            line["quantity"] -= quantity
            if line["quantity"] <= 0:
                cart.remove(line)
                return f"Removed {line['name']} from the cart."
            return f"Updated {line['name']} to {line['quantity']} in the cart."
    return f"'{item_id}' isn't in the cart."


def build_tools(cart: list[CartItem], menu_store: MenuStore, session_id: str = "", persona: str = "") -> list:
    @tool
    def search_menu(query: str) -> str:
        """Search the catalog by description, category, brand, ingredient, or need.

        Use this whenever the customer asks what's available, wants a
        recommendation, or describes what they're looking for (e.g.
        "something spicy and vegetarian", "a shampoo for dandruff").
        """
        matches = menu_store.search(query)
        if not matches:
            return "No matching items found."
        lines = [
            f"- {item['name']} ({_item_descriptor(item)}): {item['description']}" for item in matches
        ]
        return "\n".join(lines)

    @tool
    def get_item_details(name: str) -> str:
        """Get full details for one named item (ingredients/brand, price, and
        spice level when it's a food item).

        Use this when the customer asks what's in a specific item, e.g.
        "what's in the butter chicken" or "what brand is the shampoo".
        """
        item = menu_store.find_by_name(name)
        if not item:
            return f"No item found matching '{name}'."
        lines = [f"{item['name']} - {format_price(item['price'])}", item["description"]]
        if item.get("ingredients"):
            lines.append(f"Ingredients: {', '.join(item['ingredients'])}")
        if item.get("brand"):
            lines.append(f"Brand: {item['brand']}")
        if "veg" in item:
            veg_spice = "Vegetarian" if item["veg"] else "Non-vegetarian"
            if item.get("spice_level"):
                veg_spice += f", spice level: {item['spice_level']}"
            lines.append(veg_spice)
        return "\n".join(lines)

    @tool
    def add_to_cart(name: str, quantity: int = 1) -> str:
        """Add a quantity of a named menu item to the customer's cart.

        `name` must refer to a real menu item — look it up with search_menu
        or get_item_details first if you're not sure of the exact name.
        """
        item = menu_store.find_by_name(name)
        if not item:
            return f"Couldn't find '{name}' on the menu. Try searching for it first."
        return add_item_to_cart(cart, item, quantity)

    @tool
    def remove_from_cart(name: str, quantity: int = 1) -> str:
        """Remove a quantity of a named item from the cart (removes the line entirely if quantity reaches 0)."""
        for line in cart:
            if line["name"].lower() == name.strip().lower():
                line["quantity"] -= quantity
                if line["quantity"] <= 0:
                    cart.remove(line)
                    return f"Removed {line['name']} from the cart."
                return f"Updated {line['name']} to {line['quantity']} in the cart."
        return f"'{name}' isn't in the cart."

    @tool
    def view_cart() -> str:
        """Show the current cart contents and running total."""
        if not cart:
            return "The cart is empty."
        lines = [f"- {line['quantity']} x {line['name']} ({format_price(line['price'] * line['quantity'])})" for line in cart]
        total = sum(line["price"] * line["quantity"] for line in cart)
        return "\n".join(lines) + f"\nTotal: {format_price(total)}"

    @tool
    def checkout() -> str:
        """Finalize the order. Only call this after the customer explicitly confirms they're done ordering."""
        if not cart:
            return "Can't check out — the cart is empty."
        total = sum(line["price"] * line["quantity"] for line in cart)
        summary = ", ".join(f"{line['quantity']}x {line['name']}" for line in cart)
        erp.record_order(session_id, persona, list(cart), total)
        return f"Order placed: {summary}. Total: {format_price(total)}. Thank you!"

    return [search_menu, get_item_details, add_to_cart, remove_from_cart, view_cart, checkout]

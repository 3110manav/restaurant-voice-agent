"""Tool definitions for the ordering agent.

Tools are built per-session via `build_tools`, closing over that session's
cart (a plain list) and a shared MenuStore. Closing over the cart — rather
than threading session_id through every tool call — keeps the tool
signatures simple, which matters because the LLM has to fill them in.
"""
from langchain_core.tools import tool

from app.rag.menu_store import MenuStore

CartItem = dict  # {"id": str, "name": str, "price": float, "quantity": int}


def build_tools(cart: list[CartItem], menu_store: MenuStore) -> list:
    @tool
    def search_menu(query: str) -> str:
        """Search the restaurant menu by description, cuisine, ingredient, or dietary need.

        Use this whenever the customer asks what's available, wants a
        recommendation, or describes what they're in the mood for
        (e.g. "something spicy and vegetarian", "what breads do you have").
        """
        matches = menu_store.search(query)
        if not matches:
            return "No matching menu items found."
        lines = [
            f"- {item['name']} (${item['price']:.2f}, {'veg' if item['veg'] else 'non-veg'}, "
            f"spice: {item['spice_level']}): {item['description']}"
            for item in matches
        ]
        return "\n".join(lines)

    @tool
    def get_item_details(name: str) -> str:
        """Get full details (ingredients, price, spice level) for one named menu item.

        Use this when the customer asks what's in a specific dish, e.g.
        "what's in the butter chicken" or "is the paneer tikka spicy".
        """
        item = menu_store.find_by_name(name)
        if not item:
            return f"No menu item found matching '{name}'."
        return (
            f"{item['name']} - ${item['price']:.2f}\n"
            f"{item['description']}\n"
            f"Ingredients: {', '.join(item['ingredients'])}\n"
            f"{'Vegetarian' if item['veg'] else 'Non-vegetarian'}, spice level: {item['spice_level']}"
        )

    @tool
    def add_to_cart(name: str, quantity: int = 1) -> str:
        """Add a quantity of a named menu item to the customer's cart.

        `name` must refer to a real menu item — look it up with search_menu
        or get_item_details first if you're not sure of the exact name.
        """
        item = menu_store.find_by_name(name)
        if not item:
            return f"Couldn't find '{name}' on the menu. Try searching for it first."
        if quantity < 1:
            return "Quantity must be at least 1."
        for line in cart:
            if line["id"] == item["id"]:
                line["quantity"] += quantity
                return f"Updated {item['name']} to {line['quantity']} in the cart."
        cart.append({"id": item["id"], "name": item["name"], "price": item["price"], "quantity": quantity})
        return f"Added {quantity} x {item['name']} to the cart."

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
        lines = [f"- {line['quantity']} x {line['name']} (${line['price'] * line['quantity']:.2f})" for line in cart]
        total = sum(line["price"] * line["quantity"] for line in cart)
        return "\n".join(lines) + f"\nTotal: ${total:.2f}"

    @tool
    def checkout() -> str:
        """Finalize the order. Only call this after the customer explicitly confirms they're done ordering."""
        if not cart:
            return "Can't check out — the cart is empty."
        total = sum(line["price"] * line["quantity"] for line in cart)
        summary = ", ".join(f"{line['quantity']}x {line['name']}" for line in cart)
        return f"Order placed: {summary}. Total: ${total:.2f}. Thank you!"

    return [search_menu, get_item_details, add_to_cart, remove_from_cart, view_cart, checkout]

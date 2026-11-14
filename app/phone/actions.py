"""What the owner's WhatsApp buttons do. Only the store's own owner can act on an order, and each move
is conditional on the order's current state, so a double tap or a late tap can't undo anything."""
import logging

from app.phone import messages, numbers, outbox, repository

logger = logging.getLogger("sarthi.phone.actions")


def _tell_customer(order: dict, store: dict, kind: str) -> None:
    recipient = numbers.whatsapp_number(order.get("customer_phone"))
    if not recipient:
        return
    body = messages.customer_update(kind, store["name"], order["payment_ref"], order.get("language") or "hi")
    repository.queue_message(recipient, f"customer_{kind}", body, order["id"], order.get("call_id"))


def _tell_owner(order: dict, store: dict, text: str) -> None:
    repository.queue_message(
        store["owner_whatsapp"], "owner_note", messages.owner_note(text), order["id"], order.get("call_id")
    )


def handle_button(sender: str, button_id: str) -> str:
    """Returns what happened, for the logs and tests."""
    action, _, order_id = button_id.partition(":")
    if action not in ("accept", "out_of_stock", "paid") or not order_id:
        return "ignored"
    order = repository.get_order(order_id)
    store = repository.get_store(order["store_id"]) if order and order.get("store_id") else None
    if store is None:
        return "ignored"
    if numbers.whatsapp_number(sender) != numbers.whatsapp_number(store["owner_whatsapp"]):
        logger.warning("button tap on order %s from someone other than its store's owner", order_id)
        return "not_owner"

    ref = order["payment_ref"]
    if action == "accept":
        moved = repository.move_order(order_id, {"status": "placed"}, {"status": "accepted"})
        if moved:
            _tell_customer(moved, store, "accepted")
            _tell_owner(moved, store, f"Order {ref} accepted. The customer has been told.")
            result = "accepted"
        else:
            _tell_owner(order, store, f"Order {ref} is already {order['status'].replace('_', ' ')}.")
            result = "unchanged"
    elif action == "out_of_stock":
        moved = repository.move_order(order_id, {"status": ["placed", "accepted"]}, {"status": "out_of_stock"})
        if moved:
            _tell_customer(moved, store, "out_of_stock")
            customer = moved.get("customer_phone") or "the customer"
            note = f"Order {ref} marked out of stock. The customer was told not to pay. Please call {customer}."
            if moved["payment_status"] == "paid":
                note = f"Order {ref} marked out of stock, but it was already marked paid. Please refund and call {customer}."
            _tell_owner(moved, store, note)
            result = "out_of_stock"
        else:
            _tell_owner(order, store, f"Order {ref} was already marked out of stock.")
            result = "unchanged"
    else:
        if order["status"] == "out_of_stock":
            _tell_owner(order, store, f"Order {ref} is out of stock, so its bill was cancelled. It wasn't marked paid.")
            result = "unchanged"
        elif repository.move_order(order_id, {"payment_status": "unpaid"}, {"payment_status": "paid"}):
            _tell_customer(order, store, "paid")
            _tell_owner(order, store, f"Order {ref} marked paid. The customer has been told.")
            result = "paid"
        else:
            _tell_owner(order, store, f"Order {ref} was already marked paid.")
            result = "unchanged"
    outbox.flush_in_background()
    return result

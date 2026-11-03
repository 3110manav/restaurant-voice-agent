"""UPI payment links and QR codes. The amount comes from the saved order, never from a request.

A plain UPI link does not tell us when someone has paid, so the store owner confirms it with the
`Paid` button. A transaction reference is only sent for merchant UPI IDs: UPI apps can refuse a
reference on a personal ID, so there the order's code goes in the note instead.
"""
import io
from urllib.parse import quote

import qrcode


def payment_uri(store: dict, amount: float, payment_ref: str) -> str:
    params = {
        "pa": store["upi_id"],
        "pn": store["upi_payee_name"],
        "am": f"{amount:.2f}",
        "cu": "INR",
        "tn": f"Order {payment_ref}",
    }
    if store.get("upi_is_merchant"):
        params["tr"] = payment_ref
    query = "&".join(f"{key}={quote(str(value), safe='@')}" for key, value in params.items())
    return f"upi://pay?{query}"


def qr_png(uri: str) -> bytes:
    image = qrcode.make(uri, box_size=10, border=4)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

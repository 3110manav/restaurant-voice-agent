"""HTTP routes for phone ordering.

GET/POST /whatsapp/webhook  Meta's webhook: the owner's button taps and delivery reports. Every POST
                            must carry a valid signature (WHATSAPP_APP_SECRET).
GET /pay/{token}            The customer's pay page, opened from WhatsApp on the phone they'd pay from,
                            where they can't scan their own screen. Shows no personal details.
GET /pay/{token}/qr.png     That order's QR.
GET /admin/calls            The test view's data. Holds customers' numbers and addresses, so it needs
                            the X-Admin-Key header to match ADMIN_API_KEY, and is off without it.
"""
import hmac
import html
import json
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from app.currency import format_price
from app.phone import actions, repository, upi, whatsapp

logger = logging.getLogger("sarthi.phone.router")

router = APIRouter()


@router.get("/whatsapp/webhook")
def verify_webhook(request: Request) -> Response:
    """Meta calls this once, when the webhook is set up, to check it's ours."""
    params = request.query_params
    expected = os.environ.get("WHATSAPP_VERIFY_TOKEN")
    given = params.get("hub.verify_token") or ""
    if params.get("hub.mode") == "subscribe" and expected and hmac.compare_digest(given, expected):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp/webhook")
async def receive_webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)) -> dict:
    raw = await request.body()
    if not whatsapp.signature_is_valid(raw, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Bad signature")
    payload = json.loads(raw)
    # Always answer 200 once it's verified: Meta retries anything else, which would repeat good events
    # along with the one that failed.
    for tap in whatsapp.button_taps(payload):
        try:
            actions.handle_button(tap["sender"], tap["button_id"])
        except Exception:
            logger.exception("couldn't handle a button tap")
    for update in whatsapp.delivery_updates(payload):
        try:
            repository.update_delivery(update["wa_message_id"], update["status"], update["error"])
        except Exception:
            logger.exception("couldn't record a delivery report")
    return {"status": "ok"}


def _payable_order(token: str) -> tuple[dict, dict]:
    order = repository.order_by_pay_token(token)
    store = repository.get_store(order["store_id"]) if order and order.get("store_id") else None
    if store is None:
        raise HTTPException(status_code=404, detail="This payment link isn't valid")
    return order, store


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Pay {store}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; padding: 32px 16px; text-align: center; background: #fafafa; color: #1a1a1a; }}
main {{ max-width: 360px; margin: 0 auto; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
.ref {{ color: #666; font-size: 14px; }}
.amount {{ font-size: 36px; font-weight: 700; margin: 20px 0; }}
.pay {{ display: block; padding: 16px; border-radius: 12px; background: #16794c; color: #fff; font-size: 18px; font-weight: 600; text-decoration: none; }}
img {{ width: 220px; height: 220px; margin-top: 24px; }}
.note {{ color: #666; font-size: 14px; margin-top: 16px; }}
</style></head><body><main>{content}</main></body></html>"""


@router.get("/pay/{token}", response_class=HTMLResponse)
def pay_page(token: str) -> HTMLResponse:
    order, store = _payable_order(token)
    name = html.escape(store["name"])
    ref = html.escape(order["payment_ref"])
    amount = html.escape(format_price(float(order["total"])))
    head = f'<h1>{name}</h1><div class="ref">Order {ref}</div>'
    if order["status"] == "out_of_stock":
        content = f'{head}<p class="note">This bill was cancelled. Please don\'t pay it. The store will call you.</p>'
    elif order["payment_status"] == "paid":
        content = f'{head}<div class="amount">{amount}</div><p class="note">Paid. Thank you!</p>'
    else:
        uri = html.escape(upi.payment_uri(store, float(order["total"]), order["payment_ref"]), quote=True)
        content = (
            f'{head}<div class="amount">{amount}</div>'
            f'<a class="pay" href="{uri}">Pay with UPI app</a>'
            f'<img src="/pay/{html.escape(token, quote=True)}/qr.png" alt="UPI QR code for this order">'
            '<p class="note">Or scan this QR from another phone.</p>'
        )
    return HTMLResponse(
        _PAGE.format(store=name, content=content),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/pay/{token}/qr.png")
def pay_qr(token: str) -> Response:
    order, store = _payable_order(token)
    if order["status"] == "out_of_stock" or order["payment_status"] == "paid":
        raise HTTPException(status_code=410, detail="This bill is no longer payable")
    uri = upi.payment_uri(store, float(order["total"]), order["payment_ref"])
    return Response(upi.qr_png(uri), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/admin/calls")
def admin_calls(x_admin_key: str | None = Header(default=None)) -> dict:
    expected = os.environ.get("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Set ADMIN_API_KEY on the API to use this view")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Wrong admin key")
    try:
        calls = repository.list_calls()
    except repository.NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    for call in calls:
        if call["order"]:
            call["order"].pop("pay_token", None)
        # The upi link and QR aren't useful here, and the view stays small.
        for message in call["messages"]:
            message["body"] = {k: v for k, v in message["body"].items() if k in ("type", "text", "caption")}
    return {"calls": calls, "whatsapp_configured": whatsapp.is_configured()}

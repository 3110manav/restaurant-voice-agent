"""Check that your WhatsApp credentials work, before any store or agent is involved.

    python -m app.whatsapp_check --phone-number-id 123456789012345
    python -m app.whatsapp_check --phone-number-id 123456789012345 --send +919811111111
    python -m app.whatsapp_check --phone-number-id 123456789012345 --register 123456

Needs WHATSAPP_ACCESS_TOKEN in .env. Without --send it only asks Meta about the number (who it is, its quality
rating): nothing is sent. With --send it sends Meta's built-in `hello_world` template, which every test number
has already approved, to that phone. On Meta's free test number the phone must first be added and verified
under WhatsApp > API Setup > "To".

--register PIN completes the Cloud API registration of a number you added yourself (your own business number):
Meta shows it as "Pending" until this is done. PIN is a six-digit code you choose; it becomes that number's
two-step verification PIN, so keep it. The test number is already registered and doesn't need this.
"""
import argparse
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

from app.customers.phone import normalize_phone  # noqa: E402
from app.whatsapp import client  # noqa: E402
from app.whatsapp.channels import Channel  # noqa: E402


def describe(phone_number_id: str, http: httpx.Client) -> dict:
    """Ask Meta about the number. Raises client.WhatsAppError with Meta's own message on a bad token or id."""
    url = f"{client.GRAPH}/{client.graph_version()}/{phone_number_id}"
    response = http.get(
        url,
        params={"fields": "display_phone_number,verified_name,quality_rating,code_verification_status"},
        headers={"Authorization": f"Bearer {os.environ.get('WHATSAPP_ACCESS_TOKEN')}"},
    )
    if response.status_code >= 400:
        error = response.json().get("error", {})
        raise client.WhatsAppError(f"{error.get('code')}: {error.get('message')}")
    return response.json()


def register(phone_number_id: str, pin: str, http: httpx.Client) -> None:
    """Register the number with the Cloud API (POST /{id}/register). Raises client.WhatsAppError on a rejection."""
    response = http.post(
        f"{client.GRAPH}/{client.graph_version()}/{phone_number_id}/register",
        json={"messaging_product": "whatsapp", "pin": pin},
        headers={"Authorization": f"Bearer {os.environ.get('WHATSAPP_ACCESS_TOKEN')}"},
    )
    if response.status_code >= 400:
        error = response.json().get("error", {})
        raise client.WhatsAppError(f"{error.get('code')}: {error.get('message')}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phone-number-id", required=True)
    p.add_argument("--send", help="a phone to send Meta's hello_world template to")
    p.add_argument("--register", metavar="PIN", help="register your own number with the Cloud API, using this six-digit PIN")
    args = p.parse_args()
    if args.register and not (args.register.isdigit() and len(args.register) == 6):
        p.error("--register needs a six-digit PIN")

    if not os.environ.get("WHATSAPP_ACCESS_TOKEN"):
        print("WHATSAPP_ACCESS_TOKEN is not set in .env")
        return 1
    if args.register:
        try:
            with httpx.Client(timeout=15.0) as http:
                register(args.phone_number_id, args.register, http)
            print("Registered. Keep that PIN: it is now this number's two-step verification PIN.")
        except client.WhatsAppError as exc:
            print(f"Registration failed: {exc}")
            return 1
    try:
        with httpx.Client(timeout=15.0) as http:
            info = describe(args.phone_number_id, http)
    except client.WhatsAppError as exc:
        print(f"Meta rejected the token or the id: {exc}")
        print("A test token lasts 24 hours; make a new one under WhatsApp > API Setup. Check the id is the *Phone number ID*.")
        return 1
    print(f"OK: {info.get('verified_name', '?')} ({info.get('display_phone_number', '?')}), quality {info.get('quality_rating', '?')}")

    if args.send:
        to = normalize_phone(args.send)
        if to is None:
            print(f"{args.send!r} is not a valid phone number")
            return 1
        channel = Channel("check", "check", args.phone_number_id)
        payload = {"to": to.lstrip("+"), "type": "template", "template": {"name": "hello_world", "language": {"code": "en_US"}}}
        try:
            message_id = client._post(channel, payload)
        except client.WhatsAppError as exc:
            print(f"Send failed: {exc}")
            return 1
        print(f"Sent hello_world to {to} (message id {message_id}). Check that phone's WhatsApp.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

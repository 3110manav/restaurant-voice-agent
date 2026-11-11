"""Submit Sarthi's WhatsApp templates to Meta, and check which are approved.

    python -m app.whatsapp_templates --waba-id 123456789012345 --status
    python -m app.whatsapp_templates --waba-id 123456789012345 --submit

--waba-id is the "WhatsApp Business Account ID" shown on WhatsApp > API Setup (not the Phone number ID).
--submit creates every template that doesn't exist yet (existing ones are left alone); Meta then reviews them,
usually within minutes. --status lists each one's state: APPROVED, PENDING or REJECTED (with Meta's reason).
Needs WHATSAPP_ACCESS_TOKEN in .env; the token must be allowed to manage the account (the one from API Setup is).
"""
import argparse
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

from app.whatsapp import client, notify, template_defs  # noqa: E402


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ.get('WHATSAPP_ACCESS_TOKEN')}"}


def _raise(response: httpx.Response) -> None:
    if response.status_code >= 400:
        error = response.json().get("error", {})
        raise client.WhatsAppError(f"{error.get('code')}: {error.get('error_user_msg') or error.get('message')}")


def existing(waba_id: str, http: httpx.Client) -> dict[str, dict]:
    """name -> {status, rejected_reason} for the account's templates in our language."""
    response = http.get(
        f"{client.GRAPH}/{client.graph_version()}/{waba_id}/message_templates",
        params={"fields": "name,status,language,rejected_reason", "limit": 200},
        headers=_headers(),
    )
    _raise(response)
    return {t["name"]: t for t in response.json().get("data", []) if t.get("language", "").startswith(template_defs.LANGUAGE)}


def submit(waba_id: str, http: httpx.Client) -> dict[str, str]:
    """Create every missing template. Returns key -> "created" | "exists" | an error message."""
    have = existing(waba_id, http)
    results = {}
    for key in template_defs.DEFINITIONS:
        name = notify.TEMPLATES[key]
        if name in have:
            results[name] = "exists"
            continue
        response = http.post(
            f"{client.GRAPH}/{client.graph_version()}/{waba_id}/message_templates",
            json={"name": name, "language": template_defs.LANGUAGE, "category": template_defs.CATEGORY, "components": template_defs.components(key)},
            headers=_headers(),
        )
        try:
            _raise(response)
            results[name] = "created"
        except client.WhatsAppError as exc:
            results[name] = f"FAILED {exc}"
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--waba-id", required=True)
    p.add_argument("--submit", action="store_true")
    p.add_argument("--status", action="store_true")
    args = p.parse_args()
    if not os.environ.get("WHATSAPP_ACCESS_TOKEN"):
        print("WHATSAPP_ACCESS_TOKEN is not set in .env")
        return 1
    try:
        with httpx.Client(timeout=30.0) as http:
            if args.submit:
                for name, result in submit(args.waba_id, http).items():
                    print(f"{name:28} {result}")
            have = existing(args.waba_id, http)
            if args.status or args.submit:
                print()
                for key in template_defs.DEFINITIONS:
                    name = notify.TEMPLATES[key]
                    t = have.get(name)
                    reason = f" ({t['rejected_reason']})" if t and t.get("rejected_reason") not in (None, "NONE") else ""
                    print(f"{name:28} {t['status'] if t else 'not created'}{reason}")
    except client.WhatsAppError as exc:
        print(f"Meta refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Register, list or move a store's WhatsApp number (the store_channels table; migration 003).

    python -m app.whatsapp_setup --list
    python -m app.whatsapp_setup --store care-plus-medicals --phone-number-id 123456789012345 \
        --display-number +919000011111 --notify +919811111111 --rx +919822222222

--phone-number-id is Meta's id for the number (WhatsApp Manager > API setup), NOT the phone number.
--notify gets every order alert, --rx gets prescription orders (default: the same as --notify).
Re-running with the same --phone-number-id updates that number. To move a store to a different number,
register the new one and run again with --disable-old <old phone-number-id>; nothing else changes.
"""
import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from app.customers.phone import normalize_phone  # noqa: E402
from app.menu import repository  # noqa: E402
from app.menu.repository import _c  # noqa: E402


def _numbers(raw: str | None) -> list[str]:
    out = []
    for part in (raw or "").split(","):
        if part.strip():
            number = normalize_phone(part)
            if number is None:
                raise SystemExit(f"{part.strip()!r} is not a valid phone number")
            out.append(number)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true")
    p.add_argument("--store", help="the store's slug")
    p.add_argument("--phone-number-id")
    p.add_argument("--display-number")
    p.add_argument("--notify", help="comma-separated numbers that get every order")
    p.add_argument("--rx", help="comma-separated pharmacist numbers (prescription orders)")
    p.add_argument("--token-env", default="WHATSAPP_ACCESS_TOKEN", help="name of the env var holding this number's token")
    p.add_argument("--disable-old", help="a phone-number-id to switch off (moving the store to this number)")
    args = p.parse_args()

    if args.list:
        for row in _c().table("store_channels").select("*, restaurants(slug)").order("created_at").execute().data:
            print(f"{row['restaurants']['slug']:24} {row['phone_number_id']:18} {row.get('display_number') or '-':16} "
                  f"enabled={row['enabled']} notify={row['notify_numbers']} rx={row['rx_numbers']}")
        return 0
    if not (args.store and args.phone_number_id and args.notify):
        p.error("--store, --phone-number-id and --notify are required")
    store = repository.get_restaurant_by_slug(args.store)
    if store is None:
        raise SystemExit(f"no store {args.store!r}")
    row = {
        "restaurant_id": store["id"], "phone_number_id": args.phone_number_id,
        "display_number": args.display_number, "token_env": args.token_env, "enabled": True,
        "notify_numbers": _numbers(args.notify), "rx_numbers": _numbers(args.rx),
    }
    _c().table("store_channels").upsert(row, on_conflict="phone_number_id").execute()
    if args.disable_old:
        _c().table("store_channels").update({"enabled": False}).eq("phone_number_id", args.disable_old).execute()
    print(f"{args.store}: WhatsApp number {args.display_number or args.phone_number_id} registered; "
          f"orders go to {row['notify_numbers']}, prescriptions to {row['rx_numbers'] or row['notify_numbers']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

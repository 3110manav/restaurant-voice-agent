"""Set up the stores that answer phone calls.

Add or update a store (run again to change anything):

    python -m app.phone.setup_store add --slug kirana-demo --name "Sharma Kirana" --type kirana \\
        --agent Veer --owner 9198XXXXXXXX --upi shop@okbank --payee "Sharma Kirana" \\
        --catalog app/data/kirana_demo.json

    python -m app.phone.setup_store add --slug slice-station --name "Slice Station" --type restaurant \\
        --agent Kabir --owner 9198XXXXXXXX --upi shop@okbank --payee "Slice Station" \\
        --restaurant slice-station

Point a dialled number at a store. With one test number, this is how you switch between the two:

    python -m app.phone.setup_store use kirana-demo +91XXXXXXXXXX

Send a restaurant's bills and alerts from its own WhatsApp Business number instead of Sarthi's shared one. The
number must already be on WhatsApp Cloud API in Meta (WhatsApp Manager > Phone numbers), with this app's webhook.
The token goes in an environment variable on the API; only that variable's NAME is stored:

    python -m app.phone.setup_store whatsapp the-fusion-kitchen --phone-number-id 1234567890 \
        --display +91XXXXXXXXXX --token-env WHATSAPP_TOKEN_TFK

    python -m app.phone.setup_store whatsapp the-fusion-kitchen --off     # back to Sarthi's shared number
"""
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.menu import repository as menu_repository  # noqa: E402
from app.phone import numbers, repository  # noqa: E402


def add(args: argparse.Namespace) -> None:
    owner = numbers.whatsapp_number(args.owner)
    if not owner:
        raise SystemExit("--owner must be a mobile number that has WhatsApp")
    if args.type == "kirana" and not (args.catalog or args.restaurant):
        raise SystemExit("A kirana needs --catalog (a file) or --restaurant (the slug of its items in the database)")
    if args.type in ("restaurant", "pharmacy") and not args.restaurant:
        raise SystemExit("A restaurant or pharmacy needs --restaurant, the slug of its menu or medicines")
    database_store = args.type in ("kirana", "pharmacy") and bool(args.restaurant)
    if bool(args.upi) != bool(args.payee):
        raise SystemExit("Give both --upi and --payee, or neither (without them the bill says pay on delivery or at pickup)")
    if not database_store and not args.upi:
        print("No UPI given: bills from this store go without a QR, paid on delivery or at pickup.")
    fields = {
        "slug": args.slug,
        "name": args.name,
        "business_type": args.type,
        "agent_name": args.agent,
        "owner_whatsapp": owner,
        "upi_id": args.upi,
        "upi_payee_name": args.payee,
        "upi_is_merchant": args.merchant,
        "restaurant_slug": args.restaurant,
        "catalog": json.loads(Path(args.catalog).read_text()) if args.catalog else None,
    }
    repository.save_store(fields)
    print(f"Saved {args.slug}.")


def use(args: argparse.Namespace) -> None:
    number = numbers.canonical(args.number)
    if not number:
        raise SystemExit("That doesn't look like a phone number")
    if repository.get_store_by_slug(args.slug) is None:
        raise SystemExit(f"No store '{args.slug}'")
    repository.assign_number(args.slug, number)
    print(f"Calls to {number} now reach {args.slug}.")


def whatsapp(args: argparse.Namespace) -> None:
    restaurant = menu_repository.get_restaurant_by_slug(args.restaurant)
    if restaurant is None:
        raise SystemExit(f"No restaurant '{args.restaurant}'")
    table = repository._c().table("store_channels")
    if args.off:
        table.update({"enabled": False}).eq("restaurant_id", restaurant["id"]).execute()
        print(f"{args.restaurant} now sends from Sarthi's shared WhatsApp number.")
        return
    if not (args.phone_number_id and args.phone_number_id.isdigit()):
        raise SystemExit("--phone-number-id is Meta's id for the number (digits only, from WhatsApp Manager), not the number")
    display = numbers.canonical(args.display) if args.display else None
    if args.display and not display:
        raise SystemExit("--display must be a phone number")
    if not os.environ.get(args.token_env):
        print(f"Note: {args.token_env} isn't set here. Set it on the API (Render) before this number can send.")
    existing = table.select("id, restaurant_id").eq("phone_number_id", args.phone_number_id).execute().data
    if existing and existing[0]["restaurant_id"] != restaurant["id"]:
        raise SystemExit("That number is already connected to another restaurant")
    store = repository.store_for_restaurant(restaurant["slug"])
    notify = [store["owner_whatsapp"]] if store else []
    # One sending number per restaurant: switch the others off, then add or update this one.
    table.update({"enabled": False}).eq("restaurant_id", restaurant["id"]).neq("phone_number_id", args.phone_number_id).execute()
    table.upsert(
        {
            "restaurant_id": restaurant["id"], "phone_number_id": args.phone_number_id, "display_number": display,
            "token_env": args.token_env, "notify_numbers": notify, "enabled": True,
        },
        on_conflict="phone_number_id",
    ).execute()
    print(f"{args.restaurant} now sends bills and alerts from {display or args.phone_number_id} (within 5 minutes).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(required=True)

    add_parser = commands.add_parser("add")
    add_parser.add_argument("--slug", required=True)
    add_parser.add_argument("--name", required=True)
    add_parser.add_argument("--type", required=True, choices=["kirana", "restaurant", "pharmacy"])
    add_parser.add_argument("--agent", required=True)
    add_parser.add_argument("--owner", required=True)
    add_parser.add_argument("--upi", help="the store's UPI ID; without it bills are paid on delivery or at pickup")
    add_parser.add_argument("--payee")
    add_parser.add_argument("--merchant", action="store_true")
    add_parser.add_argument("--catalog")
    add_parser.add_argument("--restaurant")
    add_parser.set_defaults(run=add)

    use_parser = commands.add_parser("use")
    use_parser.add_argument("slug")
    use_parser.add_argument("number")
    use_parser.set_defaults(run=use)

    wa_parser = commands.add_parser("whatsapp", help="send a restaurant's messages from its own WhatsApp number")
    wa_parser.add_argument("restaurant", help="the restaurant's slug")
    wa_parser.add_argument("--phone-number-id", help="Meta's id for the number")
    wa_parser.add_argument("--display", help="the number itself, +91..., shown to the owner")
    wa_parser.add_argument("--token-env", default="WHATSAPP_ACCESS_TOKEN", help="the env variable holding its token")
    wa_parser.add_argument("--off", action="store_true", help="go back to Sarthi's shared number")
    wa_parser.set_defaults(run=whatsapp)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()

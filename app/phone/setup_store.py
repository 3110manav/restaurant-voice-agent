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
"""
import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.phone import hours, numbers, repository  # noqa: E402


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


def set_hours(args: argparse.Namespace) -> None:
    store = repository.get_store_by_slug(args.slug)
    if store is None:
        raise SystemExit(f"No store '{args.slug}'")
    try:
        spans = hours.parse(args.hours)
    except ValueError:
        raise SystemExit('Hours look like "11:00-23:30", or "12:00-15:30, 19:00-01:00", or "closed"')
    if args.always_open:
        opening = None
    else:
        opening = dict(store.get("opening_hours") or {})
        opening[args.day] = spans
    repository.save_store({**store, "opening_hours": opening})
    print(f"{args.slug}: {'always open' if opening is None else opening}")


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

    hours_parser = commands.add_parser("hours", help='opening hours in Indian time, e.g. hours bbc "11:00-23:30"')
    hours_parser.add_argument("slug")
    hours_parser.add_argument("hours", nargs="?", default="", help='"11:00-23:30", "12:00-15:30, 19:00-01:00" or "closed"')
    hours_parser.add_argument("--day", default="daily", choices=["daily", *hours.DAYS])
    hours_parser.add_argument("--always-open", action="store_true", help="remove the hours")
    hours_parser.set_defaults(run=set_hours)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()

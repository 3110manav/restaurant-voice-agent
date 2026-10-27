"""Seed the demo restaurants into Supabase (after supabase/migrations/001 is applied).

    python -m app.seed_restaurants                       # all three, idempotent
    python -m app.seed_restaurants --only slice-station
    python -m app.seed_restaurants --owner you@example.com   # also make that (already signed-up) user the owner
    python -m app.seed_restaurants --check               # validate the data files only; no database, no API calls

Re-running is safe: dishes are matched by name and updated in place, and only
dishes whose embedding text changed are re-embedded (a clean re-run embeds nothing).
The three restaurants: a fine-dine multi-cuisine one (the original 105-dish menu plus
authored dish stories), a Punjabi dhaba, and a pizza chain with sizes.
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.menu import service  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESTAURANTS_DIR = DATA / "restaurants"

FINE_DINE = {
    "slug": "saffron-table",
    "name": "The Saffron Table",
    "cuisine": "Multi-cuisine fine dine",
    "tagline": "Indian, Chinese, Japanese and Italian under one roof.",
    "agent_name": "Kabir",
    "accent_color": "#b45309",
}


def _status(long_description: str) -> str:
    return "approved" if long_description else "missing"


def fine_dine_spec() -> dict:
    items = json.loads((DATA / "menu.json").read_text())
    knowledge = json.loads((RESTAURANTS_DIR / "saffron-table-knowledge.json").read_text())
    categories: list[str] = []
    dishes = []
    for item in items:
        if item["category"] not in categories:
            categories.append(item["category"])
        k = knowledge.get(item["name"], {})
        long_description = k.get("long_description", "")
        dishes.append(
            {
                "category": item["category"],
                "name": item["name"],
                "price": item["price"],
                # Indian veg/non-veg labelling: anything containing egg is not "veg".
                "is_veg": item["veg"] and not any("egg" in i.lower() for i in item.get("ingredients", [])),
                "spice_level": (item.get("spice_level") or "none").lower(),
                "short_description": item["description"],
                "long_description": long_description,
                "ingredients": item.get("ingredients", []),
                "allergens": k.get("allergens", []),
                "tags": k.get("tags", []),
                "knowledge_status": _status(long_description),
            }
        )
    return {"restaurant": FINE_DINE, "categories": categories, "dishes": dishes}


def file_spec(path: Path) -> dict:
    spec = json.loads(path.read_text())
    for dish in spec["dishes"]:
        dish["knowledge_status"] = _status(dish.get("long_description", ""))
    return spec


def load_specs() -> dict[str, dict]:
    specs = {FINE_DINE["slug"]: fine_dine_spec()}
    for slug in ("sarson-da-khet", "slice-station"):
        specs[slug] = file_spec(RESTAURANTS_DIR / f"{slug}.json")
    return specs


def load_starter_menu() -> dict:
    return file_spec(RESTAURANTS_DIR / "starter-menu.json")


def check_spec(slug: str, spec: dict) -> list[str]:
    """Validate a spec offline; returns human-readable problems (empty = fine)."""
    problems = []
    names = set()
    for dish in spec["dishes"]:
        label = f"{slug}: {dish.get('name', '?')}"
        try:
            clean = service.validate_dish(dish, partial=False)
        except service.MenuValidationError as exc:
            problems.append(f"{label}: {exc}")
            continue
        if clean["name"].lower() in names:
            problems.append(f"{label}: duplicate name")
        names.add(clean["name"].lower())
        if dish.get("category") not in spec["categories"]:
            problems.append(f"{label}: category {dish.get('category')!r} not in the categories list")
        if dish.get("variants") and abs(dish["price"] - clean["price"]) > 0.01:
            problems.append(f"{label}: price {dish['price']} != cheapest size {clean['price']}")
        if dish.get("variants") and len(dish["variants"]) < 2:
            problems.append(f"{label}: has only one size")
        words = len(dish.get("long_description", "").split())
        if not 30 <= words <= 140:
            problems.append(f"{label}: story is {words} words")
    return problems


def find_user_id(email: str) -> str | None:
    from app import db

    for page in range(1, 20):
        users = db.get_client().auth.admin.list_users(page=page, per_page=100)
        for user in users:
            if (user.email or "").lower() == email.lower():
                return user.id
        if len(users) < 100:
            break
    return None


def seed(slug: str, spec: dict, owner_email: str | None) -> None:
    from app.menu import repository

    fields = {k: spec["restaurant"][k] for k in ("name", "cuisine", "tagline", "agent_name", "accent_color")}
    restaurant = repository.get_restaurant_by_slug(slug)
    restaurant = (
        repository.insert_restaurant({"slug": slug, **fields})
        if restaurant is None
        else repository.update_restaurant(restaurant["id"], fields)
    )
    service.ensure_categories(restaurant, spec["categories"])
    result = service.bulk_upsert_dishes(restaurant, spec["dishes"], source="manual")
    print(f"  {slug}: {result['written']} dishes written, {result['embedded']} embedded, {result['unchanged']} unchanged")
    if owner_email:
        user_id = find_user_id(owner_email)
        if user_id:
            repository.add_member(restaurant["id"], user_id, "owner")
            print(f"  {slug}: {owner_email} is now an owner")
        else:
            print(f"  {slug}: no account for {owner_email} yet — sign up first, then re-run with --owner")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="seed just this restaurant slug")
    parser.add_argument("--owner", help="email of an existing account to add as owner")
    parser.add_argument("--check", action="store_true", help="validate the data files and exit")
    args = parser.parse_args()

    specs = load_specs()
    specs["__starter__"] = load_starter_menu() if (RESTAURANTS_DIR / "starter-menu.json").exists() else None
    specs = {k: v for k, v in specs.items() if v}
    if args.only:
        specs = {k: v for k, v in specs.items() if k == args.only}
        if not specs:
            print(f"unknown restaurant {args.only!r}")
            return 1

    problems = []
    for slug, spec in specs.items():
        found = check_spec(slug, spec)
        variants = sum(1 for d in spec["dishes"] if d.get("variants"))
        print(f"{slug}: {len(spec['dishes'])} dishes, {len(spec['categories'])} categories, {variants} with sizes, {len(found)} problems")
        problems += found
    for p in problems:
        print("  PROBLEM:", p)
    if args.check or problems:
        return 1 if problems else 0

    for slug, spec in specs.items():
        if slug != "__starter__":
            seed(slug, spec, args.owner)
    return 0


if __name__ == "__main__":
    sys.exit(main())

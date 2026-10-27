"""Find a photo for every dish that has none, host it, and save its link.

    python -m app.menu_images --dry-run            # show which photo each dish would get
    python -m app.menu_images                      # fill every dish without a photo
    python -m app.menu_images --only slice-station # one restaurant
    python -m app.menu_images --force              # redo dishes that already have one
    python -m app.menu_images --allow-weak         # also use best guesses whose description doesn't name the dish

Sources (--provider):
  openverse  no key needed. Openly licensed photos (CC0, public domain, CC BY, CC BY-SA; never
             NoDerivatives or NonCommercial). Most need a visible credit, which the restaurant page
             shows under "Photo credits".
  pexels     better-looking photos, free key in PEXELS_API_KEY (pexels.com/api); credit not required.
The default is pexels when a key is set, otherwise openverse.

Each dish is searched by name, then by name plus its menu section, then by the section alone. Results
are scored by how many words of the dish's name the photo's description contains, and a photo is never
used for two dishes of one restaurant. Dishes that already have a photo are skipped, so the script is
safe to re-run, and it stops cleanly if a source's rate limit is reached. Credits go to
app/data/images/credits.json. A photo is only a link and a file: price, availability and the dish's
embedding are untouched.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()  # before app.db is imported: it reads the Supabase settings when first loaded

from app.menu import images, repository  # noqa: E402
from app.menu.snapshot import menu_cache  # noqa: E402

CREDITS = Path(__file__).parent / "data" / "images" / "credits.json"
USER_AGENT = "SarthiMenuImages/1.0 (restaurant menu prototype)"
_FILLER = {"and", "with", "the", "a", "of", "in", "half", "full", "regular", "medium", "large", "classic", "signature"}
_SECTION_FILLER = {"veg", "non", "classic", "signature", "mains", "menu", "and", "sides", "combos"}
MIN_WIDTH = 640


class RateLimited(Exception):
    pass


def name_words(name: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", name.lower()) if w not in _FILLER and len(w) > 2]


def queries_for(dish: dict) -> list[str]:
    """Most specific search first, then progressively broader."""
    name, section = dish["name"], dish.get("category", "")
    section_words = [w for w in re.findall(r"[A-Za-z]+", section) if w.lower() not in _SECTION_FILLER]
    found = [name]
    if section_words:
        found.append(f"{name} {' '.join(section_words[:2])}")
        found.append(" ".join(section_words[:2]) + " food")
    return list(dict.fromkeys(found))


# Dish names often leave out the dish type ("Smoky BBQ Chicken" in a Pizzas section), so a photo
# must name that type too, or "chicken" is satisfied by a plate of wings.
_DISH_TYPES = {
    "pizza", "pasta", "sandwich", "burger", "wrap", "biryani", "noodles", "dosa", "soup", "salad", "momo", "momos",
    "sushi", "dumpling", "dumplings", "dessert", "cake", "curry", "naan", "bread", "rice", "coffee", "tea",
}


def _stem(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def context_types(dish: dict) -> set[str]:
    """The dish type its menu section names, if any (Non-Veg Pizzas -> pizza)."""
    found = {_stem(w) for w in re.findall(r"[a-z]+", dish.get("category", "").lower())}
    return found & {_stem(t) for t in _DISH_TYPES}


def score(dish: dict, photo: dict) -> int:
    alt = (photo.get("alt") or "").lower()
    return sum(1 for w in name_words(dish["name"]) if w in alt)


def is_match(dish: dict, photo: dict) -> bool:
    """Names (nearly) every word of the dish and, when its section names a dish type, that type."""
    words = name_words(dish["name"])
    if not words or score(dish, photo) < len(words) - (1 if len(words) >= 4 else 0):
        return False
    types = context_types(dish)
    if types and not types & {_stem(w) for w in re.findall(r"[a-z]+", (photo.get("alt") or "").lower())}:
        return False
    return True


def pick_photo(dish: dict, search, used: set[str]) -> tuple[dict | None, bool, str]:
    """The best unused photo for `dish`, whether it is a real match, and the query that found it.

    A real match (see is_match) with the most words in common wins, and the search stops at the
    first query that has one. Failing that, the first unused result is returned as a weak guess
    (matched False), which the caller only uses when told to."""
    best, best_score, best_query, first_any = None, -1, "", None
    for query in queries_for(dish):
        for photo in search(query):
            if photo["id"] in used:
                continue
            if first_any is None:
                first_any = (photo, query)
            if is_match(dish, photo) and score(dish, photo) > best_score:
                best, best_score, best_query = photo, score(dish, photo), query
        if best is not None:
            return best, True, best_query
    return (first_any[0], False, first_any[1]) if first_any else (None, False, "")


# ---------------------------------------------------------------- sources

def _get_with_retries(client: httpx.Client, url: str, params: dict, attempts: int = 3) -> httpx.Response | None:
    """A GET that survives a timeout or dropped connection (None if it never works), so one
    slow response skips one search instead of ending a run that takes minutes."""
    for attempt in range(attempts):
        try:
            return client.get(url, params=params)
        except httpx.TransportError as exc:
            print(f"    ({type(exc).__name__} searching, attempt {attempt + 1} of {attempts})")
            time.sleep(2 * (attempt + 1))
    return None


def pexels_search(api_key: str):
    client = httpx.Client(timeout=20, headers={"Authorization": api_key, "User-Agent": USER_AGENT})
    nearly_out = False

    def search(query: str) -> list[dict]:
        nonlocal nearly_out
        if nearly_out:
            raise RateLimited("Pexels' hourly limit is nearly used up")
        response = _get_with_retries(
            client, "https://api.pexels.com/v1/search", {"query": query, "per_page": 8, "orientation": "landscape"}
        )
        if response is None:
            return []
        if response.status_code == 429:
            raise RateLimited("Pexels' hourly limit reached")
        response.raise_for_status()
        nearly_out = int(response.headers.get("X-Ratelimit-Remaining", 99)) <= 3
        return [
            {
                "id": f"pexels:{p['id']}",
                "alt": p.get("alt") or "",
                "page": p.get("url"),
                "creator": p.get("photographer"),
                "license": "Pexels License",
                "license_url": "https://www.pexels.com/license/",
                "credit": f"Photo by {p.get('photographer')} on Pexels",
                "download": [p["src"]["large"]],
            }
            for p in response.json().get("photos", [])
        ]

    return search


_LICENSE_NAMES = {"cc0": "CC0 1.0", "pdm": "Public Domain Mark 1.0"}


def _openverse_photo(x: dict) -> dict | None:
    if (x.get("width") or 0) < MIN_WIDTH:
        return None
    kind = x["license"].lower()
    version = x.get("license_version") or ""
    license_name = _LICENSE_NAMES.get(kind) or f"CC {kind.upper()} {version}".strip()
    tags = " ".join(t["name"] for t in x.get("tags") or [])
    creator = x.get("creator") or "unknown author"
    title = x.get("title") or "Untitled"
    # Originals can be huge and live on someone else's server; the API's own thumbnail is the fallback.
    download = [x["url"], x["thumbnail"]] if (x.get("width") or 0) <= 3000 else [x["thumbnail"], x["url"]]
    return {
        "id": f"openverse:{x['id']}",
        "alt": f"{title} {tags}",
        "page": x.get("foreign_landing_url"),
        "creator": creator,
        "license": license_name,
        "license_url": x.get("license_url"),
        "credit": f'"{title}" by {creator}, {license_name}',
        "download": [u for u in download if u],
    }


def openverse_search():
    client = httpx.Client(timeout=25, headers={"User-Agent": USER_AGENT})

    def search(query: str) -> list[dict]:
        time.sleep(0.4)  # be polite: anonymous use is rate limited
        response = _get_with_retries(
            client,
            "https://api.openverse.org/v1/images/",
            {
                "q": query,
                "license": "cc0,pdm,by,by-sa",
                "license_type": "commercial",
                "category": "photograph",
                "mature": "false",
                "page_size": 10,
            },
        )
        if response is None:
            return []
        if response.status_code == 429:
            raise RateLimited("Openverse's rate limit reached")
        response.raise_for_status()
        return [p for p in (_openverse_photo(x) for x in response.json().get("results", [])) if p]

    return search


# ---------------------------------------------------------------- the run

def run(
    slug: str, search, download, store, dry_run: bool, force: bool, limit: int | None, credits: dict,
    allow_weak: bool = True,
) -> dict:
    menu_cache.invalidate(slug)
    menu = menu_cache.get(slug)
    if menu is None:
        raise SystemExit(f"no restaurant '{slug}'")
    restaurant = menu.restaurant
    used = {c["photo_id"] for c in credits.get(slug, {}).values() if "photo_id" in c}
    done = weak = skipped = 0
    left_out = []
    for dish in menu.menu:
        if dish.get("image_url") and not force:
            skipped += 1
            continue
        if limit is not None and done >= limit:
            break
        photo, matched, query = pick_photo(dish, search, used)
        if photo is None:
            left_out.append(dish["name"])
            print(f"  --  {dish['name']}: no photo found")
            continue
        if not matched and not allow_weak:
            left_out.append(dish["name"])
            print(f"  --  {dish['name']}: only a weak match ({(photo['alt'] or '')[:50]!r}); left without a photo")
            continue
        weak += 0 if matched else 1
        print(f"  {'would use' if dry_run else 'ok'}  {dish['name']:32s} <- {photo['alt'][:70]}" + ("  (weak match)" if not matched else ""))
        used.add(photo["id"])
        done += 1
        if dry_run:
            continue
        url = store(slug, dish["id"], download(photo["download"]))
        repository.update_dish(restaurant["id"], dish["id"], {"image_url": url})
        credits.setdefault(slug, {})[dish["name"]] = {
            "photo_id": photo["id"],
            "image_url": url,
            "credit": photo["credit"],
            "creator": photo["creator"],
            "license": photo["license"],
            "license_url": photo.get("license_url"),
            "page": photo.get("page"),
            "matched_with": query,
            "weak": not matched,
        }
    if done and not dry_run:
        repository.bump_menu_version(restaurant["id"])
        menu_cache.invalidate(slug)
    return {"photos": done, "weak": weak, "skipped": skipped, "left_out": left_out}


def load_credits() -> dict:
    return json.loads(CREDITS.read_text()) if CREDITS.exists() else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="one restaurant slug")
    parser.add_argument("--provider", choices=["openverse", "pexels"])
    parser.add_argument("--force", action="store_true", help="replace photos that already exist")
    parser.add_argument("--dry-run", action="store_true", help="show the matches without uploading")
    parser.add_argument("--allow-weak", action="store_true", help="use best guesses that don't name the dish")
    parser.add_argument("--limit", type=int, help="at most this many dishes per restaurant")
    args = parser.parse_args()

    key = os.environ.get("PEXELS_API_KEY")
    provider = args.provider or ("pexels" if key else "openverse")
    if provider == "pexels" and not key:
        sys.exit("PEXELS_API_KEY is not set. Get a free key at https://www.pexels.com/api/ or use --provider openverse")
    search = pexels_search(key) if provider == "pexels" else openverse_search()
    print(f"Photo source: {provider}")

    slugs = [args.only] if args.only else repository.list_restaurant_slugs()
    credits = load_credits()
    http = httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    if not args.dry_run:
        images.ensure_bucket()

    def download(urls: list[str]) -> bytes:
        last = None
        for url in urls:
            try:
                response = http.get(url)
                response.raise_for_status()
                return images.prepare(response.content)
            except Exception as exc:  # a dead link or an unreadable file: try the next source of the same photo
                last = exc
        raise RuntimeError(f"couldn't download the photo: {last}")

    try:
        for slug in slugs:
            print(f"\n{slug}")
            result = run(
                slug, search, download, images.store_image, args.dry_run, args.force, args.limit, credits,
                allow_weak=args.allow_weak or provider == "pexels",
            )
            print(f"  -> {result['photos']} photos ({result['weak']} weak), {result['skipped']} already had one, {len(result['left_out'])} left without")
    except RateLimited as exc:
        print(f"\nStopped: {exc}. Run the command again later; finished dishes are skipped.")
    finally:
        if not args.dry_run:
            CREDITS.parent.mkdir(parents=True, exist_ok=True)
            CREDITS.write_text(json.dumps(credits, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

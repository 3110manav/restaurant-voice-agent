"""One store's catalog, held on its phone_stores row and searched in memory.

Callers say "cheeni" or "चीनी" as often as "sugar", and speech-to-text may write any of those, so each
item can carry `aliases`. Pack sizes are ordinary variants ("500 g", "1 kg"). Same interface as the
restaurants' LiveMenu (app/menu/snapshot.py), so app/agent/tools.py works on both.
"""
from rapidfuzz import fuzz, process

from app.menu.snapshot import FUZZY_CUTOFF, _norm


class StoreCatalog:
    def __init__(self, items: list[dict]):
        self.menu = [
            {"description": "", "variants": [], "is_available": True, **item} for item in items
        ]
        self.by_id = {item["id"]: item for item in self.menu}
        # Every name an item goes by, each pointing back at the item.
        self._names = [
            (_norm(name), item) for item in self.menu for name in [item["name"], *item.get("aliases", [])]
        ]
        self._keys = [name for name, _ in self._names]

    @property
    def categories(self) -> list[str]:
        return list(dict.fromkeys(item.get("category", "Other") for item in self.menu))

    def get(self, item_id: str) -> dict | None:
        return self.by_id.get(item_id)

    def candidates(self, name: str, limit: int = 4) -> list[dict]:
        q = _norm(name)
        if not q:
            return []
        hits = [item for key, item in self._names if q in key or (len(key) > 2 and key in q)]
        if not hits:
            found = process.extract(q, self._keys, scorer=fuzz.WRatio, limit=limit, score_cutoff=FUZZY_CUTOFF)
            hits = [self._names[idx][1] for _, _, idx in found]
        return list({item["id"]: item for item in hits}.values())[:limit]

    def find_by_name(self, name: str) -> dict | None:
        q = _norm(name)
        if not q:
            return None
        for key, item in self._names:
            if key == q:
                return item
        options = self.candidates(name)
        return options[0] if len(options) == 1 else None

    def search(self, query: str, k: int = 4) -> list[dict]:
        tokens = [t for t in _norm(query).split() if len(t) > 1]
        scored = []
        for item in self.menu:
            if not item["is_available"]:
                continue
            haystack = _norm(
                " ".join(
                    [
                        item["name"],
                        item.get("category", ""),
                        item.get("brand", ""),
                        item["description"],
                        " ".join(item.get("aliases", [])),
                    ]
                )
            )
            score = sum(1 for t in tokens if t in haystack)
            if score:
                scored.append((score, item))
        scored.sort(key=lambda pair: -pair[0])
        return [item for _, item in scored[:k]]

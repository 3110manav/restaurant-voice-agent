"""Gemini embeddings for dishes and search queries.

Three things here exist to keep the free tier (100 embedded texts/minute) from
ever being the bottleneck:

- `dish_embedding_text` / `content_hash`: only the semantic parts of a dish are
  embedded — never price, availability, image or POS id — so a price change (the
  most common edit) costs zero embedding calls, and editing one dish re-embeds
  just that dish, not the menu.
- A shared sliding-window budget (`_wait_for_budget`) that every embedding call
  goes through, so a bulk menu upload, a live edit and a guest's search can't
  collectively trip the rate limit.
- A query-embedding LRU: the vector for "something spicy" doesn't depend on the
  restaurant, so repeated phrasings are free across every restaurant and guest.
"""
import hashlib
import threading
import time
from collections import OrderedDict, deque

from langchain_google_genai import GoogleGenerativeAIEmbeddings

EMBED_MODEL = "models/gemini-embedding-001"
EMBED_DIM = 768  # reduced from the model's native 3072; plenty for a few hundred dishes
EMBED_BATCH_SIZE = 40
# The free tier allows 100 embedded texts/minute. Bulk document embedding may use at most
# 80 of them, leaving room so a guest's live search query never waits behind an upload.
DOCUMENT_BUDGET = 80
QUERY_BUDGET = 95
QUERY_CACHE_SIZE = 2000

_lock = threading.Lock()
_window: deque[tuple[float, int]] = deque()  # (timestamp, texts embedded)
_query_cache: OrderedDict[str, list[float]] = OrderedDict()
_embeddings: GoogleGenerativeAIEmbeddings | None = None


def _client() -> GoogleGenerativeAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = GoogleGenerativeAIEmbeddings(model=EMBED_MODEL, output_dimensionality=EMBED_DIM)
    return _embeddings


def dish_embedding_text(dish: dict) -> str:
    """The text that represents a dish in vector space. Deliberately excludes
    price, availability, image and POS fields (see module docstring)."""
    parts = [f"{dish['name']} ({dish.get('category') or 'Menu'})"]
    if dish.get("description"):
        parts.append(dish["description"])
    if dish.get("long_description"):
        parts.append(dish["long_description"])
    if dish.get("ingredients"):
        parts.append(f"Ingredients: {', '.join(dish['ingredients'])}.")
    if dish.get("tags"):
        parts.append(f"Tags: {', '.join(dish['tags'])}.")
    parts.append("Vegetarian." if dish.get("veg", True) else "Non-vegetarian.")
    if dish.get("spice_level") and dish["spice_level"] != "none":
        parts.append(f"Spice level: {dish['spice_level']}.")
    return " ".join(parts)


def content_hash(text: str) -> str:
    return hashlib.sha256(f"{EMBED_MODEL}:{EMBED_DIM}:{text}".encode()).hexdigest()


def _wait_for_budget(n: int, limit: int) -> None:
    """Block until embedding `n` more texts keeps us under `limit` for the last minute."""
    while True:
        with _lock:
            now = time.monotonic()
            while _window and now - _window[0][0] >= 60:
                _window.popleft()
            used = sum(count for _, count in _window)
            if used + n <= limit or not _window:
                _window.append((now, n))
                return
            wait = 60 - (now - _window[0][0]) + 0.5
        time.sleep(max(wait, 0.5))


def _with_retry(fn):
    try:
        return fn()
    except Exception as exc:  # the API's quota error text varies by client version
        if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
            time.sleep(62)
            return fn()
        raise


def embed_documents(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        _wait_for_budget(len(batch), DOCUMENT_BUDGET)
        vectors.extend(_with_retry(lambda b=batch: _client().embed_documents(b, task_type="RETRIEVAL_DOCUMENT")))
    return vectors


def embed_query(text: str) -> list[float]:
    key = " ".join(text.lower().split())
    with _lock:
        if key in _query_cache:
            _query_cache.move_to_end(key)
            return _query_cache[key]
    _wait_for_budget(1, QUERY_BUDGET)
    vector = _with_retry(lambda: _client().embed_query(key, task_type="RETRIEVAL_QUERY"))
    with _lock:
        _query_cache[key] = vector
        if len(_query_cache) > QUERY_CACHE_SIZE:
            _query_cache.popitem(last=False)
    return vector

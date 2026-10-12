"""Embeds a catalog (the restaurant menu, or the quick-commerce grocery
catalog) into a persistent local Chroma vector store for semantic retrieval.

This is the RAG layer: instead of stuffing the whole catalog into every
prompt, we embed each item once and retrieve only the relevant ones per
query (e.g. "something spicy and vegetarian", or "something for a headache").

The index is persisted to disk and keyed off a hash of the source JSON, so a
process restart reuses the existing embeddings instead of recomputing them.
This matters once a catalog is past a couple dozen items: Gemini's free
embedding tier caps out at 100 requests/minute, and re-embedding the full
catalog on every launch burns through that immediately. The one-time initial
build is throttled in batches to stay under that cap.

Two catalogs share this same class, each with its own data file and Chroma
collection (so their embeddings, hash files, and rebuild checks never
collide) — see MENU_PATH/"restaurant_menu" for food and GROCERY_PATH/
"grocery_catalog" for quick-commerce in app/main.py.
"""
import hashlib
import json
import time
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MENU_PATH = DATA_DIR / "menu.json"
GROCERY_PATH = DATA_DIR / "grocery.json"
PERSIST_DIR = Path(__file__).resolve().parent.parent.parent / "chroma_db"

# Free-tier Gemini embeddings: 100 requests/minute. Stay comfortably under
# that per batch, and pause long enough for the per-minute window to clear
# between batches.
EMBED_BATCH_SIZE = 40
EMBED_BATCH_PAUSE_SECONDS = 65


def load_items(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def _catalog_hash(items: list[dict]) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()


def _item_to_document(item: dict) -> Document:
    # Fields vary by catalog (food items have veg/spice_level/ingredients;
    # grocery items have brand instead) — build the embedded text from
    # whichever are present rather than assuming a fixed food-only schema.
    parts = [f"{item['name']} ({item['category']})"]
    if item.get("brand"):
        parts.append(f"by {item['brand']}.")
    parts.append(f"- {item['description']}")
    if item.get("ingredients"):
        parts.append(f"Ingredients: {', '.join(item['ingredients'])}.")
    if "veg" in item:
        parts.append("Vegetarian." if item["veg"] else "Non-vegetarian.")
    if item.get("spice_level"):
        parts.append(f"Spice level: {item['spice_level']}.")
    parts.append(f"Price: ${item['price']:.2f}.")
    text = " ".join(parts)
    return Document(page_content=text, metadata={"id": item["id"], "name": item["name"], "price": item["price"]})


class MenuStore:
    """Wraps a persisted Chroma collection built from a catalog, plus lookup by id/name."""

    def __init__(self, data_path: Path = MENU_PATH, collection_name: str = "restaurant_menu"):
        self.menu = load_items(data_path)
        self.by_id = {item["id"]: item for item in self.menu}
        documents = [_item_to_document(item) for item in self.menu]

        embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
        PERSIST_DIR.mkdir(exist_ok=True)
        hash_file = PERSIST_DIR / f".{collection_name}_hash"
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=str(PERSIST_DIR),
        )

        current_hash = _catalog_hash(self.menu)
        cached_hash = hash_file.read_text().strip() if hash_file.exists() else None
        indexed_count = len(self.vectorstore.get(include=[])["ids"])

        if cached_hash == current_hash and indexed_count == len(documents):
            return  # persisted index already matches the current catalog

        if indexed_count:
            self.vectorstore.delete_collection()
            self.vectorstore = Chroma(
                collection_name=collection_name,
                embedding_function=embeddings,
                persist_directory=str(PERSIST_DIR),
            )

        for i in range(0, len(documents), EMBED_BATCH_SIZE):
            batch = documents[i : i + EMBED_BATCH_SIZE]
            self.vectorstore.add_documents(batch)
            if i + EMBED_BATCH_SIZE < len(documents):
                time.sleep(EMBED_BATCH_PAUSE_SECONDS)

        hash_file.write_text(current_hash)

    def search(self, query: str, k: int = 4) -> list[dict]:
        results = self.vectorstore.similarity_search(query, k=k)
        return [self.by_id[doc.metadata["id"]] for doc in results]

    def get(self, item_id: str) -> dict | None:
        return self.by_id.get(item_id)

    def find_by_name(self, name: str) -> dict | None:
        name_lower = name.strip().lower()
        for item in self.menu:
            if item["name"].lower() == name_lower:
                return item
        for item in self.menu:
            if name_lower in item["name"].lower():
                return item
        return None

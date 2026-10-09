"""Embeds the menu into a persistent local Chroma vector store for
semantic retrieval.

This is the RAG layer: instead of stuffing the whole menu into every
prompt, we embed each item once and retrieve only the relevant ones per
query (e.g. "something spicy and vegetarian").

The index is persisted to disk and keyed off a hash of menu.json, so a
process restart reuses the existing embeddings instead of recomputing
them. This matters once the menu is past a couple dozen items: Gemini's
free embedding tier caps out at 100 requests/minute, and re-embedding the
full menu on every launch burns through that immediately. The one-time
initial build is throttled in batches to stay under that cap.
"""
import hashlib
import json
import time
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

MENU_PATH = Path(__file__).resolve().parent.parent / "data" / "menu.json"
PERSIST_DIR = Path(__file__).resolve().parent.parent.parent / "chroma_db"
HASH_FILE = PERSIST_DIR / ".menu_hash"
COLLECTION_NAME = "restaurant_menu"

# Free-tier Gemini embeddings: 100 requests/minute. Stay comfortably under
# that per batch, and pause long enough for the per-minute window to clear
# between batches.
EMBED_BATCH_SIZE = 40
EMBED_BATCH_PAUSE_SECONDS = 65


def load_menu() -> list[dict]:
    with open(MENU_PATH) as f:
        return json.load(f)


def _menu_hash(menu: list[dict]) -> str:
    return hashlib.sha256(json.dumps(menu, sort_keys=True).encode()).hexdigest()


def _menu_item_to_document(item: dict) -> Document:
    text = (
        f"{item['name']} ({item['category']}) - {item['description']} "
        f"Ingredients: {', '.join(item['ingredients'])}. "
        f"{'Vegetarian' if item['veg'] else 'Non-vegetarian'}. "
        f"Spice level: {item['spice_level']}. Price: ${item['price']:.2f}."
    )
    return Document(page_content=text, metadata={"id": item["id"], "name": item["name"], "price": item["price"]})


class MenuStore:
    """Wraps a persisted Chroma collection built from the menu, plus lookup by id."""

    def __init__(self):
        self.menu = load_menu()
        self.by_id = {item["id"]: item for item in self.menu}
        documents = [_menu_item_to_document(item) for item in self.menu]

        embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
        PERSIST_DIR.mkdir(exist_ok=True)
        self.vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(PERSIST_DIR),
        )

        current_hash = _menu_hash(self.menu)
        cached_hash = HASH_FILE.read_text().strip() if HASH_FILE.exists() else None
        indexed_count = len(self.vectorstore.get(include=[])["ids"])

        if cached_hash == current_hash and indexed_count == len(documents):
            return  # persisted index already matches the current menu

        if indexed_count:
            self.vectorstore.delete_collection()
            self.vectorstore = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=embeddings,
                persist_directory=str(PERSIST_DIR),
            )

        for i in range(0, len(documents), EMBED_BATCH_SIZE):
            batch = documents[i : i + EMBED_BATCH_SIZE]
            self.vectorstore.add_documents(batch)
            if i + EMBED_BATCH_SIZE < len(documents):
                time.sleep(EMBED_BATCH_PAUSE_SECONDS)

        HASH_FILE.write_text(current_hash)

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

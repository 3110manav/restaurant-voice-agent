"""A call's cart, saved as it changes (supabase/migrations/009_carts.sql).

The live cart is still the in-memory list the order rules work on; this keeps a copy in the database so that
  - a restart in the middle of a call doesn't lose it (the next tool call restores it),
  - a call that ends without an order leaves an "abandoned" cart the store can see and, later, call back about,
  - the owner can count how many callers dropped off.

Saving is best effort and off the call's path: a database hiccup is logged and never slows or breaks a call.
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from app.phone import repository

logger = logging.getLogger("sarthi.carts")

SWEEP_SECONDS = 300

# One worker, so saves of the same cart land in the order they were made.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="carts")


def run_later(fn, *args) -> None:
    """Runs `fn` after the tool call has answered. Tests replace this with a direct call."""
    _executor.submit(_guarded, fn, *args)


def _guarded(fn, *args) -> None:
    try:
        fn(*args)
    except Exception:
        logger.warning("couldn't save a cart", exc_info=True)


def save(row: dict) -> None:
    repository._c().table("carts").upsert(row, on_conflict="interaction_id").execute()


def load(interaction_id: str) -> dict | None:
    """The saved cart of a call, or None if there is none or the database can't be read."""
    try:
        rows = repository._c().table("carts").select("*").eq("interaction_id", interaction_id).limit(1).execute().data
    except Exception:
        logger.warning("couldn't read the saved cart of %s", interaction_id, exc_info=True)
        return None
    return rows[0] if rows else None


def mark_recovered(restaurant_id: str, phone: str, order_id: str) -> None:
    """This customer ordered, so an earlier abandoned cart of theirs at this store counts as won back."""
    repository._c().table("carts").update(
        {"status": "recovered", "order_id": order_id, "closed_at": repository.now_iso(), "closed_reason": "ordered_later"}
    ).eq("restaurant_id", restaurant_id).eq("customer_phone", phone).eq("status", "abandoned").execute()


def sweep() -> dict | None:
    """Moves quiet carts to abandoned, abandoned ones past the window to expired, and closes calls whose
    'ended' message never came. Returns the counts."""
    return repository._c().rpc("close_stale_carts", {}).execute().data


def run_forever(stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    complained = False
    while not stop.is_set():
        try:
            counts = sweep()
            complained = False
            if counts and any(counts.values()):
                logger.info("cart sweep: %s", counts)
        except repository.NotConfiguredError:
            return
        except Exception:
            if not complained:  # e.g. migration 009 not run yet; once is enough
                logger.exception("couldn't sweep carts")
                complained = True
        if stop.wait(SWEEP_SECONDS):
            return


def start() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=run_forever, args=(stop,), daemon=True).start()
    return stop

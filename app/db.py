"""The one Supabase client for the backend (service key, bypasses RLS — see
supabase/migrations/001_multi_restaurant.sql for why RLS is defense in depth,
not the main gate). Everything that talks to Supabase goes through get_client()
so a missing SUPABASE_URL / SUPABASE_SERVICE_KEY degrades the same way
everywhere: callers get None and skip persistence."""
import functools
import logging
import os

import httpx
from supabase import Client, create_client

logger = logging.getLogger("sarthi.db")

_client: Client | None = None
_url = os.environ.get("SUPABASE_URL")
_key = os.environ.get("SUPABASE_SERVICE_KEY")
if _url and _key:
    _client = create_client(_url, _key)


def get_client() -> Client | None:
    return _client


def is_configured() -> bool:
    return _client is not None


def retry_read(fn):
    """Run a read once more when the connection drops. Supabase closes idle HTTP/2 connections, and the first request
    on a stale one fails with "Server disconnected" (httpx.TransportError): a dashboard that sat quiet for a minute
    showed a 500. Only for reads: repeating a write could do it twice."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except httpx.TransportError as exc:
            logger.info("retrying %s after %s", fn.__name__, type(exc).__name__)
            return fn(*args, **kwargs)

    return wrapper

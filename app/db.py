"""The one Supabase client for the backend (service key, bypasses RLS — see
supabase/migrations/001_multi_restaurant.sql for why RLS is defense in depth,
not the main gate). Everything that talks to Supabase goes through get_client()
so a missing SUPABASE_URL / SUPABASE_SERVICE_KEY degrades the same way
everywhere: callers get None and skip persistence."""
import os

from supabase import Client, create_client

_client: Client | None = None
_url = os.environ.get("SUPABASE_URL")
_key = os.environ.get("SUPABASE_SERVICE_KEY")
if _url and _key:
    _client = create_client(_url, _key)


def get_client() -> Client | None:
    return _client


def is_configured() -> bool:
    return _client is not None

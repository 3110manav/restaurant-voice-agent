"""The platform admin's key (ADMIN_API_KEY), sent as the X-Admin-Key header. Admin routes are off without it."""
import hmac
import os

from fastapi import Header, HTTPException


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Set ADMIN_API_KEY on the API to use this view")
    if not x_admin_key or not hmac.compare_digest(x_admin_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Wrong admin key")

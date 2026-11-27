"""POS onboarding: credentials are encrypted at rest and never come back out of the API; the admin key gates it."""
import base64
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.menu import repository as menu_repository
from app.pos import admin_api, crypto, repository
from tests.fake_supabase import FakeSupabase

KEY = base64.b64encode(b"k" * 32).decode()
OTHER_KEY = base64.b64encode(b"o" * 32).decode()
SECRETS = {
    "app_key": "appkey-1234567890abcd",
    "app_secret": "appsecret-0987654321wxyz",
    "access_token": "token-abcdefghijklmnop",
}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("POS_ENCRYPTION_KEY", KEY)
    monkeypatch.delenv("POS_ENCRYPTION_KEY_PREVIOUS", raising=False)
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.example.com/")
    client = FakeSupabase()
    client.tables["restaurants"] = [{"id": "r1", "name": "Fusion", "slug": "fusion", "status": "live"}]
    monkeypatch.setattr(db, "get_client", lambda: client)
    monkeypatch.setattr(db, "is_configured", lambda: True)
    return client


@pytest.fixture
def api(env):
    app = FastAPI()
    app.include_router(admin_api.router)
    return TestClient(app)


# ---------------------------------------------------------------- crypto ----


def test_round_trip_and_context_binding(env):
    sealed = crypto.encrypt("s3cret", "row-1:app_secret")
    assert "s3cret" not in sealed and sealed.startswith("v1.")
    assert crypto.decrypt(sealed, "row-1:app_secret") == "s3cret"
    with pytest.raises(crypto.DecryptError):
        crypto.decrypt(sealed, "row-2:app_secret")  # copied to another row
    with pytest.raises(crypto.DecryptError):
        crypto.decrypt(sealed, "row-1:access_token")  # copied to another column


def test_same_value_encrypts_differently(env):
    assert crypto.encrypt("x", "c") != crypto.encrypt("x", "c")


def test_key_rotation_keeps_old_values_readable(env, monkeypatch):
    old = crypto.encrypt("value", "ctx")
    monkeypatch.setenv("POS_ENCRYPTION_KEY", OTHER_KEY)
    with pytest.raises(crypto.DecryptError):
        crypto.decrypt(old, "ctx")
    monkeypatch.setenv("POS_ENCRYPTION_KEY_PREVIOUS", KEY)
    assert crypto.decrypt(old, "ctx") == "value"
    assert crypto.needs_reencrypt(old)


def test_missing_or_bad_key(monkeypatch):
    monkeypatch.delenv("POS_ENCRYPTION_KEY", raising=False)
    assert not crypto.is_configured()
    monkeypatch.setenv("POS_ENCRYPTION_KEY", base64.b64encode(b"short").decode())
    with pytest.raises(crypto.CryptoNotConfigured):
        crypto.encrypt("x", "c")


def test_token_hash(env):
    token = crypto.new_webhook_token()
    assert crypto.token_matches(token, crypto.hash_token(token))
    assert not crypto.token_matches(token + "x", crypto.hash_token(token))


# ------------------------------------------------------------------- API ----


def _onboard(api, **overrides):
    body = {"restaurant_id": "r1", "environment": "sandbox", "pos_restaurant_id": "f871uxkp", **SECRETS, **overrides}
    return api.post("/admin/pos/integrations", json=body, headers={"X-Admin-Key": "admin-secret"})


def test_admin_key_required(api):
    assert api.get("/admin/pos/overview").status_code == 401
    assert api.get("/admin/pos/overview", headers={"X-Admin-Key": "nope"}).status_code == 401


def test_onboard_encrypts_and_never_returns_secrets(api, env):
    res = _onboard(api)
    assert res.status_code == 200, res.text
    body = res.json()
    text = json.dumps(body)
    for value in SECRETS.values():
        assert value not in text
    assert body["integration"]["app_key_hint"] == "abcd"
    assert "app_key_enc" not in body["integration"] and "webhook_token_hash" not in body["integration"]
    assert body["webhook"]["base_url"] == "https://api.example.com/pos/petpooja/"
    token = body["webhook"]["client_authorization"].removeprefix("Bearer ")

    stored = env.tables["pos_integrations"][0]
    for field, value in SECRETS.items():
        assert value not in json.dumps(stored)
        assert stored[f"{field}_enc"].startswith("v1.")
    assert stored["webhook_token_hash"] == crypto.hash_token(token)

    creds = repository.get_credentials(stored["id"])
    assert (creds.app_key, creds.app_secret, creds.access_token) == tuple(SECRETS.values())
    assert "appsecret" not in repr(creds)

    overview = api.get("/admin/pos/overview", headers={"X-Admin-Key": "admin-secret"}).json()
    assert all(v not in json.dumps(overview) for v in SECRETS.values())
    assert overview["encryption_ready"] is True


def test_onboard_new_restaurant_is_draft(api, env, monkeypatch):
    monkeypatch.setattr(menu_repository, "get_restaurant_by_slug", lambda slug: None)
    res = _onboard(api, restaurant_id=None, new_restaurant={"name": "The Fusion Kitchen Sandbox"})
    assert res.status_code == 200, res.text
    created = [r for r in env.tables["restaurants"] if r["slug"] == "the-fusion-kitchen-sandbox"]
    assert created and created[0]["status"] == "draft"


def test_validation(api):
    assert _onboard(api, pos_restaurant_id="bad id!").status_code == 422
    assert _onboard(api, app_secret="short").status_code == 422
    assert _onboard(api, new_restaurant={"name": "X Y"}).status_code == 422  # both an existing and a new one


def test_refuses_without_encryption_key(api, monkeypatch):
    monkeypatch.delenv("POS_ENCRYPTION_KEY")
    res = _onboard(api)
    assert res.status_code == 503 and "POS_ENCRYPTION_KEY" in res.json()["detail"]


def test_rotate_credentials_and_status(api, env):
    integration_id = _onboard(api).json()["integration"]["id"]
    res = api.patch(
        f"/admin/pos/integrations/{integration_id}",
        json={"access_token": "new-token-zzzzzzzz9999", "app_key": "", "status": "paused"},
        headers={"X-Admin-Key": "admin-secret"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["integration"]["status"] == "paused"
    creds = repository.get_credentials(integration_id)
    assert creds.access_token == "new-token-zzzzzzzz9999"
    assert creds.app_key == SECRETS["app_key"]  # blank = keep
    kinds = {e["kind"] for e in env.tables["pos_integration_events"]}
    assert {"created", "credentials_rotated", "status_changed"} <= kinds
    assert all("new-token" not in json.dumps(e) for e in env.tables["pos_integration_events"])


def test_webhook_token_rotation_invalidates_old(api, env):
    first = _onboard(api).json()
    old = first["webhook"]["client_authorization"].removeprefix("Bearer ")
    res = api.post(
        f"/admin/pos/integrations/{first['integration']['id']}/webhook-token", headers={"X-Admin-Key": "admin-secret"}
    )
    new = res.json()["webhook"]["client_authorization"].removeprefix("Bearer ")
    stored = env.tables["pos_integrations"][0]["webhook_token_hash"]
    assert crypto.token_matches(new, stored) and not crypto.token_matches(old, stored)


def test_find_by_restid(env, api):
    _onboard(api)
    found = repository.find_by_pos_restaurant("petpooja", "f871uxkp")
    assert found and found["restaurant_id"] == "r1" and "app_secret_enc" not in found
    assert repository.find_by_pos_restaurant("petpooja", "unknown") is None

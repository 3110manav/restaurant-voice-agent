"""Encryption for POS credentials at rest, and hashing for tokens we only ever compare.

Encrypt vs hash: Petpooja's app_key / app_secret / access_token have to be sent back to Petpooja on every call, so
they are ENCRYPTED (reversible, only with our key). A webhook token Petpooja sends to us only has to be compared, so
only its SHA-256 is stored and the token itself is shown once.

Scheme: AES-256-GCM (authenticated), a fresh 12-byte nonce per value, and associated data binding each ciphertext
to its row and column ("<integration id>:<field>"), so a value copied into another row or column fails to decrypt
instead of silently working.

Keys: POS_ENCRYPTION_KEY is 32 random bytes, base64 (generate with `python -m app.pos.crypto`). To rotate, move
the old key to POS_ENCRYPTION_KEY_PREVIOUS, set a new POS_ENCRYPTION_KEY, and re-save the credentials
(needs_reencrypt() tells which rows still use the old key). Each ciphertext names the key it was made with by a short fingerprint, so both
keys decrypt during the switch:   v1.<key id>.<base64(nonce || ciphertext)>
"""
import base64
import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PREFIX = "v1"


class CryptoNotConfigured(RuntimeError):
    pass


class DecryptError(RuntimeError):
    pass


def _load_key(env_name: str) -> bytes | None:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return None
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise CryptoNotConfigured(f"{env_name} isn't valid base64") from exc
    if len(key) != 32:
        raise CryptoNotConfigured(f"{env_name} must be 32 bytes (base64 of 32 random bytes)")
    return key


def _key_id(key: bytes) -> str:
    return hashlib.sha256(b"sarthi-pos-key:" + key).hexdigest()[:8]


def _keys() -> tuple[tuple[str, bytes], dict[str, bytes]]:
    """(current key id and key, every usable key by id). Read per call so a key change needs no code reload."""
    current = _load_key("POS_ENCRYPTION_KEY")
    if current is None:
        raise CryptoNotConfigured("Set POS_ENCRYPTION_KEY on the API to store POS credentials")
    by_id = {_key_id(current): current}
    previous = _load_key("POS_ENCRYPTION_KEY_PREVIOUS")
    if previous is not None:
        by_id.setdefault(_key_id(previous), previous)
    return (_key_id(current), current), by_id


def is_configured() -> bool:
    try:
        _keys()
        return True
    except CryptoNotConfigured:
        return False


def encrypt(plaintext: str, context: str) -> str:
    (kid, key), _ = _keys()
    nonce = os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), context.encode("utf-8"))
    return f"{_PREFIX}.{kid}.{base64.b64encode(nonce + sealed).decode('ascii')}"


def decrypt(token: str, context: str) -> str:
    _, by_id = _keys()
    try:
        prefix, kid, payload = token.split(".", 2)
    except ValueError as exc:
        raise DecryptError("Not an encrypted value") from exc
    if prefix != _PREFIX:
        raise DecryptError(f"Unknown format {prefix!r}")
    key = by_id.get(kid)
    if key is None:
        raise DecryptError("Encrypted with a key this server doesn't have (POS_ENCRYPTION_KEY changed?)")
    blob = base64.b64decode(payload)
    try:
        return AESGCM(key).decrypt(blob[:12], blob[12:], context.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        raise DecryptError("Value doesn't match this key or this row") from exc


def needs_reencrypt(token: str) -> bool:
    """True when a value was made with an older key (for rotation)."""
    (kid, _), _ = _keys()
    return token.split(".", 2)[1] != kid


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), stored_hash)


def new_webhook_token() -> str:
    return "ppwh_" + secrets.token_urlsafe(32)


def hint(value: str) -> str:
    """Last 4 characters, for telling saved credentials apart. Empty for values too short to reveal any of."""
    value = value.strip()
    return value[-4:] if len(value) >= 12 else ""


if __name__ == "__main__":
    print(base64.b64encode(os.urandom(32)).decode("ascii"))

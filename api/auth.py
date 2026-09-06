"""JWT authentication helpers for customer-facing API endpoints."""

import os
import sqlite3
import base64
import binascii
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "ecommerce.db")
JWT_SECRET = os.getenv("JWT_SECRET", "local-development-secret-change-me")
JWT_ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "60"))

bearer_scheme = HTTPBearer(auto_error=False)


def customer_exists(customer_id: str, email: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT 1 FROM customers WHERE customer_id = ? AND lower(email) = lower(?)",
            (customer_id, email),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def create_access_token(customer_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": customer_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=TOKEN_TTL_MINUTES)).timestamp()),
    }
    header = {"typ": "JWT", "alg": JWT_ALGORITHM}
    encoded_header = _encode_part(header)
    encoded_payload = _encode_part(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_encode_bytes(signature)}"


def get_authenticated_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    try:
        encoded_header, encoded_payload, encoded_signature = credentials.credentials.split(".")
        header = json.loads(_decode_bytes(encoded_header))
        if header.get("alg") != JWT_ALGORITHM:
            raise ValueError("Unsupported JWT algorithm")
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode_bytes(encoded_signature, binary=True)):
            raise ValueError("Invalid JWT signature")
        claims = json.loads(_decode_bytes(encoded_payload))
        if int(claims.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("Expired JWT")
        customer_id = claims.get("sub")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if not isinstance(customer_id, str) or not customer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has no customer identity")
    return customer_id


def _encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _encode_part(value: dict) -> str:
    return _encode_bytes(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _decode_bytes(value: str, binary: bool = False):
    padded = value + "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode(padded)
    return decoded if binary else decoded.decode("utf-8")
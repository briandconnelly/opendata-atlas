"""Stateless, HMAC-signed cursors (docs/design.md: Continuation).

The key lives in process memory only. Each cursor names the portal that issued it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from opendata_atlas.constants import CURSOR_TTL_SECONDS
from opendata_atlas.core.errors import AtlasError, ErrorCode, ErrorDetails, Repair

_KEY = secrets.token_bytes(32)
#: Version 2 binds the portal; version 1 cursors predate portals and are refused.
_VERSION = 2


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def dump(data: Any) -> bytes:
    """Compact UTF-8 JSON; non-ASCII stays raw so it costs its UTF-8 size, not `\\uXXXX`."""
    return json.dumps(data, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()


def encode(kind: str, state: dict[str, Any], *, portal_id: str) -> str:
    payload = dump({"v": _VERSION, "k": kind, "p": portal_id, "t": int(time.time()), "s": state})
    signature = hmac.new(_KEY, payload, hashlib.sha256).digest()[:16]
    return f"{_b64(payload)}.{_b64(signature)}"


def decode(
    cursor: str, kind: str, *, portal_id: str, restart: Repair, field: str = "cursor"
) -> dict[str, Any]:
    """Verify and unpack.

    A bad signature is `cursor_expired`: a server restart rotates the in-memory key.
    `field` is the published parameter that carried the cursor, named in every failure.
    """
    try:
        payload_part, signature_part = cursor.split(".", 1)
        payload = _unb64(payload_part)
        signature = _unb64(signature_part)
        data = json.loads(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise _error(
            ErrorCode.INVALID_CURSOR,
            "The cursor is malformed.",
            "It could not be decoded.",
            restart,
            field,
        ) from exc
    expected = hmac.new(_KEY, payload, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(signature, expected):
        raise _error(
            ErrorCode.CURSOR_EXPIRED,
            "The cursor has expired or the server restarted.",
            "Its signature does not match: cursors do not survive a server restart.",
            restart,
            field,
        )
    if data.get("v") != _VERSION:
        raise _error(
            ErrorCode.INVALID_CURSOR,
            "The cursor uses an unsupported format.",
            "It was issued by a different server version.",
            restart,
            field,
        )
    if data.get("k") != kind:
        raise _error(
            ErrorCode.INVALID_CURSOR,
            "The cursor belongs to a different tool.",
            "Use a cursor only with the tool that returned it.",
            restart,
            field,
        )
    if data.get("p") != portal_id:
        # The cursor's own portal is not echoed: cursor contents never leave in an error.
        raise _error(
            ErrorCode.INVALID_CURSOR,
            "The cursor belongs to a different portal.",
            "Use a cursor only with the portal that returned it.",
            restart,
            field,
        )
    if time.time() - int(data.get("t", 0)) > CURSOR_TTL_SECONDS:
        raise _error(
            ErrorCode.CURSOR_EXPIRED,
            "The cursor has expired.",
            "Cursors last 1 hour.",
            restart,
            field,
        )
    return data["s"]


def _error(code: ErrorCode, message: str, reason: str, restart: Repair, field: str) -> AtlasError:
    return AtlasError(
        code, message, details=ErrorDetails(field=field, reason=reason), repair=restart
    )

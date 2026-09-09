from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_REDACTED = "***REDACTED***"
_DENIED_KEYS = frozenset(
    {
        "args",
        "arguments",
        "argv",
        "frame",
        "frames",
        "local",
        "locals",
        "return_value",
        "returnValue",
    }
)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b((?:api[_-]?key|password|secret|token)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
)


class DiagnosticPayloadRejectedError(ValueError):
    """Raised when a diagnostic payload requests explicitly forbidden data."""


def _sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + _REDACTED, redacted)
    return redacted


def sanitize_diagnostic_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe privacy boundary for diagnostic payloads.

    Application locals, frames and arguments are forbidden rather than silently
    serialized. Secret-looking fields and common credential forms inside strings
    are redacted recursively. Callers retain structured numeric/boolean metadata
    needed for local diagnostics without gaining an arbitrary object serializer.
    """

    def sanitize(value: Any, *, key: str = "", depth: int = 0) -> Any:
        if depth > 12:
            return "<depth-limit>"
        if key in _DENIED_KEYS:
            raise DiagnosticPayloadRejectedError(f"diagnostic field {key!r} is forbidden")
        if _sensitive_key(key):
            return _REDACTED
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return _redact_text(value)
        if isinstance(value, Mapping):
            return {
                str(child_key): sanitize(child_value, key=str(child_key), depth=depth + 1)
                for child_key, child_value in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [sanitize(item, depth=depth + 1) for item in value]
        return f"<{type(value).__name__}>"

    return sanitize(payload)
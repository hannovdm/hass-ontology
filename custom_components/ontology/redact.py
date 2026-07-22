"""Shared credential/secret redaction helpers.

Used to strip password/secret fields from log records, diagnostics payloads,
and error/exception text before they are ever written, logged, or exported
(Constitution Principle II, FR-004, SC-007).
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "**REDACTED**"

# Config-entry / connection-info keys that must never appear in the clear.
SECRET_KEYS = frozenset({"password", "token", "access_token", "api_key", "secret"})

# Matches `password=...`, `password: "..."`, `"password": "..."` style fragments
# that might otherwise leak into free-form error/exception text (e.g. driver
# error messages that echo the connection URI or auth info).
_SECRET_PATTERN = re.compile(
    r"(?i)(password|token|api[_-]?key|secret)\s*[=:]\s*(\"[^\"]*\"|'[^']*'|\S+)"
)


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of a mapping with secret keys redacted."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in SECRET_KEYS:
            result[key] = REDACTED
        elif isinstance(value, dict):
            result[key] = redact_mapping(value)
        else:
            result[key] = value
    return result


def redact_text(text: str) -> str:
    """Strip inline secret-looking fragments out of free-form text.

    Used for log messages and exception/error text where a secret value
    could otherwise be echoed verbatim (e.g. by a driver's own error string).
    """
    if not text:
        return text
    return _SECRET_PATTERN.sub(lambda m: f"{m.group(1)}={REDACTED}", text)


def redact_exception(exc: BaseException) -> str:
    """Return a redacted string representation of an exception."""
    return redact_text(str(exc))

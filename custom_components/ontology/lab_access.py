"""Home Assistant Lab capability consumer (US4, T052).

Fetches the sanitized Lab capability from the add-on's authenticated internal
GraphQL endpoint.  Never reads /data, the Lab password, or internal hostnames.
Returns ``not_addon_backend`` for direct-Memgraph backends.
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

LAB_CAPABILITY_REASONS = (
    "READY",
    "NOT_ADDON_BACKEND",
    "TRANSPORT_UNAVAILABLE",
    "LAB_UNHEALTHY",
    "ENTERPRISE_REQUIRED",
    "READONLY_USER_MISSING",
    "WRITE_PROBE_SUCCEEDED",
)

_LAB_CAPABILITY_QUERY = """
query {
  labCapability {
    available
    reason
    ingressPath
    checkedAt
  }
}
"""

_REQUEST_TIMEOUT_SECONDS = 10.0

_NOT_ADDON_BACKEND = {
    "available": False,
    "reason": "NOT_ADDON_BACKEND",
    "ingress_path": None,
    "checked_at": None,
}


class LabAccess:
    """Fetch and cache the Lab capability state from the add-on GraphQL endpoint.

    Instantiated by __init__.py when an authenticated GraphQL URL/token is
    configured; otherwise the direct-Memgraph fallback returns
    ``not_addon_backend``.
    """

    def __init__(
        self,
        graphql_url: str | None,
        graphql_token: str | None,
        session: ClientSession | None = None,
    ) -> None:
        self._url = graphql_url
        self._token = graphql_token
        self._session = session
        self._owns_session = session is None and bool(graphql_url)
        self._last_capability: dict[str, Any] = dict(_NOT_ADDON_BACKEND)
        self._probe_duration_ms: float | None = None

    async def _ensure_session(self) -> ClientSession | None:
        if not self._url:
            return None
        if self._session is None and self._owns_session:
            self._session = ClientSession()
        return self._session

    async def get_capability(self) -> dict[str, Any]:
        """Return the current Lab capability, never revealing credentials."""
        if not self._url or not self._token:
            return dict(_NOT_ADDON_BACKEND)

        session = await self._ensure_session()
        if session is None:
            return dict(_NOT_ADDON_BACKEND)

        import time
        start = time.monotonic()
        try:
            response = await session.post(
                self._url,
                json={"query": _LAB_CAPABILITY_QUERY},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS),
            )
            data = await response.json()
            lab = data.get("data", {}).get("labCapability", {})
            self._probe_duration_ms = round((time.monotonic() - start) * 1000)
            capability = {
                "available": bool(lab.get("available")),
                "reason": lab.get("reason", "TRANSPORT_UNAVAILABLE"),
                "ingress_path": lab.get("ingressPath"),
                "checked_at": lab.get("checkedAt"),
            }
            self._last_capability = capability
            return capability
        except (ClientError, Exception):  # noqa: BLE001
            self._probe_duration_ms = round((time.monotonic() - start) * 1000)
            _LOGGER.debug("Lab capability check failed (transport error)")
            result = {
                "available": False,
                "reason": "TRANSPORT_UNAVAILABLE",
                "ingress_path": None,
                "checked_at": None,
            }
            self._last_capability = result
            return result

    def diagnostics(self) -> dict[str, Any]:
        """Return sanitized diagnostics — never credentials, tokens, or URIs."""
        return {
            "available": self._last_capability.get("available", False),
            "reason": self._last_capability.get("reason"),
            "probe_duration_ms": self._probe_duration_ms,
            "url_configured": bool(self._url),
        }

    async def close(self) -> None:
        """Close the owned aiohttp session if we created it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

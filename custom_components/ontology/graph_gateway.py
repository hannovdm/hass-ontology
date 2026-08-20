"""Config-entry-scoped, non-fatal graph presentation gateway."""

from __future__ import annotations

import logging
from typing import Any

from .const import CONF_GRAPHQL_TOKEN, CONF_GRAPHQL_URL
from .graph_backends import AddonGraphQLBackend, DirectMemgraphBackend, GraphBackend

_LOGGER = logging.getLogger(__name__)


def create_graph_backend(config: dict[str, Any], memgraph_client: Any, *, session: Any | None = None) -> GraphBackend:
    """Select exactly one backend for the config-entry lifetime."""
    url = str(config.get(CONF_GRAPHQL_URL) or "").strip()
    token = str(config.get(CONF_GRAPHQL_TOKEN) or "").strip()
    if url and token:
        return AddonGraphQLBackend(url, token, session=session)
    return DirectMemgraphBackend(memgraph_client)


class GraphGateway:
    """Normalize selected-backend failures into presentation unavailability."""

    def __init__(self, backend: GraphBackend) -> None:
        self.backend = backend
        self._available = True
        self._last_error_category: str | None = None
        self._request_count = 0

    async def _call(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        self._request_count += 1
        try:
            result = await getattr(self.backend, operation)(*args, **kwargs)
        except Exception:  # noqa: BLE001 - graph UI failure is intentionally non-fatal
            self._available = False
            self._last_error_category = "gateway_unavailable"
            _LOGGER.warning("Graph gateway operation %s is unavailable", operation)
            return None
        self._available = True
        self._last_error_category = None
        return result

    async def initial_graph(self, limit: int = 500, after: str | None = None) -> dict[str, Any]:
        result = await self._call("initial_graph", limit, after)
        return result or {"available": False, "error": "gateway_unavailable", "nodes": [], "relationships": [], "truncated": False, "nextCursor": None, "revision": 0}

    async def expand_node(self, node_id: str, node_limit: int = 100, edge_limit: int = 250, after: str | None = None) -> dict[str, Any]:
        result = await self._call("expand_node", node_id, node_limit, edge_limit, after)
        return result or {"available": False, "error": "gateway_unavailable", "nodes": [], "relationships": [], "truncated": False, "nextCursor": None, "revision": 0}

    async def search_graph(self, term: str, limit: int = 50) -> dict[str, Any]:
        result = await self._call("search_graph", term, limit)
        return result or {"available": False, "error": "gateway_unavailable", "matches": [], "truncated": False, "revision": 0}

    async def graph_element(self, element_id: str) -> dict[str, Any] | None:
        return await self._call("graph_element", element_id)

    async def graph_health(self) -> dict[str, Any]:
        result = await self._call("graph_health")
        return result or {"status": "UNAVAILABLE", "revision": 0, "latencyMs": 0}

    def diagnostics(self) -> dict[str, Any]:
        return {"available": self._available, "error_category": self._last_error_category, "request_count": self._request_count, "backend": type(self.backend).__name__}

    async def close(self) -> None:
        await self.backend.close()


async def async_attach_graph_gateway(entry: Any, coordinator: Any, *, session: Any | None = None) -> GraphGateway:
    """Attach a selected gateway without probing or blocking ontology setup."""
    config = {**dict(entry.data), **dict(entry.options)}
    gateway = GraphGateway(create_graph_backend(config, coordinator.memgraph_client, session=session))
    coordinator.graph_gateway = gateway
    return gateway

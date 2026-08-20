"""Equivalent fixed read-only backends for graph presentation data."""

from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    GRAPH_EXPAND_EDGE_LIMIT,
    GRAPH_EXPAND_EDGE_MAX,
    GRAPH_EXPAND_NODE_LIMIT,
    GRAPH_EXPAND_NODE_MAX,
    GRAPH_INITIAL_EDGE_LIMIT,
    GRAPH_INITIAL_NODE_LIMIT,
    GRAPH_PROPERTY_LIMIT,
    GRAPH_PROPERTY_VALUE_MAX_LENGTH,
    GRAPH_REQUEST_TIMEOUT_SECONDS,
    GRAPH_SEARCH_LIMIT,
    GRAPH_SEARCH_MAX,
)
from .redact import SECRET_KEYS, redact_value

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_SAFE_PROPERTY_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SENSITIVE_PROPERTY = re.compile(
    r"password|passphrase|secret|token|credential|connection|uri|url|host",
    re.IGNORECASE,
)
_NODE_TYPES = {
    "Area": "AREA",
    "Device": "DEVICE",
    "Entity": "ENTITY",
    "Automation": "AUTOMATION",
    "Scene": "SCENE",
    "Script": "SCRIPT",
    "Dashboard": "DASHBOARD",
    "DashboardCard": "DASHBOARD_CARD",
    "SemanticType": "SEMANTIC_TYPE",
    "ValidationFinding": "VALIDATION_FINDING",
}

_INITIAL_GRAPH = """
MATCH (n)
WHERE n:Area OR n:Device
OPTIONAL MATCH (assigned_area:Area)-[:HAS_DEVICE]->(n)
WITH n, count(assigned_area) > 0 AS assigned
ORDER BY CASE WHEN n:Area THEN 0 WHEN assigned THEN 1 ELSE 2 END,
         coalesce(n.name, n.ha_id), n.ha_id
WITH collect(n)[0..$node_limit] AS nodes
OPTIONAL MATCH (a:Area)-[r:HAS_DEVICE]->(d:Device)
WHERE a IN nodes AND d IN nodes
RETURN nodes, collect(CASE WHEN r IS NULL THEN null ELSE {
    type: type(r),
    source: labels(startNode(r))[0] + ':' + startNode(r).ha_id,
    target: labels(endNode(r))[0] + ':' + endNode(r).ha_id,
    id: coalesce(r.ha_id, r.id, '0'),
    source_class: r.source,
    properties: properties(r)
} END)[0..$edge_limit] AS relationships
"""
_EXPAND_NODE = """
MATCH (center)
WHERE any(label IN labels(center) WHERE label + ':' + center.ha_id = $id)
OPTIONAL MATCH (center)-[r]-(neighbor)
WITH center, r, neighbor ORDER BY coalesce(neighbor.name, neighbor.ha_id), type(r)
RETURN [center] + collect(DISTINCT neighbor)[0..$node_limit] AS nodes,
             collect(DISTINCT CASE WHEN r IS NULL OR neighbor IS NULL THEN null ELSE {
                 type: type(r),
                 source: labels(startNode(r))[0] + ':' + startNode(r).ha_id,
                 target: labels(endNode(r))[0] + ':' + endNode(r).ha_id,
                 id: coalesce(r.ha_id, r.id, '0'),
                 source_class: r.source,
                 properties: properties(r)
             } END)[0..$edge_limit] AS relationships
"""
_SEARCH_GRAPH = """
MATCH (n)
WHERE toLower(coalesce(n.name, '')) CONTAINS toLower($term)
   OR toLower(coalesce(n.ha_id, '')) CONTAINS toLower($term)
RETURN n ORDER BY coalesce(n.name, n.ha_id), n.ha_id LIMIT $limit
"""
_GRAPH_ELEMENT = """
MATCH (element)
WHERE any(label IN labels(element) WHERE label + ':' + element.ha_id = $id)
OPTIONAL MATCH (element)-[r]-(neighbor)
RETURN element, collect(DISTINCT neighbor)[0..26] AS nodes,
             collect(DISTINCT CASE WHEN r IS NULL OR neighbor IS NULL THEN null ELSE {
                 type: type(r),
                 source: labels(startNode(r))[0] + ':' + startNode(r).ha_id,
                 target: labels(endNode(r))[0] + ':' + endNode(r).ha_id,
                 id: coalesce(r.ha_id, r.id, '0'),
                 source_class: r.source,
                 properties: properties(r)
             } END)[0..51] AS relationships
"""
_GRAPH_RELATIONSHIP = """
MATCH ()-[r]->()
WITH r,
         type(r) + ':' + labels(startNode(r))[0] + ':' + startNode(r).ha_id + ':' +
         labels(endNode(r))[0] + ':' + endNode(r).ha_id + ':' +
         coalesce(r.ha_id, r.id, '0') AS stable_id
WHERE stable_id = $id
RETURN {
    type: type(r),
    source: labels(startNode(r))[0] + ':' + startNode(r).ha_id,
    target: labels(endNode(r))[0] + ':' + endNode(r).ha_id,
    id: coalesce(r.ha_id, r.id, '0'),
    source_class: r.source,
    properties: properties(r)
} AS relationship,
startNode(r) AS source_node,
endNode(r) AS target_node
LIMIT 1
"""
_GRAPH_HEALTH = "RETURN 1 AS healthy"

_GRAPHQL_DOCUMENTS = {
    "InitialGraph": """query InitialGraph($limit: Int!, $after: String) {
      initialGraph(limit: $limit, after: $after) { nodes { id haId type label icon state unavailable findingSeverity properties { name value displayValue } } relationships { id type source target directed sourceClass properties { name value displayValue } } pageInfo { truncated nextCursor } revision }
    }""",
    "ExpandNode": """query ExpandNode($id: ID!, $nodeLimit: Int!, $edgeLimit: Int!, $after: String) {
      expandNode(id: $id, nodeLimit: $nodeLimit, edgeLimit: $edgeLimit, after: $after) { nodes { id haId type label icon state unavailable findingSeverity properties { name value displayValue } } relationships { id type source target directed sourceClass properties { name value displayValue } } pageInfo { truncated nextCursor } revision }
    }""",
    "SearchGraph": """query SearchGraph($term: String!, $limit: Int!) { searchGraph(term: $term, limit: $limit) { matches { id haId type label icon } truncated revision } }""",
    "GraphElement": """query GraphElement($id: ID!) { graphElement(id: $id) { node { id haId type label icon state unavailable findingSeverity properties { name value displayValue } } relationship { id type source target directed sourceClass properties { name value displayValue } } directConnections { nodes { id haId type label icon state unavailable findingSeverity properties { name value displayValue } } relationships { id type source target directed sourceClass properties { name value displayValue } } pageInfo { truncated nextCursor } revision } } }""",
    "GraphHealth": """query GraphHealth { graphHealth { status revision latencyMs } }""",
}


class GraphBackendUnavailable(Exception):
    """Raised when the selected graph presentation backend is unavailable."""


def _clamp(value: int | None, default: int, maximum: int) -> int:
    return min(max(value if isinstance(value, int) else default, 1), maximum)


def _bounded_text(value: Any, limit: int = GRAPH_PROPERTY_VALUE_MAX_LENGTH) -> str:
    return _CONTROL_CHARACTERS.sub("", str(value if value is not None else ""))[:limit]


def _raw_properties(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        properties = value.get("properties", value)
        return properties if isinstance(properties, dict) else {}
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def _raw_labels(value: Any) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(label) for label in value.get("labels", []))
    return sorted(str(label) for label in getattr(value, "labels", []))


def _safe_properties(properties: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in sorted(properties):
        if (
            len(result) >= GRAPH_PROPERTY_LIMIT
            or not _SAFE_PROPERTY_NAME.fullmatch(name)
            or name.lower() in SECRET_KEYS
            or _SENSITIVE_PROPERTY.search(name)
        ):
            continue
        value = redact_value(properties[name])
        if not isinstance(value, (str, int, float, bool, type(None))):
            value = _bounded_text(json.dumps(value, sort_keys=True, default=str))
        elif isinstance(value, str):
            value = _bounded_text(value)
        result.append({"name": name, "value": value, "displayValue": _bounded_text(value)})
    return result


def normalize_graph_node(value: Any) -> dict[str, Any]:
    """Normalize one driver/JSON node into the safe presentation record."""
    properties = _raw_properties(value)
    labels = _raw_labels(value)
    canonical_label = next((label for label in labels if label in _NODE_TYPES), "Other")
    ha_id = _bounded_text(properties.get("ha_id") or properties.get("id"), 512)
    if not ha_id:
        raise ValueError("Graph node is missing a stable identifier")
    label = _bounded_text(
        properties.get("name") or properties.get("friendly_name") or ha_id, 256
    )
    state = properties.get("state")
    return {
        "id": f"{canonical_label}:{ha_id}",
        "haId": ha_id,
        "type": _NODE_TYPES.get(canonical_label, "OTHER"),
        "label": label,
        "icon": properties.get("icon")
        if re.fullmatch(r"mdi:[a-z0-9-]+", str(properties.get("icon", "")))
        else None,
        "state": _bounded_text(state, 256) if state is not None else None,
        "unavailable": str(state).lower() in {"unknown", "unavailable"},
        "findingSeverity": str(properties["severity"]).upper()
        if properties.get("severity")
        else None,
        "properties": _safe_properties(properties),
    }


def _endpoint_id(value: Any, side: str, properties: dict[str, Any]) -> str:
    if isinstance(value, dict):
        endpoint = value.get("source" if side == "start" else "target")
        if endpoint:
            return _bounded_text(endpoint, 512)
    node = getattr(value, f"{side}_node", None)
    if node is not None:
        return normalize_graph_node(node)["id"]
    return _bounded_text(properties.get("source" if side == "start" else "target"), 512)


def normalize_graph_relationship(value: Any) -> dict[str, Any]:
    properties = _raw_properties(value)
    metadata = value if isinstance(value, dict) else {}
    rel_type = _bounded_text(getattr(value, "type", None) or metadata.get("type") or properties.get("type") or "RELATED_TO", 128)
    source = _endpoint_id(value, "start", properties)
    target = _endpoint_id(value, "end", properties)
    discriminator = _bounded_text(metadata.get("id") or properties.get("ha_id") or properties.get("id") or "0", 128)
    return {
        "id": f"{rel_type}:{source}:{target}:{discriminator}",
        "type": rel_type,
        "source": source,
        "target": target,
        "directed": True,
        "sourceClass": str(metadata.get("source_class") or metadata.get("sourceClass") or properties.get("source_class") or properties.get("sourceClass")).upper()
        if metadata.get("source_class") or metadata.get("sourceClass") or properties.get("source_class") or properties.get("sourceClass")
        else None,
        "properties": _safe_properties(properties),
    }


def _slice(rows: list[dict[str, Any]], node_limit: int, edge_limit: int) -> dict[str, Any]:
    row = rows[0] if rows else {}
    raw_nodes = list(row.get("nodes") or [])
    raw_relationships = list(row.get("relationships") or [])
    nodes = _unique_nodes(
        [normalize_graph_node(node) for node in raw_nodes[:node_limit] if node]
    )
    return {
        "nodes": nodes,
        "relationships": _renderable_relationships(
            nodes,
            [
                normalize_graph_relationship(rel)
                for rel in raw_relationships[:edge_limit]
                if rel
            ],
        ),
        "truncated": len(raw_nodes) > node_limit or len(raw_relationships) > edge_limit,
        "nextCursor": None,
        "revision": 0,
    }


def _unique_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first node for each Cytoscape element identifier."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for node in nodes:
        if node["id"] not in seen:
            seen.add(node["id"])
            result.append(node)
    return result


def _renderable_relationships(
    nodes: list[dict[str, Any]], relationships: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Remove elements that Cytoscape cannot add to a snapshot."""
    node_ids = {node["id"] for node in nodes}
    seen = set(node_ids)
    result: list[dict[str, Any]] = []
    for relationship in relationships:
        if (
            relationship["source"] not in node_ids
            or relationship["target"] not in node_ids
            or relationship["id"] in seen
        ):
            continue
        seen.add(relationship["id"])
        result.append(relationship)
    return result


class GraphBackend(ABC):
    """Named read-only graph presentation operations."""

    @abstractmethod
    async def initial_graph(self, limit: int = GRAPH_INITIAL_NODE_LIMIT, after: str | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def expand_node(self, node_id: str, node_limit: int = GRAPH_EXPAND_NODE_LIMIT, edge_limit: int = GRAPH_EXPAND_EDGE_LIMIT, after: str | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def search_graph(self, term: str, limit: int = GRAPH_SEARCH_LIMIT) -> dict[str, Any]: ...

    @abstractmethod
    async def graph_element(self, element_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def graph_health(self) -> dict[str, Any]: ...

    @abstractmethod
    async def close(self) -> None: ...


class AddonGraphQLBackend(GraphBackend):
    """Authenticated client for the add-on's fixed GraphQL operations."""

    def __init__(self, url: str, token: str, *, session: ClientSession | Any | None = None) -> None:
        self._url = url
        self._token = token
        self._owns_session = session is None
        self._session = session or ClientSession(timeout=ClientTimeout(total=GRAPH_REQUEST_TIMEOUT_SECONDS))

    def __repr__(self) -> str:
        return "AddonGraphQLBackend(configured=True)"

    async def _operation(self, operation: str, variables: dict[str, Any], field: str) -> Any:
        payload = {"operationName": operation, "query": _GRAPHQL_DOCUMENTS[operation], "variables": variables}
        try:
            async with asyncio.timeout(GRAPH_REQUEST_TIMEOUT_SECONDS):
                response = await self._session.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=payload,
                )
                if response.status in {401, 403}:
                    raise GraphBackendUnavailable("GraphQL authentication failed")
                if response.status != 200:
                    raise GraphBackendUnavailable("GraphQL transport unavailable")
                body = await response.json()
        except GraphBackendUnavailable:
            raise
        except (TimeoutError, ClientError, OSError) as err:
            raise GraphBackendUnavailable("GraphQL transport unavailable") from err
        if body.get("errors"):
            raise GraphBackendUnavailable("GraphQL operation failed")
        return body.get("data", {}).get(field)

    async def initial_graph(self, limit: int = GRAPH_INITIAL_NODE_LIMIT, after: str | None = None) -> dict[str, Any]:
        bounded = _clamp(limit, GRAPH_INITIAL_NODE_LIMIT, GRAPH_INITIAL_NODE_LIMIT)
        result = await self._operation("InitialGraph", {"limit": bounded, "after": after}, "initialGraph")
        return _normalize_graphql_slice(result)

    async def expand_node(self, node_id: str, node_limit: int = GRAPH_EXPAND_NODE_LIMIT, edge_limit: int = GRAPH_EXPAND_EDGE_LIMIT, after: str | None = None) -> dict[str, Any]:
        result = await self._operation("ExpandNode", {"id": _bounded_text(node_id, 512), "nodeLimit": _clamp(node_limit, GRAPH_EXPAND_NODE_LIMIT, GRAPH_EXPAND_NODE_MAX), "edgeLimit": _clamp(edge_limit, GRAPH_EXPAND_EDGE_LIMIT, GRAPH_EXPAND_EDGE_MAX), "after": after}, "expandNode")
        return _normalize_graphql_slice(result)

    async def search_graph(self, term: str, limit: int = GRAPH_SEARCH_LIMIT) -> dict[str, Any]:
        result = await self._operation("SearchGraph", {"term": _bounded_text(term, 256).strip(), "limit": _clamp(limit, GRAPH_SEARCH_LIMIT, GRAPH_SEARCH_MAX)}, "searchGraph")
        return result

    async def graph_element(self, element_id: str) -> dict[str, Any] | None:
        return await self._operation("GraphElement", {"id": _bounded_text(element_id, 512)}, "graphElement")

    async def graph_health(self) -> dict[str, Any]:
        return await self._operation("GraphHealth", {}, "graphHealth")

    async def close(self) -> None:
        if self._owns_session:
            await self._session.close()


def _normalize_graphql_slice(value: dict[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    page_info = value.get("pageInfo") or {}
    nodes = _unique_nodes(value.get("nodes") or [])
    return {
        "nodes": nodes,
        "relationships": _renderable_relationships(
            nodes, value.get("relationships") or []
        ),
        "truncated": bool(page_info.get("truncated")),
        "nextCursor": page_info.get("nextCursor"),
        "revision": int(value.get("revision") or 0),
    }


class DirectMemgraphBackend(GraphBackend):
    """Fixed parameterized Cypher over the coordinator's shared client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def initial_graph(self, limit: int = GRAPH_INITIAL_NODE_LIMIT, after: str | None = None) -> dict[str, Any]:
        bounded = _clamp(limit, GRAPH_INITIAL_NODE_LIMIT, GRAPH_INITIAL_NODE_LIMIT)
        rows = await self._client.run_query(_INITIAL_GRAPH, {"node_limit": bounded + 1, "edge_limit": GRAPH_INITIAL_EDGE_LIMIT + 1})
        return _slice(rows, bounded, GRAPH_INITIAL_EDGE_LIMIT)

    async def expand_node(self, node_id: str, node_limit: int = GRAPH_EXPAND_NODE_LIMIT, edge_limit: int = GRAPH_EXPAND_EDGE_LIMIT, after: str | None = None) -> dict[str, Any]:
        bounded_nodes = _clamp(node_limit, GRAPH_EXPAND_NODE_LIMIT, GRAPH_EXPAND_NODE_MAX)
        bounded_edges = _clamp(edge_limit, GRAPH_EXPAND_EDGE_LIMIT, GRAPH_EXPAND_EDGE_MAX)
        rows = await self._client.run_query(_EXPAND_NODE, {"id": _bounded_text(node_id, 512), "node_limit": bounded_nodes + 1, "edge_limit": bounded_edges + 1})
        return _slice(rows, bounded_nodes, bounded_edges)

    async def search_graph(self, term: str, limit: int = GRAPH_SEARCH_LIMIT) -> dict[str, Any]:
        bounded = _clamp(limit, GRAPH_SEARCH_LIMIT, GRAPH_SEARCH_MAX)
        rows = await self._client.run_query(_SEARCH_GRAPH, {"term": _bounded_text(term, 256).strip(), "limit": bounded + 1})
        nodes = [normalize_graph_node(row.get("n") or row.get("node") or row) for row in rows]
        return {"matches": [{key: node[key] for key in ("id", "haId", "type", "label", "icon")} for node in nodes[:bounded]], "truncated": len(nodes) > bounded, "revision": 0}

    async def graph_element(self, element_id: str) -> dict[str, Any] | None:
        rows = await self._client.run_query(_GRAPH_ELEMENT, {"id": _bounded_text(element_id, 512)})
        if rows and rows[0].get("element"):
            row = rows[0]
            return {"node": normalize_graph_node(row["element"]), "relationship": None, "directConnections": _slice(rows, 25, 50)}
        relationship_rows = await self._client.run_query(
            _GRAPH_RELATIONSHIP, {"id": _bounded_text(element_id, 512)}
        )
        if not relationship_rows:
            return None
        row = relationship_rows[0]
        return {
            "node": None,
            "relationship": normalize_graph_relationship(row["relationship"]),
            "directConnections": {
                "nodes": [
                    normalize_graph_node(row["source_node"]),
                    normalize_graph_node(row["target_node"]),
                ],
                "relationships": [
                    normalize_graph_relationship(row["relationship"])
                ],
                "truncated": False,
                "nextCursor": None,
                "revision": 0,
            },
        }

    async def graph_health(self) -> dict[str, Any]:
        started = asyncio.get_running_loop().time()
        await self._client.run_query(_GRAPH_HEALTH, {})
        return {"status": "HEALTHY", "revision": 0, "latencyMs": round((asyncio.get_running_loop().time() - started) * 1000)}

    async def close(self) -> None:
        return None

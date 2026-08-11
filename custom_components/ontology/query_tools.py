"""Shared, transport-agnostic predefined query tools (User Story 1).

Plain async functions operating on a `MemgraphClient`, independent of any
calling transport (research.md §7). Home Assistant services, Assist intent
handlers (`intent_handlers.py`), and the MCP endpoint (`mcp_server.py`) all
call these same functions and share one JSON-compatible `ToolResult` shape
(data-model.md §2): `{"target", "result_type", "result", "warnings"}`.
"""

from __future__ import annotations

from typing import Any

from .const import (
    DEFAULT_QUERY_LIMIT,
    LABEL_AREA,
    LABEL_AUTOMATION,
    LABEL_DEVICE,
    LABEL_DOMAIN,
    LABEL_ENTITY,
    LABEL_INTEGRATION,
    MAX_QUERY_LIMIT,
    REL_CLASSIFIED_AS,
    REL_CONTROLS,
    REL_HAS_AREA,
    REL_HAS_DEVICE,
    REL_HAS_ENTITY,
    REL_IN_DOMAIN,
    REL_PROVIDED_BY,
    REL_REFERENCES,
    RESULT_TYPE_AREA_CONTEXT,
    RESULT_TYPE_AUTOMATION_DEPENDENCIES,
    RESULT_TYPE_DEVICE_CONTEXT,
    RESULT_TYPE_ENTITY_CONTEXT,
    RESULT_TYPE_NOT_FOUND,
    RESULT_TYPE_SEARCH,
)
from .memgraph_client import MemgraphClient
from .redact import SECRET_KEYS

_NO_DEPENDENCIES_WARNING = "no known dependencies found"


def node_properties(node: Any) -> dict[str, Any] | None:
    """Unwrap a raw graph value returned for a whole-node `RETURN` into its
    plain property dict.

    `MemgraphClient.run_query`/`run_query_limited` serialize a returned
    `neo4j.graph.Node` into `{"element_id", "labels", "properties"}`
    (memgraph_client.py `_serialize_value`, added to make `ontology.query`
    JSON-safe) - callers that `RETURN` a whole node (rather than a scalar
    property) must unwrap `properties` rather than treat the row value
    itself as the property dict.
    """
    if node is None:
        return None
    if isinstance(node, dict) and "properties" in node and "labels" in node:
        return dict(node["properties"])
    return dict(node)


def _redact(value: Any) -> Any:
    """Recursively strip any key matching `redact.py`'s `SECRET_KEYS` (FR-006).

    Applied to every `ToolResult.result` payload before it is returned to any
    caller (service/Assist/MCP), regardless of transport.
    """
    if isinstance(value, dict):
        return {
            key: ("**REDACTED**" if key.lower() in SECRET_KEYS else _redact(val))
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def build_tool_result(
    target: str,
    result_type: str,
    result: dict[str, Any] | list[Any] | None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build the shared `ToolResult` envelope (data-model.md §2)."""
    return {
        "target": target,
        "result_type": result_type,
        "result": _redact(result) if result is not None else None,
        "warnings": list(warnings) if warnings else [],
    }


def not_found_result(target: str, _result_type: str) -> dict[str, Any]:
    """Build the shared "not found" `ToolResult` (FR-007, FR-012, FR-017, SC-006).

    `result_type` is always `"not_found"`, never the requested tool's own
    result-type discriminator - the second argument is accepted for call-site
    readability only.
    """
    return build_tool_result(target, RESULT_TYPE_NOT_FOUND, None)


def _effective_limit(limit: int | None) -> int:
    return min(limit or DEFAULT_QUERY_LIMIT, MAX_QUERY_LIMIT)


def count_results(result: dict[str, Any] | list[Any] | None) -> int:
    """Best-effort item count for a `ToolResult.result` payload (used for audit trails)."""
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        for value in result.values():
            if isinstance(value, list):
                return len(value)
        return 1
    return 1


async def search(
    client: MemgraphClient, term: str, limit: int | None = None
) -> dict[str, Any]:
    """Bounded name/identifier match across Area/Device/Entity (FR-001)."""
    effective_limit = _effective_limit(limit)
    query = (
        f"MATCH (n) WHERE (n:{LABEL_AREA} OR n:{LABEL_DEVICE} OR n:{LABEL_ENTITY}) "
        "AND (toLower(coalesce(n.name, '')) CONTAINS toLower($term) "
        "OR toLower(n.ha_id) CONTAINS toLower($term)) "
        "RETURN labels(n) AS labels, n AS node"
    )
    rows, truncated = await client.run_query_limited(query, {"term": term}, effective_limit)

    matches: list[dict[str, Any]] = []
    for row in rows:
        labels = [
            label for label in row["labels"] if label in (LABEL_AREA, LABEL_DEVICE, LABEL_ENTITY)
        ]
        if not labels:
            continue
        node = node_properties(row["node"])
        matches.append({"type": labels[0], "ha_id": node.get("ha_id"), "name": node.get("name")})

    warnings = [f"result truncated to {effective_limit} rows"] if truncated else []
    return build_tool_result(term, RESULT_TYPE_SEARCH, {"matches": matches}, warnings)


async def area_context(client: MemgraphClient, area: str) -> dict[str, Any]:
    """Resolve an area (id or name) and return its devices/entities (FR-002, FR-009)."""
    query = (
        f"MATCH (a:{LABEL_AREA}) "
        "WHERE a.ha_id = $identifier OR toLower(a.name) = toLower($identifier) "
        f"OPTIONAL MATCH (a)-[:{REL_HAS_DEVICE}]->(d:{LABEL_DEVICE}) "
        f"OPTIONAL MATCH (d)-[:{REL_HAS_ENTITY}]->(e1:{LABEL_ENTITY}) "
        f"OPTIONAL MATCH (a)<-[:{REL_HAS_AREA}]-(e2:{LABEL_ENTITY}) "
        "WITH a, collect(DISTINCT d) AS devices, "
        "[e IN collect(DISTINCT e1) + collect(DISTINCT e2) WHERE e IS NOT NULL] AS entities "
        "RETURN a, devices, entities LIMIT 1"
    )
    rows = await client.run_query(query, {"identifier": area})
    if not rows or rows[0].get("a") is None:
        return not_found_result(area, RESULT_TYPE_AREA_CONTEXT)

    row = rows[0]
    result = {
        "area": node_properties(row["a"]),
        "devices": [node_properties(d) for d in row.get("devices") or [] if d is not None],
        "entities": [node_properties(e) for e in row.get("entities") or [] if e is not None],
    }
    return build_tool_result(area, RESULT_TYPE_AREA_CONTEXT, result)


async def device_context(client: MemgraphClient, device: str) -> dict[str, Any]:
    """Resolve a device (id or name) and return its area/entities (FR-002, FR-011)."""
    query = (
        f"MATCH (d:{LABEL_DEVICE}) "
        "WHERE d.ha_id = $identifier OR toLower(d.name) = toLower($identifier) "
        f"OPTIONAL MATCH (a:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(d) "
        f"OPTIONAL MATCH (d)-[:{REL_HAS_ENTITY}]->(e:{LABEL_ENTITY}) "
        "RETURN d, a, collect(DISTINCT e) AS entities LIMIT 1"
    )
    rows = await client.run_query(query, {"identifier": device})
    if not rows or rows[0].get("d") is None:
        return not_found_result(device, RESULT_TYPE_DEVICE_CONTEXT)

    row = rows[0]
    result = {
        "device": node_properties(row["d"]),
        "area": node_properties(row["a"]) if row.get("a") is not None else None,
        "entities": [node_properties(e) for e in row.get("entities") or [] if e is not None],
    }
    return build_tool_result(device, RESULT_TYPE_DEVICE_CONTEXT, result)


async def entity_context(client: MemgraphClient, entity: str) -> dict[str, Any]:
    """Resolve an entity (id or name); return device/area/domain/integration/
    semantic classifications/direct dependencies where available (FR-002, FR-010)."""
    query = (
        f"MATCH (e:{LABEL_ENTITY}) "
        "WHERE e.ha_id = $identifier OR toLower(e.name) = toLower($identifier) "
        f"OPTIONAL MATCH (d:{LABEL_DEVICE})-[:{REL_HAS_ENTITY}]->(e) "
        f"OPTIONAL MATCH (a:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(d) "
        f"OPTIONAL MATCH (a2:{LABEL_AREA})-[:{REL_HAS_AREA}]->(e) "
        f"OPTIONAL MATCH (e)-[:{REL_IN_DOMAIN}]->(dom:{LABEL_DOMAIN}) "
        f"OPTIONAL MATCH (e)-[:{REL_PROVIDED_BY}]->(integ:{LABEL_INTEGRATION}) "
        f"OPTIONAL MATCH (e)-[:{REL_CLASSIFIED_AS}]->(st) "
        f"OPTIONAL MATCH (dependent:{LABEL_AUTOMATION})-[:{REL_REFERENCES}|{REL_CONTROLS}]->(e) "
        "RETURN e, d, coalesce(a, a2) AS area, dom, integ, "
        "collect(DISTINCT st.ha_id) AS semantic_types, "
        "collect(DISTINCT dependent.ha_id) AS dependents LIMIT 1"
    )
    rows = await client.run_query(query, {"identifier": entity})
    if not rows or rows[0].get("e") is None:
        return not_found_result(entity, RESULT_TYPE_ENTITY_CONTEXT)

    row = rows[0]
    dom = node_properties(row.get("dom"))
    integ = node_properties(row.get("integ"))
    result = {
        "entity": node_properties(row["e"]),
        "device": node_properties(row["d"]) if row.get("d") is not None else None,
        "area": node_properties(row["area"]) if row.get("area") is not None else None,
        "domain": dom.get("ha_id") if dom is not None else None,
        "integration": integ.get("ha_id") if integ is not None else None,
        "semantic_types": [t for t in row.get("semantic_types") or [] if t],
        "dependents": [d for d in row.get("dependents") or [] if d],
    }
    return build_tool_result(entity, RESULT_TYPE_ENTITY_CONTEXT, result)


async def automation_dependencies(client: MemgraphClient, entity: str) -> dict[str, Any]:
    """Automations related to `entity`, with a reason where available (FR-003, FR-008)."""
    query = (
        f"MATCH (e:{LABEL_ENTITY}) "
        "WHERE e.ha_id = $identifier OR toLower(e.name) = toLower($identifier) "
        f"OPTIONAL MATCH (auto:{LABEL_AUTOMATION})-[r:{REL_REFERENCES}|{REL_CONTROLS}]->(e) "
        "WITH e, collect(DISTINCT {automation: auto, reason: type(r)}) AS related "
        "RETURN e, [x IN related WHERE x.automation IS NOT NULL] AS related LIMIT 1"
    )
    rows = await client.run_query(query, {"identifier": entity})
    if not rows or rows[0].get("e") is None:
        return not_found_result(entity, RESULT_TYPE_AUTOMATION_DEPENDENCIES)

    row = rows[0]
    automations = []
    for item in row.get("related") or []:
        automation = node_properties(item.get("automation"))
        if automation is None:
            continue
        automations.append(
            {
                "ha_id": automation.get("ha_id"),
                "name": automation.get("name"),
                "reason": item.get("reason"),
            }
        )
    warnings = [] if automations else [_NO_DEPENDENCIES_WARNING]
    return build_tool_result(
        entity, RESULT_TYPE_AUTOMATION_DEPENDENCIES, {"automations": automations}, warnings
    )

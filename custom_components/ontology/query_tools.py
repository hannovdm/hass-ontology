"""Shared, transport-agnostic predefined query tools (User Story 1).

Plain async functions operating on a `MemgraphClient`, independent of any
calling transport (research.md §7). Home Assistant services, Assist intent
handlers (`intent_handlers.py`), and the MCP endpoint (`mcp_server.py`) all
call these same functions and share one JSON-compatible `ToolResult` shape
(data-model.md §2): `{"target", "result_type", "result", "warnings"}`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .const import (
    DEFAULT_QUERY_LIMIT,
    ENERGY_ROLE_CONSUMER,
    LABEL_AREA,
    LABEL_AUTOMATION,
    LABEL_DEVICE,
    LABEL_DOMAIN,
    LABEL_ENERGY_ROLE_ASSIGNMENT,
    LABEL_ENTITY,
    LABEL_GAS_CYLINDER,
    LABEL_INTEGRATION,
    MAX_QUERY_LIMIT,
    MEASUREMENT_KIND,
    MEASUREMENT_KIND_BATTERY,
    MEASUREMENT_KIND_POWER,
    MEASUREMENT_STATUS,
    MEASUREMENT_STATUS_AVAILABLE,
    MEASUREMENT_STATUS_INVALID_VALUE,
    MEASUREMENT_STATUS_UNAVAILABLE,
    MEASUREMENT_STATUS_UNSUPPORTED_UNIT,
    OUTCOME_AMBIGUOUS,
    OUTCOME_EMPTY,
    OUTCOME_NOT_FOUND,
    OUTCOME_OK,
    REL_ASSIGNS_ROLE_TO,
    REL_CLASSIFIED_AS,
    REL_CONTROLS,
    REL_HAS_AREA,
    REL_HAS_DEVICE,
    REL_HAS_ENTITY,
    REL_IN_DOMAIN,
    REL_PROVIDED_BY,
    REL_REFERENCES,
    RESULT_TYPE_ACTIVE_CONSUMERS,
    RESULT_TYPE_AREA_CONTEXT,
    RESULT_TYPE_AUTOMATION_DEPENDENCIES,
    RESULT_TYPE_DEVICE_CONTEXT,
    RESULT_TYPE_ENTITY_CONTEXT,
    RESULT_TYPE_LOW_BATTERY_AREAS,
    RESULT_TYPE_NOT_FOUND,
    RESULT_TYPE_SEARCH,
    RESULT_TYPE_UNASSIGNED_AREA_ITEMS,
    SOURCE_INFERRED,
    SOURCE_USER,
)
from .memgraph_client import MemgraphClient
from .redact import redact_value

_NO_DEPENDENCIES_WARNING = "no known dependencies found"

_TARGET_LABELS = {
    "area": LABEL_AREA,
    "device": LABEL_DEVICE,
    "entity": LABEL_ENTITY,
    "gas_cylinder": LABEL_GAS_CYLINDER,
}


@dataclass(frozen=True, slots=True)
class TargetResolution:
    """Deterministic result of resolving one operation target."""

    outcome: str
    target_type: str | None = None
    target_id: str | None = None
    candidates: list[dict[str, Any]] | None = None
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.candidates is None:
            object.__setattr__(self, "candidates", [])


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


def build_tool_result(
    target: str,
    result_type: str,
    result: dict[str, Any] | list[Any] | None,
    warnings: list[str] | None = None,
    *,
    outcome: str = OUTCOME_OK,
) -> dict[str, Any]:
    """Build the shared `ToolResult` envelope (data-model.md §2)."""
    return {
        "target": redact_value(target),
        "result_type": result_type,
        "outcome": outcome,
        "result": redact_value(result) if result is not None else None,
        "warnings": redact_value(list(warnings)) if warnings else [],
    }


def not_found_result(target: str, _result_type: str) -> dict[str, Any]:
    """Build the shared "not found" `ToolResult` (FR-007, FR-012, FR-017, SC-006).

    `result_type` is always `"not_found"`, never the requested tool's own
    result-type discriminator - the second argument is accepted for call-site
    readability only.
    """
    return build_tool_result(
        target, RESULT_TYPE_NOT_FOUND, None, outcome=OUTCOME_NOT_FOUND
    )


async def resolve_target(
    client: MemgraphClient,
    identifier: str,
    eligible_target_types: tuple[str, ...],
    *,
    limit: int,
) -> TargetResolution:
    """Resolve an exact stable ID or one unique exact display name."""
    if not eligible_target_types:
        raise ValueError("At least one eligible target type is required")
    try:
        labels = [
            (target_type, _TARGET_LABELS[target_type])
            for target_type in eligible_target_types
        ]
    except KeyError as err:
        raise ValueError(f"Unsupported target type: {err.args[0]}") from err

    effective_limit = min(max(limit, 1), MAX_QUERY_LIMIT)
    candidate_limit = effective_limit + 1
    branches = []
    for target_type, label in labels:
        branches.append(
            f"MATCH (n:{label}) "
            "WHERE n.ha_id = $identifier "
            "OR toLower(coalesce(n.name, '')) = toLower($identifier) "
            f"RETURN '{target_type}' AS target_type, n.ha_id AS target_id, "
            "n.name AS name, null AS area_name "
            "ORDER BY CASE WHEN n.ha_id = $identifier THEN 0 ELSE 1 END, "
            "toLower(coalesce(n.name, '')), n.ha_id "
            "LIMIT $candidate_limit"
        )
    rows = await client.run_query(
        " UNION ALL ".join(branches),
        {"identifier": identifier, "candidate_limit": candidate_limit},
    )

    eligible_rows = [
        row for row in rows if row.get("target_type") in eligible_target_types
    ]
    exact_id_matches = [
        row for row in eligible_rows if row.get("target_id") == identifier
    ]
    matches = exact_id_matches or eligible_rows
    candidates = sorted(
        (
            {
                "target_type": str(row["target_type"]),
                "target_id": str(row["target_id"]),
                "name": row.get("name"),
                "area_name": row.get("area_name"),
            }
            for row in matches
        ),
        key=lambda candidate: (
            candidate["target_type"],
            str(candidate["name"] or "").casefold(),
            candidate["target_id"],
        ),
    )
    if not candidates:
        return TargetResolution(outcome=OUTCOME_NOT_FOUND)
    if len(candidates) == 1:
        candidate = candidates[0]
        return TargetResolution(
            outcome=OUTCOME_OK,
            target_type=candidate["target_type"],
            target_id=candidate["target_id"],
        )
    return TargetResolution(
        outcome=OUTCOME_AMBIGUOUS,
        candidates=candidates[:effective_limit],
        truncated=len(candidates) > effective_limit,
    )


def _effective_limit(limit: int | None) -> int:
    return min(limit or DEFAULT_QUERY_LIMIT, MAX_QUERY_LIMIT)


def _bounded_collection(
    items: list[Any], name: str, warnings: list[str], limit: int = DEFAULT_QUERY_LIMIT
) -> list[Any]:
    if len(items) > limit:
        warnings.append(f"{name} truncated to {limit} items")
    return items[:limit]


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


async def unassigned_area_items(
    client: MemgraphClient, limit: int | None = None
) -> dict[str, Any]:
    """Return devices and sensor entities without an effective area."""
    effective_limit = _effective_limit(limit)
    query = (
        f"MATCH (item:{LABEL_DEVICE}) "
        f"WHERE NOT EXISTS {{ MATCH (:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(item) }} "
        "RETURN 'device' AS item_type, item.ha_id AS ha_id, "
        "coalesce(item.name, item.ha_id) AS name "
        "UNION ALL "
        f"MATCH (item:{LABEL_ENTITY})-[:{REL_IN_DOMAIN}]->"
        f"(:{LABEL_DOMAIN} {{ha_id: 'sensor'}}) "
        f"WHERE NOT EXISTS {{ MATCH (item)-[:{REL_HAS_AREA}]->(:{LABEL_AREA}) }} "
        f"AND NOT EXISTS {{ MATCH (:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->"
        f"(:{LABEL_DEVICE})-[:{REL_HAS_ENTITY}]->(item) }} "
        "RETURN 'sensor' AS item_type, item.ha_id AS ha_id, "
        "coalesce(item.name, item.ha_id) AS name "
        "ORDER BY item_type, toLower(name), ha_id"
    )
    rows, truncated = await client.run_query_limited(query, {}, effective_limit)
    devices = [row for row in rows if row.get("item_type") == "device"]
    sensors = [row for row in rows if row.get("item_type") == "sensor"]
    warnings = (
        [f"unassigned area results truncated to {effective_limit} items"]
        if truncated
        else []
    )
    return build_tool_result(
        "home",
        RESULT_TYPE_UNASSIGNED_AREA_ITEMS,
        {"devices": devices, "sensors": sensors, "truncated": truncated},
        warnings,
        outcome=OUTCOME_EMPTY if not rows else OUTCOME_OK,
    )


async def low_battery_areas(
    client: MemgraphClient,
    threshold_percentage: float = 20.0,
    max_age_hours: float = 24.0,
    limit: int | None = None,
    *,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Return fresh, strictly-below-threshold battery readings grouped by area."""
    threshold = float(threshold_percentage)
    maximum_age = float(max_age_hours)
    effective_limit = _effective_limit(limit)
    fresh_after_epoch = (now_epoch if now_epoch is not None else time.time()) - (
        maximum_age * 3600
    )
    parameters = {
        "threshold_percentage": threshold,
        "fresh_after_epoch": fresh_after_epoch,
    }
    query = (
        f"MATCH (e:{LABEL_ENTITY}) "
        f"WHERE e.{MEASUREMENT_KIND} = '{MEASUREMENT_KIND_BATTERY}' "
        f"AND e.{MEASUREMENT_STATUS} = '{MEASUREMENT_STATUS_AVAILABLE}' "
        "AND e.battery_percentage < $threshold_percentage "
        "AND e.measurement_last_updated_epoch >= $fresh_after_epoch "
        f"OPTIONAL MATCH (d:{LABEL_DEVICE})-[:{REL_HAS_ENTITY}]->(e) "
        f"OPTIONAL MATCH (device_area:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(d) "
        f"OPTIONAL MATCH (e)-[:{REL_HAS_AREA}]->(direct_area:{LABEL_AREA}) "
        "WITH e, d, coalesce(device_area, direct_area) AS area "
        "WHERE area IS NOT NULL "
        "RETURN area.ha_id AS area_id, area.name AS area_name, "
        "d.ha_id AS device_id, e.ha_id AS entity_id, "
        "coalesce(d.name, e.name, e.ha_id) AS name, "
        "e.name AS entity_name, e.battery_percentage AS percentage, "
        "e.measurement_last_updated AS measured_at "
        "ORDER BY toLower(coalesce(area.name, '')), area.ha_id, "
        "toLower(coalesce(d.name, e.name, '')), coalesce(d.ha_id, e.ha_id), e.ha_id"
    )
    rows, truncated = await client.run_query_limited(
        query, parameters, effective_limit
    )
    count_query = (
        f"MATCH (e:{LABEL_ENTITY}) "
        f"WHERE e.{MEASUREMENT_KIND} = '{MEASUREMENT_KIND_BATTERY}' "
        f"AND e.{MEASUREMENT_STATUS} IN $warning_statuses "
        f"RETURN e.{MEASUREMENT_STATUS} AS status, count(e) AS status_count "
        "ORDER BY status"
    )
    count_rows = await client.run_query(
        count_query,
        {
            "warning_statuses": [
                MEASUREMENT_STATUS_UNAVAILABLE,
                MEASUREMENT_STATUS_INVALID_VALUE,
                MEASUREMENT_STATUS_UNSUPPORTED_UNIT,
            ]
        },
    )
    status_counts = {
        str(row["status"]): int(row.get("status_count", 0))
        for row in count_rows
        if row.get("status") is not None
    }
    unavailable_count = sum(status_counts.values())

    areas_by_id: dict[str, dict[str, Any]] = {}
    items_by_area: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        area_id = str(row["area_id"])
        area = areas_by_id.setdefault(
            area_id,
            {
                "area_id": row.get("area_id"),
                "area_name": row.get("area_name") or row.get("area_id"),
                "items": [],
            },
        )
        item_key = str(row.get("device_id") or row["entity_id"])
        area_items = items_by_area.setdefault(area_id, {})
        item = area_items.get(item_key)
        if item is None:
            item = {
                "device_id": row.get("device_id"),
                "entity_id": row["entity_id"],
                "name": row.get("name") or row["entity_id"],
                "measurements": [],
            }
            area_items[item_key] = item
            area["items"].append(item)
        item["measurements"].append(
            {
                "entity_id": row["entity_id"],
                "name": row.get("entity_name") or row.get("name") or row["entity_id"],
                "percentage": float(row["percentage"]),
                "measured_at": row.get("measured_at"),
            }
        )

    areas = list(areas_by_id.values())
    warnings: list[str] = []
    warning_messages = (
        (MEASUREMENT_STATUS_UNAVAILABLE, "unavailable", "unavailable"),
        (MEASUREMENT_STATUS_INVALID_VALUE, "invalid", "invalid"),
        (
            MEASUREMENT_STATUS_UNSUPPORTED_UNIT,
            "has an unsupported unit",
            "have an unsupported unit",
        ),
    )
    for status, singular, plural in warning_messages:
        count = status_counts.get(status, 0)
        if count:
            measurement = "measurement" if count == 1 else "measurements"
            warnings.append(
                f"{count} battery {measurement} {singular if count == 1 else plural}"
            )
    if truncated:
        warnings.append(f"low battery results truncated to {effective_limit} items")
    payload = {
        "threshold_percentage": threshold,
        "max_age_hours": maximum_age,
        "areas": areas,
        "unavailable_count": unavailable_count,
        "truncated": truncated,
    }
    return build_tool_result(
        "home",
        RESULT_TYPE_LOW_BATTERY_AREAS,
        payload,
        warnings,
        outcome=OUTCOME_OK if areas else OUTCOME_EMPTY,
    )


async def active_consumers(
    client: MemgraphClient,
    threshold_watts: float = 1.0,
    max_age_hours: float = 24.0,
    limit: int | None = None,
    *,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Return fresh consumer-role power measurements grouped by device."""
    threshold = float(threshold_watts)
    maximum_age = float(max_age_hours)
    effective_limit = _effective_limit(limit)
    fresh_after_epoch = (now_epoch if now_epoch is not None else time.time()) - (
        maximum_age * 3600
    )
    parameters = {
        "threshold_watts": threshold,
        "fresh_after_epoch": fresh_after_epoch,
        "consumer_role": ENERGY_ROLE_CONSUMER,
        "user_source": SOURCE_USER,
        "inferred_source": SOURCE_INFERRED,
    }
    query = (
        f"MATCH (device:{LABEL_DEVICE})-[:{REL_HAS_ENTITY}]->(e:{LABEL_ENTITY}) "
        f"WHERE e.{MEASUREMENT_KIND} = '{MEASUREMENT_KIND_POWER}' "
        f"AND e.{MEASUREMENT_STATUS} = '{MEASUREMENT_STATUS_AVAILABLE}' "
        "AND e.power_watts > $threshold_watts "
        "AND e.measurement_last_updated_epoch >= $fresh_after_epoch "
        f"OPTIONAL MATCH (user_role:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        f"{{source: $user_source}})-[:{REL_ASSIGNS_ROLE_TO}]->(e) "
        f"OPTIONAL MATCH (inferred_role:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        f"{{source: $inferred_source}})-[:{REL_ASSIGNS_ROLE_TO}]->(e) "
        "WITH device, e, user_role, inferred_role, "
        "coalesce(user_role.role, inferred_role.role) AS effective_role, "
        "CASE WHEN user_role IS NOT NULL THEN user_role.source "
        "ELSE inferred_role.source END AS effective_source "
        "WHERE effective_role = $consumer_role "
        f"OPTIONAL MATCH (area:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(device) "
        "WITH device, area, e, effective_role, effective_source "
        "ORDER BY e.ha_id "
        "WITH device, area, collect({entity_id: e.ha_id, "
        "name: coalesce(e.name, e.ha_id), watts: e.power_watts, "
        "source_unit: e.unit_of_measurement, role: effective_role, "
        "role_source: effective_source, measured_at: e.measurement_last_updated}) "
        "AS measurements "
        "RETURN device.ha_id AS device_id, coalesce(device.name, device.ha_id) AS name, "
        "area.ha_id AS area_id, area.name AS area_name, measurements "
        "ORDER BY toLower(coalesce(device.name, '')), device.ha_id"
    )
    rows, truncated = await client.run_query_limited(
        query, parameters, effective_limit
    )

    unresolved_query = (
        f"MATCH (e:{LABEL_ENTITY}) "
        f"WHERE e.{MEASUREMENT_KIND} = '{MEASUREMENT_KIND_POWER}' "
        f"AND e.{MEASUREMENT_STATUS} = '{MEASUREMENT_STATUS_AVAILABLE}' "
        "AND e.power_watts > $threshold_watts "
        "AND e.measurement_last_updated_epoch >= $fresh_after_epoch "
        f"OPTIONAL MATCH (user_role:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        f"{{source: $user_source}})-[:{REL_ASSIGNS_ROLE_TO}]->(e) "
        f"OPTIONAL MATCH (inferred_role:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        f"{{source: $inferred_source}})-[:{REL_ASSIGNS_ROLE_TO}]->(e) "
        "WITH e, coalesce(user_role.role, inferred_role.role) AS effective_role "
        "WHERE effective_role IS NULL "
        "RETURN count(DISTINCT e) AS unresolved_role_count"
    )
    unresolved_rows = await client.run_query(unresolved_query, parameters)
    unresolved_role_count = (
        int(unresolved_rows[0].get("unresolved_role_count", 0))
        if unresolved_rows
        else 0
    )
    consumers = [
        {
            "device_id": row["device_id"],
            "name": row.get("name") or row["device_id"],
            "area_id": row.get("area_id"),
            "area_name": row.get("area_name"),
            "measurements": list(row.get("measurements") or []),
        }
        for row in rows
    ]
    active_device_ids = {consumer["device_id"] for consumer in consumers}
    known_rows = await client.run_query(
        f"MATCH (device:{LABEL_DEVICE})-[:{REL_HAS_ENTITY}]->(e:{LABEL_ENTITY}) "
        "WHERE e.device_class = 'energy' "
        "AND NOT device.ha_id IN $active_device_ids "
        f"OPTIONAL MATCH (user_role:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        f"{{source: $user_source}})-[:{REL_ASSIGNS_ROLE_TO}]->(e) "
        f"OPTIONAL MATCH (inferred_role:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        f"{{source: $inferred_source}})-[:{REL_ASSIGNS_ROLE_TO}]->(e) "
        "WITH device, e, coalesce(user_role.role, inferred_role.role) AS effective_role "
        "WHERE effective_role = $consumer_role "
        f"OPTIONAL MATCH (area:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(device) "
        "WITH device, area, collect(DISTINCT {entity_id: e.ha_id, "
        "name: coalesce(e.name, e.ha_id)}) AS energy_entities "
        "RETURN device.ha_id AS device_id, "
        "coalesce(device.name, device.ha_id) AS name, "
        "area.ha_id AS area_id, area.name AS area_name, energy_entities "
        "ORDER BY toLower(coalesce(device.name, '')), device.ha_id "
        "LIMIT $known_candidate_limit",
        {
            **parameters,
            "active_device_ids": sorted(active_device_ids),
            "known_candidate_limit": effective_limit + 1,
        },
    )
    known_truncated = len(known_rows) > effective_limit
    known_consumers = [
        {
            "device_id": row["device_id"],
            "name": row.get("name") or row["device_id"],
            "area_id": row.get("area_id"),
            "area_name": row.get("area_name"),
            "energy_entities": list(row.get("energy_entities") or []),
        }
        for row in known_rows[:effective_limit]
        if row["device_id"] not in active_device_ids
    ]
    warnings: list[str] = []
    if unresolved_role_count:
        noun = "measurement has" if unresolved_role_count == 1 else "measurements have"
        warnings.append(
            f"{unresolved_role_count} active power {noun} no effective energy role"
        )
    if truncated or known_truncated:
        warnings.append(
            f"active consumer results truncated to {effective_limit} devices"
        )
    payload = {
        "threshold_watts": threshold,
        "max_age_hours": maximum_age,
        "consumers": consumers,
        "unresolved_role_count": unresolved_role_count,
        "known_consumers_without_current_power": known_consumers,
        "truncated": truncated or known_truncated,
    }
    return build_tool_result(
        "home",
        RESULT_TYPE_ACTIVE_CONSUMERS,
        payload,
        warnings,
        outcome=OUTCOME_OK if consumers or known_consumers else OUTCOME_EMPTY,
    )


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
    warnings: list[str] = []
    devices = [node_properties(d) for d in row.get("devices") or [] if d is not None]
    entities = [node_properties(e) for e in row.get("entities") or [] if e is not None]
    devices = _bounded_collection(devices, "devices", warnings)
    entities = _bounded_collection(entities, "entities", warnings)
    entities_by_device: dict[str, list[dict[str, Any]]] = {}
    for entity_data in entities:
        device_id = entity_data.get("device_id")
        if device_id:
            entities_by_device.setdefault(device_id, []).append(entity_data)
    grouped_devices = [
        {**device_data, "entities": entities_by_device.get(device_data.get("ha_id"), [])}
        for device_data in devices
    ]
    if not devices:
        warnings.append("device relationships unavailable")
    if not entities:
        warnings.append("entity relationships unavailable")
    result = {
        "area": node_properties(row["a"]),
        "devices": grouped_devices,
        "entities": entities,
    }
    return build_tool_result(area, RESULT_TYPE_AREA_CONTEXT, result, warnings)


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
    warnings: list[str] = []
    entities = [node_properties(e) for e in row.get("entities") or [] if e is not None]
    entities = _bounded_collection(entities, "entities", warnings)
    if row.get("a") is None:
        warnings.append("area relationship unavailable")
    if not entities:
        warnings.append("entity relationships unavailable")
    result = {
        "device": node_properties(row["d"]),
        "area": node_properties(row["a"]) if row.get("a") is not None else None,
        "entities": entities,
    }
    return build_tool_result(device, RESULT_TYPE_DEVICE_CONTEXT, result, warnings)


async def entity_context(client: MemgraphClient, entity: str) -> dict[str, Any]:
    """Resolve an entity (id or name); return device/area/domain/integration/
    semantic classifications/direct dependencies where available (FR-002, FR-010)."""
    query = (
        f"MATCH (e:{LABEL_ENTITY}) "
        "WHERE e.ha_id = $identifier OR toLower(e.name) = toLower($identifier) "
        f"OPTIONAL MATCH (d:{LABEL_DEVICE})-[:{REL_HAS_ENTITY}]->(e) "
        f"OPTIONAL MATCH (a:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(d) "
        f"OPTIONAL MATCH (e)-[:{REL_HAS_AREA}]->(a2:{LABEL_AREA}) "
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
    warnings: list[str] = []
    semantic_types = [t for t in row.get("semantic_types") or [] if t]
    dependents = [d for d in row.get("dependents") or [] if d]
    semantic_types = _bounded_collection(semantic_types, "semantic types", warnings)
    dependents = _bounded_collection(dependents, "dependents", warnings)
    for value, relationship in (
        (row.get("d"), "device"),
        (row.get("area"), "area"),
        (dom, "domain"),
        (integ, "integration"),
    ):
        if value is None:
            warnings.append(f"{relationship} relationship unavailable")
    result = {
        "entity": node_properties(row["e"]),
        "device": node_properties(row["d"]) if row.get("d") is not None else None,
        "area": node_properties(row["area"]) if row.get("area") is not None else None,
        "domain": dom.get("ha_id") if dom is not None else None,
        "integration": integ.get("ha_id") if integ is not None else None,
        "semantic_types": semantic_types,
        "dependents": dependents,
    }
    return build_tool_result(entity, RESULT_TYPE_ENTITY_CONTEXT, result, warnings)


async def automation_dependencies(client: MemgraphClient, entity: str) -> dict[str, Any]:
    """Automations related to `entity`, with a reason where available (FR-003, FR-008)."""
    query = (
        f"MATCH (e:{LABEL_ENTITY}) "
        "WHERE e.ha_id = $identifier OR toLower(e.name) = toLower($identifier) "
        f"OPTIONAL MATCH (auto:{LABEL_AUTOMATION})-[r:{REL_REFERENCES}|{REL_CONTROLS}]->(e) "
        "WITH count(DISTINCT e) AS matched_count, "
        "collect(DISTINCT {automation: auto, reason: type(r)}) AS related "
        "RETURN matched_count, [x IN related WHERE x.automation IS NOT NULL] AS related"
    )
    rows = await client.run_query(query, {"identifier": entity})
    if not rows or not rows[0].get("matched_count"):
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
    warnings: list[str] = [] if automations else [_NO_DEPENDENCIES_WARNING]
    automations = _bounded_collection(automations, "automations", warnings)
    return build_tool_result(
        entity, RESULT_TYPE_AUTOMATION_DEPENDENCIES, {"automations": automations}, warnings
    )

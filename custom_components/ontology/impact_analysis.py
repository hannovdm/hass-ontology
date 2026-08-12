"""Bounded-depth entity/device/area impact analysis (User Stories 3-5).

Implements the traversal strategy from research.md §5: entity-level impact
analysis is a bounded 2-hop Cypher traversal; device-level aggregates
entity-level results across the device's live `HAS_ENTITY` edges; area-level
aggregates device-level results across the area's current devices plus any
directly-related entities.
"""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant

from . import agent_audit, query_tools
from .const import (
    DEFAULT_QUERY_LIMIT,
    IMPACT_SCOPE_AREA,
    IMPACT_SCOPE_DEVICE,
    IMPACT_SCOPE_ENTITY,
    LABEL_AREA,
    LABEL_AUTOMATION,
    LABEL_DASHBOARD,
    LABEL_DASHBOARD_CARD,
    LABEL_DEVICE,
    LABEL_ENTITY,
    LABEL_SCENE,
    LABEL_SCRIPT,
    MAX_QUERY_LIMIT,
    REL_CLASSIFIED_AS,
    REL_CONTAINS_CARD,
    REL_CONTROLS,
    REL_DISPLAYS_ENTITY,
    REL_HAS_AREA,
    REL_HAS_DEVICE,
    REL_HAS_ENTITY,
    REL_REFERENCES,
    RESULT_TYPE_IMPACT_ANALYSIS,
    RESULT_TYPE_NOT_FOUND,
)
from .memgraph_client import MemgraphClient
from .query_tools import build_tool_result, node_properties, not_found_result

_NO_DEPENDENCIES_WARNING = "no known dependencies found"

_EMPTY_DEPENDENCIES: dict[str, list[Any]] = {
    "automations": [],
    "scripts": [],
    "scenes": [],
    "dashboards": [],
    "semantic_assets": [],
}


def _node_ref(node: Any) -> dict[str, Any] | None:
    properties = node_properties(node)
    if properties is None:
        return None
    return {
        "ha_id": properties.get("ha_id"),
        "name": properties.get("name") or properties.get("title") or properties.get("ha_id"),
    }


async def _resolve_node(
    client: MemgraphClient, label: str, identifier: str
) -> dict[str, Any] | None:
    """Resolve a node by `ha_id` or case-insensitive `name` (bounded, `LIMIT 1`)."""
    query = (
        f"MATCH (n:{label}) WHERE n.ha_id = $identifier OR toLower(n.name) = toLower($identifier) "
        "RETURN n LIMIT 1"
    )
    rows = await client.run_query(query, {"identifier": identifier})
    if not rows or rows[0].get("n") is None:
        return None
    return node_properties(rows[0]["n"])


async def _entity_dependencies(client: MemgraphClient, entity_id: str) -> dict[str, Any]:
    """Bounded 2-hop traversal of one entity's dependents (research.md §5)."""
    query = (
        f"MATCH (e:{LABEL_ENTITY} {{ha_id: $entity_id}}) "
        f"OPTIONAL MATCH (auto:{LABEL_AUTOMATION})-[:{REL_REFERENCES}|{REL_CONTROLS}]->(e) "
        f"OPTIONAL MATCH (scr:{LABEL_SCRIPT})-[:{REL_REFERENCES}|{REL_CONTROLS}]->(e) "
        f"OPTIONAL MATCH (scn:{LABEL_SCENE})-[:{REL_REFERENCES}|{REL_CONTROLS}]->(e) "
        f"OPTIONAL MATCH (card:{LABEL_DASHBOARD_CARD})-[:{REL_DISPLAYS_ENTITY}]->(e) "
        f"OPTIONAL MATCH (dash:{LABEL_DASHBOARD})-[:{REL_CONTAINS_CARD}]->(card) "
        f"OPTIONAL MATCH (e)-[:{REL_CLASSIFIED_AS}]->(st) "
        "RETURN "
        "collect(DISTINCT auto) AS automations, "
        "collect(DISTINCT scr) AS scripts, "
        "collect(DISTINCT scn) AS scenes, "
        "collect(DISTINCT dash) AS dashboards, "
        "collect(DISTINCT st) AS semantic_assets"
    )
    rows, _truncated = await client.run_query_limited(
        query, {"entity_id": entity_id}, MAX_QUERY_LIMIT
    )
    if not rows:
        return dict(_EMPTY_DEPENDENCIES)
    row = rows[0]
    dependencies = {
        "automations": [_node_ref(n) for n in row.get("automations") or [] if n],
        "scripts": [_node_ref(n) for n in row.get("scripts") or [] if n],
        "scenes": [_node_ref(n) for n in row.get("scenes") or [] if n],
        "dashboards": [_node_ref(n) for n in row.get("dashboards") or [] if n],
        "semantic_assets": [_node_ref(n) for n in row.get("semantic_assets") or [] if n],
    }
    warnings = []
    for key in _EMPTY_DEPENDENCIES:
        if len(dependencies[key]) > DEFAULT_QUERY_LIMIT:
            warnings.append(f"{key.replace('_', ' ')} truncated to {DEFAULT_QUERY_LIMIT} items")
            dependencies[key] = dependencies[key][:DEFAULT_QUERY_LIMIT]
    dependencies["_warnings"] = warnings
    return dependencies


def _merge_dependencies(*dependency_dicts: dict[str, Any]) -> dict[str, Any]:
    """Merge multiple `_entity_dependencies`-shaped dicts, de-duplicated by `ha_id`."""
    merged: dict[str, list[Any]] = {key: [] for key in _EMPTY_DEPENDENCIES}
    seen: dict[str, set[str | None]] = {key: set() for key in _EMPTY_DEPENDENCIES}
    for deps in dependency_dicts:
        for key in merged:
            for item in deps.get(key, []) or []:
                if item is None:
                    continue
                identifier = item.get("ha_id")
                if identifier in seen[key]:
                    continue
                seen[key].add(identifier)
                if len(merged[key]) < DEFAULT_QUERY_LIMIT:
                    merged[key].append(item)
    merged["_warnings"] = list(
        dict.fromkeys(
            warning
            for deps in dependency_dicts
            for warning in deps.get("_warnings", [])
        )
    )
    return merged


def _build_result(
    scope: str,
    *,
    affected_entities: list[str] | None = None,
    affected_devices: list[str] | None = None,
    dependencies: dict[str, Any] | None = None,
    current_area: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dependencies = dependencies or dict(_EMPTY_DEPENDENCIES)
    has_dependencies = any(dependencies[key] for key in _EMPTY_DEPENDENCIES)
    result = {
        "scope": scope,
        "affected_entities": affected_entities or [],
        "affected_devices": affected_devices or [],
        "automations": dependencies["automations"],
        "scripts": dependencies["scripts"],
        "scenes": dependencies["scenes"],
        "dashboards": dependencies["dashboards"],
        "semantic_assets": dependencies["semantic_assets"],
        "has_dependencies": has_dependencies,
    }
    if current_area is not None:
        result["current_area"] = _node_ref(current_area)
    return result


def _warnings_for(result: dict[str, Any], dependencies: dict[str, Any]) -> list[str]:
    warnings = list(dependencies.get("_warnings", []))
    if not result["has_dependencies"]:
        warnings.append(_NO_DEPENDENCIES_WARNING)
    return warnings


async def _analyze_entity(client: MemgraphClient, target: str) -> dict[str, Any]:
    entity = await _resolve_node(client, LABEL_ENTITY, target)
    if entity is None:
        return not_found_result(target, RESULT_TYPE_IMPACT_ANALYSIS)
    dependencies = await _entity_dependencies(client, entity["ha_id"])
    result = _build_result(IMPACT_SCOPE_ENTITY, dependencies=dependencies)
    return build_tool_result(
        target, RESULT_TYPE_IMPACT_ANALYSIS, result, _warnings_for(result, dependencies)
    )


async def _analyze_device(client: MemgraphClient, target: str) -> dict[str, Any]:
    device = await _resolve_node(client, LABEL_DEVICE, target)
    if device is None:
        return not_found_result(target, RESULT_TYPE_IMPACT_ANALYSIS)
    entity_rows = await client.run_query(
        f"MATCH (d:{LABEL_DEVICE} {{ha_id: $device_id}})-[:{REL_HAS_ENTITY}]->(e:{LABEL_ENTITY}) "
        f"OPTIONAL MATCH (a:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(d) "
        "RETURN e, a AS area",
        {"device_id": device["ha_id"]},
    )
    entities = [
        node_properties(row["e"])
        for row in entity_rows[:DEFAULT_QUERY_LIMIT]
        if row.get("e") is not None
    ]
    current_area = next(
        (node_properties(row["area"]) for row in entity_rows if row.get("area") is not None),
        None,
    )
    dependency_dicts = await asyncio.gather(
        *(_entity_dependencies(client, e["ha_id"]) for e in entities)
    )
    merged = _merge_dependencies(*dependency_dicts)
    if len(entity_rows) > DEFAULT_QUERY_LIMIT:
        merged.setdefault("_warnings", []).append(
            f"affected entities truncated to {DEFAULT_QUERY_LIMIT} items"
        )
    result = _build_result(
        IMPACT_SCOPE_DEVICE,
        affected_entities=[e.get("ha_id") for e in entities],
        dependencies=merged,
        current_area=current_area,
    )
    return build_tool_result(
        target, RESULT_TYPE_IMPACT_ANALYSIS, result, _warnings_for(result, merged)
    )


async def _analyze_area(client: MemgraphClient, target: str) -> dict[str, Any]:
    area = await _resolve_node(client, LABEL_AREA, target)
    if area is None:
        return not_found_result(target, RESULT_TYPE_IMPACT_ANALYSIS)

    device_rows = await client.run_query(
        f"MATCH (a:{LABEL_AREA} {{ha_id: $area_id}})-[:{REL_HAS_DEVICE}]->(d:{LABEL_DEVICE}) "
        "RETURN d",
        {"area_id": area["ha_id"]},
    )
    devices = [node_properties(row["d"]) for row in device_rows if row.get("d") is not None]

    affected_entities: list[str] = []
    dependency_dicts: list[dict[str, Any]] = []
    device_results = await asyncio.gather(
        *(_analyze_device(client, device["ha_id"]) for device in devices[:DEFAULT_QUERY_LIMIT])
    )
    for device_result in device_results:
        inner = device_result.get("result") or {}
        affected_entities.extend(inner.get("affected_entities", []))
        dependency_dicts.append(inner)

    # Directly-related entities (HAS_AREA straight to the area, not via a device).
    direct_entity_rows = await client.run_query(
        f"MATCH (a:{LABEL_AREA} {{ha_id: $area_id}})<-[:{REL_HAS_AREA}]-(e:{LABEL_ENTITY}) "
        "RETURN e",
        {"area_id": area["ha_id"]},
    )
    direct_entities = []
    for row in direct_entity_rows[:DEFAULT_QUERY_LIMIT]:
        entity = row.get("e")
        if entity is None:
            continue
        entity = node_properties(entity)
        direct_entities.append(entity)
        affected_entities.append(entity["ha_id"])
    dependency_dicts.extend(
        await asyncio.gather(
            *(_entity_dependencies(client, entity["ha_id"]) for entity in direct_entities)
        )
    )

    merged = _merge_dependencies(*dependency_dicts)
    if len(device_rows) > DEFAULT_QUERY_LIMIT:
        merged.setdefault("_warnings", []).append(
            f"affected devices truncated to {DEFAULT_QUERY_LIMIT} items"
        )
    if len(direct_entity_rows) > DEFAULT_QUERY_LIMIT:
        merged.setdefault("_warnings", []).append(
            f"direct entities truncated to {DEFAULT_QUERY_LIMIT} items"
        )
    result = _build_result(
        IMPACT_SCOPE_AREA,
        affected_entities=sorted(set(affected_entities)),
        affected_devices=[d.get("ha_id") for d in devices[:DEFAULT_QUERY_LIMIT]],
        dependencies=merged,
    )
    return build_tool_result(
        target, RESULT_TYPE_IMPACT_ANALYSIS, result, _warnings_for(result, merged)
    )


async def analyze(
    client: MemgraphClient,
    scope: str,
    target: str,
    *,
    hass: HomeAssistant | None = None,
    entry_id: str | None = None,
) -> dict[str, Any]:
    """Run the bounded-depth impact-analysis traversal for `scope` (FR-013–FR-018)."""
    try:
        if scope == IMPACT_SCOPE_ENTITY:
            tool_result = await _analyze_entity(client, target)
        elif scope == IMPACT_SCOPE_DEVICE:
            tool_result = await _analyze_device(client, target)
        elif scope == IMPACT_SCOPE_AREA:
            tool_result = await _analyze_area(client, target)
        else:
            raise ValueError(f"Unknown impact analysis scope: {scope!r}")
    except Exception as err:
        if hass is not None and entry_id is not None:
            await agent_audit.async_append_record(
                hass,
                entry_id,
                {
                    "event": "impact_analysis",
                    "scope": scope,
                    "status": "error",
                    "result_count": 0,
                    "error_category": type(err).__name__,
                    "has_dependencies": False,
                    "timestamp": agent_audit.now_iso(),
                },
            )
        raise

    if hass is not None and entry_id is not None:
        result = tool_result.get("result") or {}
        not_found = tool_result.get("result_type") == RESULT_TYPE_NOT_FOUND
        await agent_audit.async_append_record(
            hass,
            entry_id,
            {
                "event": "impact_analysis",
                "scope": scope,
                "status": "not_found" if not_found else "resolved",
                "result_count": 0 if not_found else query_tools.count_results(result),
                "error_category": None,
                "has_dependencies": bool(result.get("has_dependencies")),
                "timestamp": agent_audit.now_iso(),
            },
        )
    return tool_result

"""Allow-list JSON context export for local AI agents (User Story 6).

Every export uses an explicit allow-list field projection per node type
(research.md §6, data-model.md §4) rather than the block-list `redact.py`
helper used elsewhere - a never-anticipated future node property can never
leak through an allow-list projection.
"""

from __future__ import annotations

from typing import Any

from . import impact_analysis, query_tools
from .const import (
    CONTEXT_EXPORT_ALLOWED_FIELDS,
    EXPORT_TYPE_AREA,
    EXPORT_TYPE_AUTOMATION,
    EXPORT_TYPE_DEVICE,
    EXPORT_TYPE_ENTITY,
    EXPORT_TYPE_IMPACT,
    EXPORT_TYPE_WHOLE_HOME,
    IMPACT_SCOPE_AREA,
    IMPACT_SCOPE_DEVICE,
    IMPACT_SCOPE_ENTITY,
    LABEL_AREA,
    LABEL_AUTOMATION,
    LABEL_DEVICE,
    LABEL_ENTITY,
    LABEL_SEMANTIC_TYPE,
    LABEL_VALIDATION_FINDING,
    REL_CLASSIFIED_AS,
    REL_CONTROLS,
    REL_REFERENCES,
    RESULT_TYPE_EXPORT_CONTEXT,
    RESULT_TYPE_NOT_FOUND,
    SEMANTIC_TYPE_LABELS,
)
from .memgraph_client import MemgraphClient
from .query_tools import build_tool_result, node_properties, not_found_result


def project(node: dict[str, Any] | None, label: str) -> dict[str, Any] | None:
    """Project `node` through the allow-list for `label` (data-model.md §4)."""
    if node is None:
        return None
    if label in SEMANTIC_TYPE_LABELS:
        return _project_semantic_asset(node, label)
    allowed = CONTEXT_EXPORT_ALLOWED_FIELDS.get(label, ())
    return {field: node.get(field) for field in allowed if field in node}


def _project_semantic_asset(node: dict[str, Any], asset_label: str) -> dict[str, Any]:
    """Project a semantic asset instance node (labelled e.g. `GasCylinder`)
    through the `SemanticType` allow-list (`ha_id`, `asset_type`, `entity_id`)."""
    allowed = CONTEXT_EXPORT_ALLOWED_FIELDS[LABEL_SEMANTIC_TYPE]
    projected = {field: node.get(field) for field in allowed if field in node}
    projected.setdefault("asset_type", asset_label)
    ha_id = node.get("ha_id") or ""
    if not projected.get("entity_id"):
        projected["entity_id"] = ha_id.split("::", 1)[0] if "::" in ha_id else None
    projected["ha_id"] = ha_id
    return projected


async def _export_area_or_whole_home(
    client: MemgraphClient, target: str | None
) -> dict[str, Any] | None:
    """Devices, entities, automations, semantic assets, validation findings
    (FR-021), scoped to `target` if given, or the whole graph otherwise."""
    if target is not None:
        area_result = await query_tools.area_context(client, target)
        if area_result["result_type"] == RESULT_TYPE_NOT_FOUND:
            return None
        area_data = area_result["result"]
        devices = area_data.get("devices", [])
        entities = area_data.get("entities", [])
        entity_ids = [e.get("ha_id") for e in entities if e.get("ha_id")]
        automations_rows = await client.run_query(
            f"MATCH (auto:{LABEL_AUTOMATION})"
            f"-[:{REL_REFERENCES}|{REL_CONTROLS}]->(e:{LABEL_ENTITY}) "
            "WHERE e.ha_id IN $entity_ids RETURN DISTINCT auto",
            {"entity_ids": entity_ids},
        )
        semantic_rows = await client.run_query(
            f"MATCH (e:{LABEL_ENTITY})-[:{REL_CLASSIFIED_AS}]->(st) "
            "WHERE e.ha_id IN $entity_ids RETURN st, e.ha_id AS entity_id, labels(st) AS labels",
            {"entity_ids": entity_ids},
        )
        finding_rows = await client.run_query(
            f"MATCH (f:{LABEL_VALIDATION_FINDING}) "
            "WHERE f.target_id IN $entity_ids OR f.target_id = $area_id RETURN f",
            {"entity_ids": entity_ids, "area_id": target},
        )
    else:
        devices = [
            node_properties(r["d"])
            for r in await client.run_query(f"MATCH (d:{LABEL_DEVICE}) RETURN d")
        ]
        entities = [
            node_properties(r["e"])
            for r in await client.run_query(f"MATCH (e:{LABEL_ENTITY}) RETURN e")
        ]
        automations_rows = await client.run_query(f"MATCH (auto:{LABEL_AUTOMATION}) RETURN auto")
        semantic_rows = await client.run_query(
            f"MATCH (e:{LABEL_ENTITY})-[:{REL_CLASSIFIED_AS}]->(st) "
            "RETURN st, e.ha_id AS entity_id, labels(st) AS labels"
        )
        finding_rows = await client.run_query(f"MATCH (f:{LABEL_VALIDATION_FINDING}) RETURN f")

    semantic_assets = []
    for row in semantic_rows:
        node = node_properties(row.get("st"))
        if node is None:
            continue
        labels = [label for label in row.get("labels") or [] if label in SEMANTIC_TYPE_LABELS]
        asset_label = labels[0] if labels else LABEL_SEMANTIC_TYPE
        projected = project(node, asset_label)
        if projected is not None and row.get("entity_id"):
            projected["entity_id"] = row["entity_id"]
        semantic_assets.append(projected)

    return {
        "devices": [p for p in (project(d, LABEL_DEVICE) for d in devices) if p is not None],
        "entities": [p for p in (project(e, LABEL_ENTITY) for e in entities) if p is not None],
        "automations": [
            p
            for p in (
                project(node_properties(r["auto"]), LABEL_AUTOMATION)
                for r in automations_rows
                if r.get("auto") is not None
            )
            if p is not None
        ],
        "semantic_assets": semantic_assets,
        "validation_findings": [
            p
            for p in (
                project(node_properties(r["f"]), LABEL_VALIDATION_FINDING)
                for r in finding_rows
                if r.get("f") is not None
            )
            if p is not None
        ],
    }


async def _export_entity(client: MemgraphClient, target: str) -> dict[str, Any] | None:
    """Direct graph relationships only (FR-022)."""
    tool_result = await query_tools.entity_context(client, target)
    if tool_result["result_type"] == RESULT_TYPE_NOT_FOUND:
        return None
    result = tool_result["result"]
    relationships: list[dict[str, Any]] = []
    if result.get("device"):
        relationships.append(
            {"type": "HAS_ENTITY", "target": project(result["device"], LABEL_DEVICE)}
        )
    if result.get("area"):
        relationships.append({"type": "HAS_AREA", "target": project(result["area"], LABEL_AREA)})
    for dependent_id in result.get("dependents", []):
        relationships.append({"type": "REFERENCES", "target": {"ha_id": dependent_id}})
    return {"relationships": relationships}


async def _export_device(client: MemgraphClient, target: str) -> dict[str, Any] | None:
    """Direct graph relationships only (FR-022)."""
    tool_result = await query_tools.device_context(client, target)
    if tool_result["result_type"] == RESULT_TYPE_NOT_FOUND:
        return None
    result = tool_result["result"]
    relationships: list[dict[str, Any]] = []
    if result.get("area"):
        relationships.append({"type": "HAS_DEVICE", "target": project(result["area"], LABEL_AREA)})
    for entity in result.get("entities", []):
        relationships.append({"type": "HAS_ENTITY", "target": project(entity, LABEL_ENTITY)})
    return {"relationships": relationships}


async def _export_automation(client: MemgraphClient, target: str) -> dict[str, Any] | None:
    """Direct graph relationships only (FR-022)."""
    query = (
        f"MATCH (auto:{LABEL_AUTOMATION}) "
        "WHERE auto.ha_id = $identifier OR toLower(auto.name) = toLower($identifier) "
        f"OPTIONAL MATCH (auto)-[r:{REL_REFERENCES}|{REL_CONTROLS}]->(e:{LABEL_ENTITY}) "
        "WITH auto, collect(DISTINCT {reason: type(r), entity: e}) AS refs "
        "RETURN auto, [x IN refs WHERE x.entity IS NOT NULL] AS refs LIMIT 1"
    )
    rows = await client.run_query(query, {"identifier": target})
    if not rows or rows[0].get("auto") is None:
        return None
    row = rows[0]
    relationships = [
        {"type": ref["reason"], "target": project(node_properties(ref["entity"]), LABEL_ENTITY)}
        for ref in row.get("refs") or []
        if ref.get("entity") is not None
    ]
    return {"relationships": relationships}


async def _export_impact(client: MemgraphClient, target: str) -> dict[str, Any] | None:
    """Pass an `ImpactAnalysisResult` through the allow-list projections (data-model.md §4)."""
    for scope in (IMPACT_SCOPE_ENTITY, IMPACT_SCOPE_DEVICE, IMPACT_SCOPE_AREA):
        tool_result = await impact_analysis.analyze(client, scope, target)
        if tool_result["result_type"] != RESULT_TYPE_NOT_FOUND:
            return tool_result["result"]
    return None


async def export(
    client: MemgraphClient, export_type: str, target: str | None = None
) -> dict[str, Any]:
    """Build the allow-list JSON export document for `export_type` (FR-019–FR-022)."""
    if export_type == EXPORT_TYPE_WHOLE_HOME:
        document = await _export_area_or_whole_home(client, None)
    elif export_type == EXPORT_TYPE_AREA:
        document = await _export_area_or_whole_home(client, target)
    elif export_type == EXPORT_TYPE_ENTITY:
        document = await _export_entity(client, target)
    elif export_type == EXPORT_TYPE_DEVICE:
        document = await _export_device(client, target)
    elif export_type == EXPORT_TYPE_AUTOMATION:
        document = await _export_automation(client, target)
    elif export_type == EXPORT_TYPE_IMPACT:
        document = await _export_impact(client, target)
    else:
        raise ValueError(f"Unknown export_type: {export_type!r}")

    resolved_target = target or "whole_home"
    if document is None:
        return not_found_result(resolved_target, RESULT_TYPE_EXPORT_CONTEXT)
    return build_tool_result(resolved_target, RESULT_TYPE_EXPORT_CONTEXT, document)

"""On-demand validation engine covering the 9 finding categories (User Story 5).

Each category is an independent, idempotent Cypher read + ``ValidationFinding``
MERGE pass (research.md §6). Findings are created/updated on detection and
marked resolved when no longer detected on a subsequent run, per the
retention policy documented in spec.md's Assumptions.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import semantic_classifier
from .const import (
    DOMAIN,
    FINDING_DUPLICATE_ENTITY,
    FINDING_INVALID_RELATIONSHIP,
    FINDING_MISSING_AREA,
    FINDING_MISSING_DEVICE,
    FINDING_MISSING_SEMANTIC_CLASSIFICATION,
    FINDING_ORPHAN_DEVICE,
    FINDING_ORPHAN_ENTITY,
    FINDING_SCHEMA_MISMATCH,
    FINDING_STATUS_OPEN,
    FINDING_STATUS_RESOLVED,
    FINDING_UNAVAILABLE_CRITICAL_ENTITY,
    LABEL_AREA,
    LABEL_DEVICE,
    LABEL_ENTITY,
    LABEL_ONTOLOGY_SCHEMA,
    LABEL_SEMANTIC_TYPE,
    LABEL_VALIDATION_FINDING,
    REL_RELATES_TO,
    SCHEMA_SINGLETON_ID,
    SCHEMA_VERSION,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SOURCE_GENERATED,
)
from .graph_builder import get_schema_version
from .memgraph_client import MemgraphClient

_LOGGER = logging.getLogger(__name__)

_CATEGORY_SEVERITY: dict[str, str] = {
    FINDING_MISSING_AREA: SEVERITY_INFO,
    FINDING_MISSING_DEVICE: SEVERITY_INFO,
    FINDING_ORPHAN_ENTITY: SEVERITY_WARNING,
    FINDING_ORPHAN_DEVICE: SEVERITY_WARNING,
    FINDING_DUPLICATE_ENTITY: SEVERITY_WARNING,
    FINDING_UNAVAILABLE_CRITICAL_ENTITY: SEVERITY_ERROR,
    FINDING_INVALID_RELATIONSHIP: SEVERITY_ERROR,
    FINDING_SCHEMA_MISMATCH: SEVERITY_ERROR,
    FINDING_MISSING_SEMANTIC_CLASSIFICATION: SEVERITY_INFO,
}


def _finding_ha_id(category: str, target_ha_id: str) -> str:
    """Stable per-finding id (data-model.md `"<category>::<target ha_id>"`)."""
    return f"{category}::{target_ha_id}"


async def _detect_missing_area(client: MemgraphClient) -> list[tuple[str, str]]:
    """Devices with no HAS_AREA relationship to any Area."""
    query = (
        f"MATCH (d:{LABEL_DEVICE}) WHERE NOT (:{LABEL_AREA})-[:HAS_DEVICE]->(d) "
        "RETURN d.ha_id AS ha_id"
    )
    rows = await client.run_query(query, {})
    return [(row["ha_id"], LABEL_DEVICE) for row in rows]


async def _detect_missing_device(client: MemgraphClient) -> list[tuple[str, str]]:
    """Entities with no incoming HAS_ENTITY from any Device.

    Domain-agnostic simplification: not every entity is expected to belong
    to a device (e.g. some helper/template entities never do), so this
    category is informational (severity=info), not a hard failure.
    """
    query = (
        f"MATCH (e:{LABEL_ENTITY}) WHERE NOT (:{LABEL_DEVICE})-[:HAS_ENTITY]->(e) "
        "RETURN e.ha_id AS ha_id"
    )
    rows = await client.run_query(query, {})
    return [(row["ha_id"], LABEL_ENTITY) for row in rows]


async def _detect_orphan_entity(client: MemgraphClient) -> list[tuple[str, str]]:
    """Entities with no Device AND no Area/Domain relationship at all."""
    query = (
        f"MATCH (e:{LABEL_ENTITY}) "
        "WHERE NOT (:{device})-[:HAS_ENTITY]->(e) "
        "AND NOT (e)-[:IN_DOMAIN]->() "
        "RETURN e.ha_id AS ha_id"
    ).replace("{device}", LABEL_DEVICE)
    rows = await client.run_query(query, {})
    return [(row["ha_id"], LABEL_ENTITY) for row in rows]


async def _detect_orphan_device(client: MemgraphClient) -> list[tuple[str, str]]:
    """Devices with no entities at all (HAS_ENTITY out-degree zero)."""
    query = (
        f"MATCH (d:{LABEL_DEVICE}) WHERE NOT (d)-[:HAS_ENTITY]->(:{LABEL_ENTITY}) "
        "RETURN d.ha_id AS ha_id"
    )
    rows = await client.run_query(query, {})
    return [(row["ha_id"], LABEL_DEVICE) for row in rows]


async def _detect_duplicate_entity(client: MemgraphClient) -> list[tuple[str, str]]:
    """Entity nodes sharing the same non-null `name` property."""
    query = (
        f"MATCH (e:{LABEL_ENTITY}) WHERE e.name IS NOT NULL "
        "WITH e.name AS name, collect(e.ha_id) AS ids "
        "WHERE size(ids) > 1 "
        "UNWIND ids AS ha_id "
        "RETURN ha_id"
    )
    rows = await client.run_query(query, {})
    return [(row["ha_id"], LABEL_ENTITY) for row in rows]


async def _detect_unavailable_critical_entity(
    hass: HomeAssistant, client: MemgraphClient
) -> list[tuple[str, str]]:
    """Entities the graph knows about whose current HA state is unavailable.

    "Critical" here means entities that back a semantic asset (already
    classified) - an unavailable entity backing a GasCylinder/EnergyAsset/
    SecurityDevice/etc. is more actionable than an arbitrary unavailable
    helper entity.
    """
    query = (
        f"MATCH (:{LABEL_SEMANTIC_TYPE})<-[:CLASSIFIED_AS]-(e:{LABEL_ENTITY}) "
        "RETURN DISTINCT e.ha_id AS ha_id"
    )
    rows = await client.run_query(query, {})
    findings: list[tuple[str, str]] = []
    for row in rows:
        entity_id = row["ha_id"]
        state = hass.states.get(entity_id)
        if state is not None and state.state == "unavailable":
            findings.append((entity_id, LABEL_ENTITY))
    return findings


async def _detect_invalid_relationship(client: MemgraphClient) -> list[tuple[str, str]]:
    """Defensive check: any node/relationship missing its `source` property.

    True dangling edges are impossible in Memgraph/Neo4j's property graph
    model (a relationship cannot reference a non-existent node), so this
    category instead guards against writes that skipped the `source`
    bookkeeping every other write in this integration always sets.
    """
    query = (
        "MATCH (a)-[r]->(b) WHERE r.source IS NULL OR a.source IS NULL OR b.source IS NULL "
        "RETURN DISTINCT coalesce(a.ha_id, 'unknown') AS ha_id"
    )
    rows = await client.run_query(query, {})
    return [(row["ha_id"], LABEL_ENTITY) for row in rows]


async def _detect_schema_mismatch(client: MemgraphClient) -> list[tuple[str, str]]:
    """Graph's recorded OntologySchema version differs from this release's."""
    current = await get_schema_version(client)
    if current is not None and current != SCHEMA_VERSION:
        return [(SCHEMA_SINGLETON_ID, LABEL_ONTOLOGY_SCHEMA)]
    return []


async def _detect_missing_semantic_classification(
    hass: HomeAssistant, client: MemgraphClient
) -> list[tuple[str, str]]:
    """HA entities matching at least one classification rule but not yet classified."""
    query = f"MATCH (e:{LABEL_ENTITY})-[:CLASSIFIED_AS]->() RETURN DISTINCT e.ha_id AS ha_id"
    rows = await client.run_query(query, {})
    already_classified = {row["ha_id"] for row in rows}

    registry = er.async_get(hass)
    findings: list[tuple[str, str]] = []
    for entity in registry.entities.values():
        if entity.platform == DOMAIN or entity.entity_id in already_classified:
            continue
        if semantic_classifier.matching_rules(hass, entity.entity_id):
            findings.append((entity.entity_id, LABEL_ENTITY))
    return findings


async def _merge_finding(
    client: MemgraphClient, category: str, target_ha_id: str, target_label: str, severity: str
) -> str:
    finding_ha_id = _finding_ha_id(category, target_ha_id)
    now = datetime.now(UTC).isoformat()
    query = (
        f"MERGE (f:{LABEL_VALIDATION_FINDING} {{ha_id: $finding_ha_id}}) "
        "ON CREATE SET f.first_detected_at = $now "
        "SET f.category = $category, f.severity = $severity, f.status = $status, "
        "f.last_detected_at = $now, f.resolved_at = null, f.source = $source, "
        "f.updated_at = $now "
        f"WITH f MATCH (target:{target_label} {{ha_id: $target_ha_id}}) "
        f"MERGE (f)-[:{REL_RELATES_TO}]->(target)"
    )
    await client.run_query(
        query,
        {
            "finding_ha_id": finding_ha_id,
            "category": category,
            "severity": severity,
            "status": FINDING_STATUS_OPEN,
            "now": now,
            "source": SOURCE_GENERATED,
            "target_label": target_label,
            "target_ha_id": target_ha_id,
        },
    )
    return finding_ha_id


async def _reconcile_category(
    client: MemgraphClient, category: str, detected: list[tuple[str, str]], severity: str
) -> int:
    detected_ids: set[str] = set()
    for target_ha_id, target_label in detected:
        try:
            finding_id = await _merge_finding(
                client, category, target_ha_id, target_label, severity
            )
            detected_ids.add(finding_id)
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Skipping finding merge for %s/%s: target node not found",
                category,
                target_ha_id,
                exc_info=True,
            )

    now = datetime.now(UTC).isoformat()
    # Retention policy (spec.md Assumptions): a resolved finding is only
    # removed after it has remained resolved across one full *subsequent*
    # validation run - never in the same run it transitions to resolved.
    # The `f.resolved_at <> $now` guard on the delete below excludes findings
    # that were just resolved by the SET above (same `now` timestamp), so
    # deletion only ever catches findings resolved in an earlier run.
    delete_query = (
        f"MATCH (f:{LABEL_VALIDATION_FINDING} {{category: $category, status: $resolved}}) "
        "WHERE NOT f.ha_id IN $detected_ids AND f.resolved_at <> $now "
        "DETACH DELETE f"
    )
    await client.run_query(
        delete_query,
        {
            "category": category,
            "resolved": FINDING_STATUS_RESOLVED,
            "detected_ids": list(detected_ids),
            "now": now,
        },
    )
    resolve_query = (
        f"MATCH (f:{LABEL_VALIDATION_FINDING} {{category: $category, status: $open}}) "
        "WHERE NOT f.ha_id IN $detected_ids "
        "SET f.status = $resolved, f.resolved_at = $now, f.updated_at = $now"
    )
    await client.run_query(
        resolve_query,
        {
            "category": category,
            "open": FINDING_STATUS_OPEN,
            "resolved": FINDING_STATUS_RESOLVED,
            "detected_ids": list(detected_ids),
            "now": now,
        },
    )
    return len(detected_ids)


async def async_run_validation(hass: HomeAssistant, client: MemgraphClient) -> dict[str, int]:
    """Run all 9 validation categories and reconcile findings (User Story 5, FR-051-FR-056).

    Returns a dict of open-finding counts by category from this run.
    """
    detections: dict[str, list[tuple[str, str]]] = {
        FINDING_MISSING_AREA: await _detect_missing_area(client),
        FINDING_MISSING_DEVICE: await _detect_missing_device(client),
        FINDING_ORPHAN_ENTITY: await _detect_orphan_entity(client),
        FINDING_ORPHAN_DEVICE: await _detect_orphan_device(client),
        FINDING_DUPLICATE_ENTITY: await _detect_duplicate_entity(client),
        FINDING_UNAVAILABLE_CRITICAL_ENTITY: await _detect_unavailable_critical_entity(
            hass, client
        ),
        FINDING_INVALID_RELATIONSHIP: await _detect_invalid_relationship(client),
        FINDING_SCHEMA_MISMATCH: await _detect_schema_mismatch(client),
        FINDING_MISSING_SEMANTIC_CLASSIFICATION: await _detect_missing_semantic_classification(
            hass, client
        ),
    }

    counts: dict[str, int] = {}
    for category, detected in detections.items():
        counts[category] = await _reconcile_category(
            client, category, detected, _CATEGORY_SEVERITY[category]
        )
    return counts

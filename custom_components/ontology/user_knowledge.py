"""Durable user-managed ontology knowledge.

This module initially owns energy-role assignments for feature 004 User
Story 2. Supply associations and combined import/export belong to later
stories and are intentionally not implemented here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from homeassistant.core import HomeAssistant

from .const import (
    ENERGY_ROLES,
    LABEL_ENERGY_ROLE_ASSIGNMENT,
    LABEL_ENTITY,
    MEASUREMENT_KIND,
    MEASUREMENT_KIND_POWER,
    REL_ASSIGNS_ROLE_TO,
    SOURCE_GENERATED,
    SOURCE_INFERRED,
    SOURCE_USER,
)
from .memgraph_client import MemgraphClient
from .semantic_classifier import infer_energy_role


class EnergyRoleRejected(ValueError):
    """Raised when an energy-role mutation cannot be applied safely."""


def energy_role_assignment_id(source: str, measurement_entity_id: str) -> str:
    """Return the canonical assignment ID for one source/entity pair."""
    return str(
        uuid5(
            NAMESPACE_URL,
            f"home-assistant-ontology:energy-role:{source}:{measurement_entity_id}",
        )
    )


def _validate_role(role: object) -> str:
    if not isinstance(role, str) or role not in ENERGY_ROLES:
        raise EnergyRoleRejected("Invalid energy role")
    return role


async def _resolve_power_entity(client: MemgraphClient, identifier: str) -> str:
    rows = await client.run_query(
        f"MATCH (entity:{LABEL_ENTITY}) "
        "WHERE entity.ha_id = $identifier "
        "OR toLower(coalesce(entity.name, '')) = toLower($identifier) "
        "RETURN entity.ha_id AS entity_id, entity.name AS name, "
        f"entity.{MEASUREMENT_KIND} AS measurement_kind "
        "ORDER BY CASE WHEN entity.ha_id = $identifier THEN 0 ELSE 1 END, "
        "toLower(coalesce(entity.name, '')), entity.ha_id "
        "LIMIT 3",
        {"identifier": identifier},
    )
    exact = [row for row in rows if row.get("entity_id") == identifier]
    candidates = exact or rows
    if not candidates:
        raise EnergyRoleRejected("Power measurement entity not found")
    if len(candidates) > 1:
        raise EnergyRoleRejected("Power measurement entity is ambiguous")
    candidate = candidates[0]
    if candidate.get("measurement_kind") != MEASUREMENT_KIND_POWER:
        raise EnergyRoleRejected("Entity is not a power measurement")
    return str(candidate["entity_id"])


async def async_set_energy_role(
    client: MemgraphClient,
    entity: str,
    role: object,
) -> dict[str, Any]:
    """Upsert a user role and return the resulting effective assignment."""
    validated_role = _validate_role(role)
    entity_id = await _resolve_power_entity(client, entity)
    assignment_id = energy_role_assignment_id(SOURCE_USER, entity_id)
    now = datetime.now(UTC).isoformat()
    rows = await client.run_query(
        f"MATCH (entity:{LABEL_ENTITY} {{ha_id: $entity_id}}) "
        f"MERGE (assignment:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        "{ha_id: $assignment_id}) "
        "ON CREATE SET assignment.created_at = $now "
        "SET assignment.measurement_entity_id = $entity_id, "
        "assignment.role = $role, assignment.source = $source, "
        "assignment.updated_at = $now "
        f"MERGE (assignment)-[binding:{REL_ASSIGNS_ROLE_TO}]->(entity) "
        "SET binding.source = $binding_source "
        "RETURN assignment.ha_id AS assignment_id, entity.ha_id AS entity_id, "
        "assignment.role AS role, assignment.source AS source, "
        "assignment.role AS effective_role, assignment.source AS effective_source",
        {
            "assignment_id": assignment_id,
            "entity_id": entity_id,
            "role": validated_role,
            "source": SOURCE_USER,
            "binding_source": "generated",
            "now": now,
        },
    )
    if not rows:
        raise EnergyRoleRejected("Power measurement entity no longer exists")
    return dict(rows[0])


async def async_delete_user_energy_role(
    client: MemgraphClient, entity: str
) -> dict[str, Any]:
    """Delete only the user assignment and expose any inferred fallback."""
    entity_id = await _resolve_power_entity(client, entity)
    rows = await client.run_query(
        f"MATCH (assignment:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        "{ha_id: $assignment_id, source: $source}) "
        "WITH assignment, assignment.measurement_entity_id AS entity_id "
        "DETACH DELETE assignment "
        f"OPTIONAL MATCH (inferred:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        "{measurement_entity_id: entity_id, source: $inferred_source}) "
        "RETURN 1 AS deleted, entity_id, inferred.role AS effective_role, "
        "inferred.source AS effective_source",
        {
            "assignment_id": energy_role_assignment_id(SOURCE_USER, entity_id),
            "source": SOURCE_USER,
            "inferred_source": SOURCE_INFERRED,
        },
    )
    if not rows:
        return {
            "deleted": False,
            "entity_id": entity_id,
            "effective_role": None,
            "effective_source": None,
        }
    row = rows[0]
    return {
        "deleted": bool(row.get("deleted")),
        "entity_id": row.get("entity_id") or entity_id,
        "effective_role": row.get("effective_role"),
        "effective_source": row.get("effective_source"),
    }


async def _upsert_inferred_energy_role(
    client: MemgraphClient, entity_id: str, role: str
) -> None:
    now = datetime.now(UTC).isoformat()
    await client.run_query(
        f"MATCH (entity:{LABEL_ENTITY} {{ha_id: $entity_id}}) "
        f"MERGE (assignment:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
        "{ha_id: $assignment_id}) "
        "ON CREATE SET assignment.created_at = $now "
        "SET assignment.measurement_entity_id = $entity_id, "
        "assignment.role = $role, assignment.source = $source, "
        "assignment.updated_at = $now "
        f"MERGE (assignment)-[binding:{REL_ASSIGNS_ROLE_TO}]->(entity) "
        "SET binding.source = $binding_source",
        {
            "assignment_id": energy_role_assignment_id(SOURCE_INFERRED, entity_id),
            "entity_id": entity_id,
            "role": role,
            "source": SOURCE_INFERRED,
            "binding_source": SOURCE_GENERATED,
            "now": now,
        },
    )


async def async_repair_energy_role_bindings(client: MemgraphClient) -> None:
    """Recreate generated bindings while retaining unresolved statements."""
    await client.run_query(
        f"MATCH (assignment:{LABEL_ENERGY_ROLE_ASSIGNMENT}) "
        f"OPTIONAL MATCH (assignment)-[binding:{REL_ASSIGNS_ROLE_TO}]->() "
        "DELETE binding "
        "WITH DISTINCT assignment "
        f"MATCH (entity:{LABEL_ENTITY} "
        "{ha_id: assignment.measurement_entity_id}) "
        f"MERGE (assignment)-[binding:{REL_ASSIGNS_ROLE_TO}]->(entity) "
        "SET binding.source = $binding_source",
        {"binding_source": SOURCE_GENERATED},
    )


async def async_reconcile_energy_roles(
    hass: HomeAssistant,
    client: MemgraphClient,
    entity_id: str | None = None,
) -> int:
    """Refresh inferred statements and repair all effective-role bindings."""
    if entity_id is None:
        entity_ids = sorted(state.entity_id for state in hass.states.async_all())
    else:
        entity_ids = [entity_id]

    inferred_count = 0
    for candidate_id in entity_ids:
        role = infer_energy_role(hass, candidate_id)
        if role is None:
            await client.run_query(
                f"MATCH (assignment:{LABEL_ENERGY_ROLE_ASSIGNMENT} "
                "{ha_id: $assignment_id, source: $source}) "
                "DETACH DELETE assignment",
                {
                    "assignment_id": energy_role_assignment_id(
                        SOURCE_INFERRED, candidate_id
                    ),
                    "source": SOURCE_INFERRED,
                },
            )
            continue
        await _upsert_inferred_energy_role(client, candidate_id, role)
        inferred_count += 1

    await async_repair_energy_role_bindings(client)
    return inferred_count
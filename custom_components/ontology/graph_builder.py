"""Maps Home Assistant registries to idempotent MERGE Cypher writes.

All writes go through :func:`merge_node` / :func:`merge_relationship`, which
always ``MERGE`` on the node's ``ha_id`` (Constitution Principle III/VI,
data-model.md "Common conventions") and stamp ``source``/``updated_at``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import label_registry as lr

from .const import (
    AUTOMATION_DOMAIN,
    HOME_SINGLETON_ID,
    LABEL_AREA,
    LABEL_AUTOMATION,
    LABEL_DEVICE,
    LABEL_DOMAIN,
    LABEL_ENTITY,
    LABEL_FLOOR,
    LABEL_HOME,
    LABEL_INTEGRATION,
    LABEL_LABEL,
    LABEL_ONTOLOGY_SCHEMA,
    LABEL_SCENE,
    LABEL_SCRIPT,
    REL_CONTROLS,
    REL_HAS_AREA,
    REL_HAS_DEVICE,
    REL_HAS_ENTITY,
    REL_HAS_FLOOR,
    REL_HAS_LABEL,
    REL_IN_DOMAIN,
    REL_ON_FLOOR,
    REL_PROVIDED_BY,
    REL_REFERENCES,
    SCENE_DOMAIN,
    SCHEMA_SINGLETON_ID,
    SCHEMA_VERSION,
    SCRIPT_DOMAIN,
    SOURCE_GENERATED,
    SOURCE_HOME_ASSISTANT,
)
from .memgraph_client import MemgraphClient

_LOGGER = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sanitize_label(label: str) -> str:
    """Guard against label/relationship-type injection.

    Labels and relationship types cannot be parameterized in Cypher, so they
    are restricted to a safe identifier charset before being interpolated
    into a query string.
    """
    if not label.replace("_", "").isalnum():
        raise ValueError(f"Unsafe Cypher label/type: {label!r}")
    return label


async def merge_node(
    client: MemgraphClient,
    label: str,
    ha_id: str,
    properties: dict[str, Any] | None = None,
    source: str = SOURCE_HOME_ASSISTANT,
) -> None:
    """Idempotently create/update a node, keyed on ``ha_id`` within ``label``."""
    label = _sanitize_label(label)
    props = dict(properties or {})
    props["source"] = source
    props["updated_at"] = _now_iso()
    query = (
        f"MERGE (n:{label} {{ha_id: $ha_id}}) "
        "SET n += $properties"
    )
    await client.run_query_with_retry(query, {"ha_id": ha_id, "properties": props})


async def merge_relationship(
    client: MemgraphClient,
    from_label: str,
    from_ha_id: str,
    rel_type: str,
    to_label: str,
    to_ha_id: str,
    source: str = SOURCE_HOME_ASSISTANT,
) -> None:
    """Idempotently create/update a relationship between two existing nodes."""
    from_label = _sanitize_label(from_label)
    to_label = _sanitize_label(to_label)
    rel_type = _sanitize_label(rel_type)
    query = (
        f"MATCH (a:{from_label} {{ha_id: $from_ha_id}}), "
        f"(b:{to_label} {{ha_id: $to_ha_id}}) "
        f"MERGE (a)-[r:{rel_type}]->(b) "
        "SET r.source = $source, r.updated_at = $updated_at"
    )
    await client.run_query_with_retry(
        query,
        {
            "from_ha_id": from_ha_id,
            "to_ha_id": to_ha_id,
            "source": source,
            "updated_at": _now_iso(),
        },
    )


# ---------------------------------------------------------------------------
# Discovery (User Story 3): read HA registries, write nodes/relationships.
# Every optional relationship (Area<->Floor, Device<->Area, Entity<->Device,
# Entity<->Label, Entity<->Integration) is skipped, not raised, when the
# underlying registry data is missing (FR-006).
# ---------------------------------------------------------------------------


async def ensure_home_node(client: MemgraphClient) -> None:
    """Create/update the singleton Home node (root of the hierarchy)."""
    await merge_node(client, LABEL_HOME, HOME_SINGLETON_ID, {"name": "Home"})


async def collect_floors(hass: HomeAssistant, client: MemgraphClient) -> list[str]:
    """Discover HA floors (optional registry, FR-006). Returns discovered ids."""
    registry = fr.async_get(hass)
    floor_ids: list[str] = []
    for floor in registry.async_list_floors():
        await merge_node(
            client,
            LABEL_FLOOR,
            floor.floor_id,
            {"name": floor.name, "level": floor.level, "icon": floor.icon},
        )
        await merge_relationship(
            client, LABEL_HOME, HOME_SINGLETON_ID, REL_HAS_FLOOR, LABEL_FLOOR, floor.floor_id
        )
        floor_ids.append(floor.floor_id)
    return floor_ids


async def collect_areas(hass: HomeAssistant, client: MemgraphClient) -> list[str]:
    """Discover HA areas; may exist with no floor (FR-006). Returns discovered ids."""
    registry = ar.async_get(hass)
    area_ids: list[str] = []
    for area in registry.async_list_areas():
        await merge_node(client, LABEL_AREA, area.id, {"name": area.name, "icon": area.icon})
        await merge_relationship(
            client, LABEL_HOME, HOME_SINGLETON_ID, REL_HAS_AREA, LABEL_AREA, area.id
        )
        floor_id = getattr(area, "floor_id", None)
        if floor_id:
            await merge_relationship(
                client, LABEL_AREA, area.id, REL_ON_FLOOR, LABEL_FLOOR, floor_id
            )
        else:
            _LOGGER.debug("Area %s has no floor assigned; skipping ON_FLOOR", area.id)
        area_ids.append(area.id)
    return area_ids


async def collect_devices(hass: HomeAssistant, client: MemgraphClient) -> list[str]:
    """Discover HA devices; may exist with no area (FR-006). Returns discovered ids."""
    registry = dr.async_get(hass)
    device_ids: list[str] = []
    for device in registry.devices.values():
        name = device.name_by_user or device.name
        await merge_node(
            client,
            LABEL_DEVICE,
            device.id,
            {"name": name, "manufacturer": device.manufacturer, "model": device.model},
        )
        if device.area_id:
            await merge_relationship(
                client, LABEL_AREA, device.area_id, REL_HAS_DEVICE, LABEL_DEVICE, device.id
            )
        else:
            _LOGGER.debug("Device %s has no area assigned; skipping HAS_DEVICE", device.id)
        device_ids.append(device.id)
    return device_ids


async def collect_labels(hass: HomeAssistant, client: MemgraphClient) -> list[str]:
    """Discover HA labels (optional registry, FR-006). Returns discovered ids."""
    registry = lr.async_get(hass)
    label_ids: list[str] = []
    for label in registry.async_list_labels():
        await merge_node(
            client, LABEL_LABEL, label.label_id, {"name": label.name, "color": label.color}
        )
        label_ids.append(label.label_id)
    return label_ids


async def collect_entities(
    hass: HomeAssistant, client: MemgraphClient
) -> tuple[list[str], set[str], set[str]]:
    """Discover HA entities.

    May exist with no device (directly-provided entities, FR-006); always
    links to exactly one Domain; links to Integration/Label only when known.
    Returns (entity_ids, discovered_domains, discovered_integrations).
    """
    registry = er.async_get(hass)
    entity_ids: list[str] = []
    domains: set[str] = set()
    integrations: set[str] = set()
    for entity in registry.entities.values():
        await _write_entity_node_and_relationships(hass, client, entity.entity_id)
        domains.add(entity.entity_id.split(".", 1)[0])
        if entity.platform:
            integrations.add(entity.platform)
        entity_ids.append(entity.entity_id)
    return entity_ids, domains, integrations


async def _write_entity_node_and_relationships(
    hass: HomeAssistant, client: MemgraphClient, entity_id: str
) -> None:
    """Write the Entity node and its Device/Domain/Integration/Label edges."""
    registry = er.async_get(hass)
    entry = registry.entities.get(entity_id)
    state = hass.states.get(entity_id)
    name = (entry.name if entry else None) or (state.name if state else None) or entity_id
    domain = entity_id.split(".", 1)[0]

    props: dict[str, Any] = {"name": name}
    if state is not None:
        props["state"] = state.state
        props["state_updated_at"] = state.last_changed.isoformat()

    await merge_node(client, LABEL_ENTITY, entity_id, props)
    await merge_node(client, LABEL_DOMAIN, domain, {})
    await merge_relationship(client, LABEL_ENTITY, entity_id, REL_IN_DOMAIN, LABEL_DOMAIN, domain)

    if entry is None:
        return

    if entry.device_id:
        await merge_relationship(
            client, LABEL_DEVICE, entry.device_id, REL_HAS_ENTITY, LABEL_ENTITY, entity_id
        )
    else:
        _LOGGER.debug("Entity %s has no device; skipping HAS_ENTITY", entity_id)

    if entry.platform:
        await merge_node(client, LABEL_INTEGRATION, entry.platform, {"name": entry.platform})
        await merge_relationship(
            client, LABEL_ENTITY, entity_id, REL_PROVIDED_BY, LABEL_INTEGRATION, entry.platform
        )
    else:
        _LOGGER.debug("Entity %s has no known source integration; skipping PROVIDED_BY", entity_id)

    for label_id in entry.labels or ():
        await merge_relationship(
            client, LABEL_ENTITY, entity_id, REL_HAS_LABEL, LABEL_LABEL, label_id
        )


def _referenced_entity_ids(hass: HomeAssistant, entity_id: str) -> list[str]:
    """Best-effort extraction of entities referenced by an automation/scene/
    script, from its current state attributes (data-model.md, US3)."""
    state = hass.states.get(entity_id)
    if state is None:
        return []
    referenced = state.attributes.get("entity_id", [])
    if isinstance(referenced, str):
        return [referenced]
    return list(referenced)


async def _collect_referencing_domain(
    hass: HomeAssistant,
    client: MemgraphClient,
    domain: str,
    label: str,
    rel_type: str,
) -> list[str]:
    """Shared implementation for collect_automations/collect_scenes/collect_scripts."""
    node_ids: list[str] = []
    for state in hass.states.async_all(domain):
        name = state.attributes.get("friendly_name", state.entity_id)
        await merge_node(client, label, state.entity_id, {"name": name})
        for referenced_id in _referenced_entity_ids(hass, state.entity_id):
            await merge_relationship(
                client, label, state.entity_id, rel_type, LABEL_ENTITY, referenced_id
            )
        node_ids.append(state.entity_id)
    return node_ids


async def collect_automations(hass: HomeAssistant, client: MemgraphClient) -> list[str]:
    """Discover automation entities and their best-effort referenced entities."""
    return await _collect_referencing_domain(
        hass, client, AUTOMATION_DOMAIN, LABEL_AUTOMATION, REL_REFERENCES
    )


async def collect_scenes(hass: HomeAssistant, client: MemgraphClient) -> list[str]:
    """Discover scene entities and the entities they control."""
    return await _collect_referencing_domain(hass, client, SCENE_DOMAIN, LABEL_SCENE, REL_CONTROLS)


async def collect_scripts(hass: HomeAssistant, client: MemgraphClient) -> list[str]:
    """Discover script entities and their best-effort referenced entities."""
    return await _collect_referencing_domain(
        hass, client, SCRIPT_DOMAIN, LABEL_SCRIPT, REL_REFERENCES
    )


async def collect_domains(client: MemgraphClient, domains: set[str]) -> None:
    """Write a Domain node for every domain discovered among entities."""
    for domain in domains:
        await merge_node(client, LABEL_DOMAIN, domain, {})


async def collect_integrations(client: MemgraphClient, integrations: set[str]) -> None:
    """Write an Integration node for every source integration discovered among entities."""
    for integration in integrations:
        await merge_node(client, LABEL_INTEGRATION, integration, {"name": integration})


# ---------------------------------------------------------------------------
# Full-graph orchestration (User Story 4)
# ---------------------------------------------------------------------------


async def build_full_graph(hass: HomeAssistant, client: MemgraphClient) -> dict[str, Any]:
    """Run all discovery `collect_*` functions and write the full ontology.

    Idempotent: safe to call repeatedly (data-model.md, Constitution Principle
    III/VI) since every write is a `MERGE` keyed on `ha_id`.
    """
    await ensure_home_node(client)
    await collect_floors(hass, client)
    await collect_areas(hass, client)
    await collect_devices(hass, client)
    await collect_labels(hass, client)
    entity_ids, domains, integrations = await collect_entities(hass, client)
    await collect_domains(client, domains)
    await collect_integrations(client, integrations)
    automation_ids = await collect_automations(hass, client)
    scene_ids = await collect_scenes(hass, client)
    script_ids = await collect_scripts(hass, client)
    await ensure_schema_node(client)

    return {
        "entities": len(entity_ids),
        "domains": len(domains),
        "integrations": len(integrations),
        "automations": len(automation_ids),
        "scenes": len(scene_ids),
        "scripts": len(script_ids),
    }


async def ensure_schema_node(client: MemgraphClient) -> None:
    """Create the OntologySchema singleton on first sync (Constitution Principle VI).

    Never silently rewritten afterwards — schema-version mismatch handling
    (User Story 8) reads this node but does not touch it here.
    """
    query = (
        f"MERGE (s:{LABEL_ONTOLOGY_SCHEMA} {{ha_id: $ha_id}}) "
        "ON CREATE SET s.version = $version, s.updated_at = $updated_at"
    )
    await client.run_query_with_retry(
        query,
        {
            "ha_id": SCHEMA_SINGLETON_ID,
            "version": SCHEMA_VERSION,
            "updated_at": _now_iso(),
        },
    )


async def get_schema_version(client: MemgraphClient) -> str | None:
    """Read the recorded `OntologySchema.version`, or `None` if not yet created."""
    query = f"MATCH (s:{LABEL_ONTOLOGY_SCHEMA} {{ha_id: $ha_id}}) RETURN s.version AS version"
    rows = await client.run_query(query, {"ha_id": SCHEMA_SINGLETON_ID})
    if not rows:
        return None
    return rows[0]["version"]


async def clear_generated_graph(client: MemgraphClient) -> None:
    """Delete only nodes/relationships this integration owns (FR-017a).

    Never deletes anything with `source = "user"` or `source = "inferred"`;
    the `OntologySchema` node is intentionally left untouched.
    """
    query = (
        "MATCH (n) "
        f"WHERE n.source IN [$home_assistant, $generated] AND NOT n:{LABEL_ONTOLOGY_SCHEMA} "
        "DETACH DELETE n"
    )
    await client.run_query_with_retry(
        query, {"home_assistant": SOURCE_HOME_ASSISTANT, "generated": SOURCE_GENERATED}
    )


# ---------------------------------------------------------------------------
# Single-element updates (User Story 5)
# ---------------------------------------------------------------------------


async def update_entity(hass: HomeAssistant, client: MemgraphClient, entity_id: str) -> None:
    """MERGE only the affected Entity node and its direct relationships.

    If the entity no longer exists in HA (deleted mid-flight), treat it as a
    removal rather than raising (edge case, spec.md Edge Cases / T045a).
    """
    registry = er.async_get(hass)
    if registry.entities.get(entity_id) is None and hass.states.get(entity_id) is None:
        await _delete_node(client, LABEL_ENTITY, entity_id)
        return
    await _write_entity_node_and_relationships(hass, client, entity_id)


async def update_device(hass: HomeAssistant, client: MemgraphClient, device_id: str) -> None:
    """MERGE only the affected Device node and its Area relationship.

    Treats a since-deleted device as a removal (T045a).
    """
    registry = dr.async_get(hass)
    device = registry.devices.get(device_id)
    if device is None:
        await _delete_node(client, LABEL_DEVICE, device_id)
        return
    name = device.name_by_user or device.name
    await merge_node(
        client,
        LABEL_DEVICE,
        device.id,
        {"name": name, "manufacturer": device.manufacturer, "model": device.model},
    )
    if device.area_id:
        await merge_relationship(
            client, LABEL_AREA, device.area_id, REL_HAS_DEVICE, LABEL_DEVICE, device.id
        )


async def update_area(hass: HomeAssistant, client: MemgraphClient, area_id: str) -> None:
    """MERGE only the affected Area node and its Home/Floor relationships.

    Treats a since-deleted area as a removal (T045a).
    """
    registry = ar.async_get(hass)
    area = registry.async_get_area(area_id)
    if area is None:
        await _delete_node(client, LABEL_AREA, area_id)
        return
    await merge_node(client, LABEL_AREA, area.id, {"name": area.name, "icon": area.icon})
    await merge_relationship(
        client, LABEL_HOME, HOME_SINGLETON_ID, REL_HAS_AREA, LABEL_AREA, area.id
    )
    floor_id = getattr(area, "floor_id", None)
    if floor_id:
        await merge_relationship(client, LABEL_AREA, area.id, REL_ON_FLOOR, LABEL_FLOOR, floor_id)


async def _delete_node(client: MemgraphClient, label: str, ha_id: str) -> None:
    """Remove a node (and its relationships) this integration owns, by `ha_id`.

    Only ever targets `home_assistant`/`generated`-sourced nodes, mirroring
    `clear_generated_graph`'s ownership boundary (FR-017a).
    """
    label = _sanitize_label(label)
    query = (
        f"MATCH (n:{label} {{ha_id: $ha_id}}) "
        "WHERE n.source IN [$home_assistant, $generated] "
        "DETACH DELETE n"
    )
    await client.run_query_with_retry(
        query,
        {"ha_id": ha_id, "home_assistant": SOURCE_HOME_ASSISTANT, "generated": SOURCE_GENERATED},
    )


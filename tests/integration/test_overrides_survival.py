"""Integration test: a user-managed relationship survives full
`ontology.resync` and `ontology.rebuild` (User Story 4, T032)."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import overrides
from custom_components.ontology.const import (
    DOMAIN,
    LABEL_ENTITY,
    LABEL_SEMANTIC_TYPE,
    REL_OVERRIDE_OF,
    SOURCE_USER,
)
from custom_components.ontology.coordinator import OntologyCoordinator
from custom_components.ontology.memgraph_client import MemgraphClient

_TYPE_LABEL = "CustomAsset"


async def _override_row(client: MemgraphClient) -> dict | None:
    rows = await client.run_query(
        f"MATCH (e:{LABEL_ENTITY} {{ha_id: 'sensor.override_target'}})"
        f"-[r:{REL_OVERRIDE_OF}]->(t:{LABEL_SEMANTIC_TYPE} {{ha_id: $type_label}}) "
        "RETURN r.source AS source",
        {"type_label": _TYPE_LABEL},
    )
    return rows[0] if rows else None


async def _make_coordinator(hass, memgraph_client: MemgraphClient) -> OntologyCoordinator:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        "override-target-unique-id",
        suggested_object_id="override_target",
    )
    hass.states.async_set("sensor.override_target", "1")
    await hass.async_block_till_done()

    coordinator = OntologyCoordinator(hass, entry, memgraph_client)
    await coordinator._execute_full_sync(clear_first=False)  # initial sync, no clearing
    await overrides.async_create_override(
        memgraph_client, LABEL_ENTITY, "sensor.override_target", _TYPE_LABEL
    )
    assert await _override_row(memgraph_client) is not None
    return coordinator


async def test_user_override_survives_resync(hass, memgraph_client: MemgraphClient) -> None:
    coordinator = await _make_coordinator(hass, memgraph_client)

    await coordinator.async_resync()

    row = await _override_row(memgraph_client)
    assert row is not None
    assert row["source"] == SOURCE_USER


async def test_user_override_survives_rebuild(hass, memgraph_client: MemgraphClient) -> None:
    coordinator = await _make_coordinator(hass, memgraph_client)

    # `ontology.rebuild` clears integration-owned data (which would normally
    # cascade-delete any relationship incident to a deleted Entity node) and
    # rebuilds; preservation of user-managed overrides is unconditional.
    await coordinator.async_rebuild()

    row = await _override_row(memgraph_client)
    assert row is not None
    assert row["source"] == SOURCE_USER

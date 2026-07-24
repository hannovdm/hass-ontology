"""Integration test: classification results (`source = "inferred"`) survive
`ontology.resync` and `ontology.rebuild` (User Story 1, T008)."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er

from custom_components.ontology import graph_builder
from custom_components.ontology.const import (
    LABEL_ENTITY,
    LABEL_GAS_CYLINDER,
    REL_MEASURED_BY,
    SOURCE_INFERRED,
)
from custom_components.ontology.memgraph_client import MemgraphClient


async def _classified_as_gas_cylinder_row(client: MemgraphClient) -> dict | None:
    rows = await client.run_query(
        f"MATCH (t:{LABEL_GAS_CYLINDER})-[r:{REL_MEASURED_BY}]->"
        f"(e:{LABEL_ENTITY} {{ha_id: 'sensor.gas_meter'}}) "
        "RETURN r.source AS source, t.ha_id AS type_ha_id"
    )
    return rows[0] if rows else None


async def test_classification_survives_resync(hass, memgraph_client: MemgraphClient) -> None:
    er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "gas-meter-unique-id", suggested_object_id="gas_meter"
    )
    hass.states.async_set("sensor.gas_meter", "12.5")
    await hass.async_block_till_done()

    await graph_builder.build_full_graph(hass, memgraph_client, auto_classify=True)

    row = await _classified_as_gas_cylinder_row(memgraph_client)
    assert row is not None
    assert row["source"] == SOURCE_INFERRED

    # `ontology.resync` re-reads registries and MERGEs in place without clearing.
    await graph_builder.build_full_graph(hass, memgraph_client, auto_classify=True)

    row_after_resync = await _classified_as_gas_cylinder_row(memgraph_client)
    assert row_after_resync is not None
    assert row_after_resync["source"] == SOURCE_INFERRED
    assert row_after_resync["type_ha_id"] == row["type_ha_id"]


async def test_classification_survives_rebuild(hass, memgraph_client: MemgraphClient) -> None:
    er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "gas-meter-unique-id", suggested_object_id="gas_meter"
    )
    hass.states.async_set("sensor.gas_meter", "12.5")
    await hass.async_block_till_done()

    await graph_builder.build_full_graph(hass, memgraph_client, auto_classify=True)
    assert await _classified_as_gas_cylinder_row(memgraph_client) is not None

    # `ontology.rebuild` clears integration-owned (home_assistant/generated)
    # data first, then rebuilds - classification is `source=inferred` and is
    # regenerated fresh by the rebuild's own classification pass, so it
    # should be present again afterwards, not merely "not deleted".
    await graph_builder.clear_generated_graph(memgraph_client)
    await graph_builder.build_full_graph(hass, memgraph_client, auto_classify=True)

    row_after_rebuild = await _classified_as_gas_cylinder_row(memgraph_client)
    assert row_after_rebuild is not None
    assert row_after_rebuild["source"] == SOURCE_INFERRED

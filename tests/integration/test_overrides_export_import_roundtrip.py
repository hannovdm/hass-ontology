"""Integration test: overrides export -> clear -> import round-trip against
real Memgraph, confirming the restored overrides are identical to what was
exported (User Story 4/7, T049, FR-024)."""

from __future__ import annotations

import pytest

from custom_components.ontology import overrides
from custom_components.ontology.const import LABEL_ENTITY, OVERRIDES_EXPORT_VERSION
from custom_components.ontology.graph_builder import merge_node
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_overrides_export_clear_import_round_trip(memgraph_client: MemgraphClient) -> None:
    await merge_node(memgraph_client, LABEL_ENTITY, "sensor.gas_1", {"name": "Gas Sensor 1"})
    await merge_node(memgraph_client, LABEL_ENTITY, "sensor.gas_2", {"name": "Gas Sensor 2"})

    await overrides.async_create_override(
        memgraph_client, LABEL_ENTITY, "sensor.gas_1", "GasCylinder"
    )
    await overrides.async_create_override(
        memgraph_client, LABEL_ENTITY, "sensor.gas_2", "GasCylinder"
    )

    before = await overrides.async_list_overrides(memgraph_client)
    assert len(before) == 2

    payload = await overrides.async_export_overrides(memgraph_client)

    # Simulate a clear that wipes both override relationships.
    await overrides.async_delete_override(
        memgraph_client, LABEL_ENTITY, "sensor.gas_1", "GasCylinder"
    )
    await overrides.async_delete_override(
        memgraph_client, LABEL_ENTITY, "sensor.gas_2", "GasCylinder"
    )
    assert await overrides.async_list_overrides(memgraph_client) == []

    imported_count = await overrides.async_import_overrides(memgraph_client, payload)
    assert imported_count == 2

    after = await overrides.async_list_overrides(memgraph_client)

    def _key(entry: dict[str, str]) -> tuple[str, str, str]:
        return (entry["source_label"], entry["source_ha_id"], entry["type_label"])

    assert sorted(after, key=_key) == sorted(before, key=_key)


async def test_overrides_import_rejects_malformed_payload_with_no_partial_writes(
    memgraph_client: MemgraphClient,
) -> None:
    await merge_node(memgraph_client, LABEL_ENTITY, "sensor.valid", {"name": "Valid Sensor"})
    payload = {
        "version": OVERRIDES_EXPORT_VERSION,
        "overrides": [
            {
                "relationship_type": "OVERRIDE_OF",
                "source_label": LABEL_ENTITY,
                "source_ha_id": "sensor.valid",
                "type_label": "GasCylinder",
            },
            {
                "relationship_type": "OVERRIDE_OF",
                "source_label": "NotALabel",
                "source_ha_id": "sensor.invalid",
                "type_label": "GasCylinder",
            },
        ],
    }

    with pytest.raises(overrides.OverrideImportRejected):
        await overrides.async_import_overrides(memgraph_client, payload)

    assert await overrides.async_list_overrides(memgraph_client) == []

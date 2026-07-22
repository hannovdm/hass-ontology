"""Integration test: initial full synchronization performance against a real
Memgraph container for a ~500 entity/device fixture (SC-001, T063)."""

from __future__ import annotations

import time

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient

ENTITY_COUNT = 500
AREA_COUNT = 10
DEVICES_PER_AREA = 10
ENTITIES_PER_DEVICE = ENTITY_COUNT // (AREA_COUNT * DEVICES_PER_AREA)

SC_001_TIMEOUT_SECONDS = 5 * 60


async def test_initial_sync_completes_under_five_minutes_for_500_entities(
    hass, memgraph_client: MemgraphClient
) -> None:
    """SC-001: initial full sync of a ~500 entity/device fixture must
    complete in under 5 minutes against a real Memgraph instance."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    area_registry = ar.async_get(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    entity_total = 0
    for area_index in range(AREA_COUNT):
        area = area_registry.async_create(f"Area {area_index}")
        for device_index in range(DEVICES_PER_AREA):
            device = device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"device-{area_index}-{device_index}")},
                name=f"Device {area_index}-{device_index}",
            )
            device_registry.async_update_device(device.id, area_id=area.id)
            for entity_index in range(ENTITIES_PER_DEVICE):
                entity = entity_registry.async_get_or_create(
                    "sensor",
                    "test_platform",
                    f"unique-{area_index}-{device_index}-{entity_index}",
                    device_id=device.id,
                )
                hass.states.async_set(entity.entity_id, "on")
                entity_total += 1

    await hass.async_block_till_done()
    assert entity_total == ENTITY_COUNT

    start = time.monotonic()
    counts = await graph_builder.build_full_graph(hass, memgraph_client)
    elapsed = time.monotonic() - start

    assert counts["entities"] >= ENTITY_COUNT
    assert elapsed < SC_001_TIMEOUT_SECONDS, (
        f"Initial full sync of {ENTITY_COUNT} entities took {elapsed:.1f}s, "
        f"exceeding the SC-001 budget of {SC_001_TIMEOUT_SECONDS}s"
    )

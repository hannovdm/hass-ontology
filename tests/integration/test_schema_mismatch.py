"""Integration test: startup with a mismatched `OntologySchema.version` in
Memgraph fails to load, performs no graph writes, and creates a
`schema_version_mismatch` repair issue (User Story 8, FR-017)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
from testcontainers.core.container import DockerContainer

from custom_components.ontology.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
    ISSUE_SCHEMA_VERSION_MISMATCH,
)
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_schema_mismatch_blocks_setup_and_creates_repair_issue(
    hass, memgraph_client: MemgraphClient, memgraph_container: DockerContainer
) -> None:
    # Pre-seed a schema node with a version that will never match const.SCHEMA_VERSION.
    await memgraph_client.run_query(
        "MERGE (s:OntologySchema {ha_id: 'home_assistant_ontology'}) "
        "SET s.version = '0.0.1-incompatible'"
    )

    host = memgraph_container.get_container_host_ip()
    port = int(memgraph_container.get_exposed_port(7687))
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: host, CONF_PORT: port})
    entry.add_to_hass(hass)

    setup_ok = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert setup_ok is False

    # No graph writes should have occurred: no Area node from a real sync.
    ar.async_get(hass).async_create("Should Not Sync")
    area_rows = await memgraph_client.run_query("MATCH (a:Area) RETURN count(a) AS c")
    assert area_rows[0]["c"] == 0

    issue_id = f"{ISSUE_SCHEMA_VERSION_MISMATCH}_{entry.entry_id}"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None

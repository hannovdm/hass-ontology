"""Integration test: first-run synchronization against a Memgraph instance
that already contains unrelated, non-ontology data only creates/touches the
integration's own `ha_id`-keyed nodes/relationships and leaves the unrelated
data untouched (edge case, spec.md Edge Cases, T062a)."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_first_run_sync_leaves_unrelated_data_untouched(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    # Pre-existing, unrelated data with no `ha_id`/`source` properties at all.
    await memgraph_client.run_query(
        "CREATE (:Person {name: 'Alice'})-[:KNOWS]->(:Person {name: 'Bob'})"
    )

    await graph_builder.build_full_graph(hass, memgraph_client)

    person_rows = await memgraph_client.run_query(
        "MATCH (p:Person) RETURN p.name AS name ORDER BY p.name"
    )
    assert [row["name"] for row in person_rows] == ["Alice", "Bob"]

    knows_rows = await memgraph_client.run_query(
        "MATCH (:Person {name: 'Alice'})-[r:KNOWS]->(:Person {name: 'Bob'}) RETURN count(r) AS c"
    )
    assert knows_rows[0]["c"] == 1

    home_rows = await memgraph_client.run_query("MATCH (h:Home) RETURN count(h) AS c")
    assert home_rows[0]["c"] == 1


async def test_setup_succeeds_with_no_external_ai_runtime_reachable(
    hass, memgraph_container
) -> None:
    """T070 (FR-031, FR-032, SC-007): `async_setup_entry` never depends on the
    reachability of any external local AI runtime - v3's Assist intents,
    impact analysis, context export, and (disabled-by-default) MCP endpoint
    are all pure Memgraph/HA-registry reads, never callers of any AI runtime.
    Startup succeeds with zero failures attributable to v3 even though
    nothing resembling an "AI runtime" is running anywhere in this test."""
    from custom_components.ontology.const import CONF_HOST, CONF_PORT

    host = memgraph_container.get_container_host_ip()
    port = int(memgraph_container.get_exposed_port(7687))
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: host, CONF_PORT: port})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.value == "loaded"

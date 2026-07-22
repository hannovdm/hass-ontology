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

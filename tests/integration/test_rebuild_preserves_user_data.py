"""Integration test: `ontology.rebuild` (clear_generated_graph + rebuild)
clears only home_assistant/generated-sourced elements, never source="user"
or source="inferred" ones (FR-017a, Constitution Principle V)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_rebuild_preserves_user_and_inferred_data(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    area = ar.async_get(hass).async_create("Garage")
    await graph_builder.build_full_graph(hass, memgraph_client)

    await memgraph_client.run_query(
        "CREATE (:Note {ha_id: 'user-note-1', source: 'user', text: 'manual annotation'})"
    )
    await memgraph_client.run_query(
        "CREATE (:InferredFact {ha_id: 'inferred-1', source: 'inferred', text: 'derived fact'})"
    )

    await graph_builder.clear_generated_graph(memgraph_client)
    await graph_builder.build_full_graph(hass, memgraph_client)

    area_rows = await memgraph_client.run_query(
        "MATCH (a:Area {ha_id: $ha_id}) RETURN count(a) AS c", {"ha_id": area.id}
    )
    assert area_rows[0]["c"] == 1

    user_rows = await memgraph_client.run_query(
        "MATCH (n:Note {ha_id: 'user-note-1'}) RETURN count(n) AS c"
    )
    assert user_rows[0]["c"] == 1

    inferred_rows = await memgraph_client.run_query(
        "MATCH (n:InferredFact {ha_id: 'inferred-1'}) RETURN count(n) AS c"
    )
    assert inferred_rows[0]["c"] == 1

    schema_rows = await memgraph_client.run_query("MATCH (s:OntologySchema) RETURN count(s) AS c")
    assert schema_rows[0]["c"] == 1

"""Integration test: dashboard sync does not fail the overall sync when a
dashboard is unloadable or a card references a deleted entity (T028,
FR-047-FR-050), verified against a real Memgraph instance."""

from __future__ import annotations

from custom_components.ontology import dashboard_sync
from custom_components.ontology.const import (
    LABEL_DASHBOARD,
    LABEL_DASHBOARD_CARD,
    REL_CONTAINS_CARD,
    REL_DISPLAYS_ENTITY,
)
from custom_components.ontology.memgraph_client import MemgraphClient


class _FakeDashboard:
    def __init__(self, config: dict, title: str | None = None, fail: bool = False) -> None:
        self._config = config
        self.config = {"title": title} if title else {}
        self._fail = fail

    async def async_load(self, _force: bool) -> dict:
        if self._fail:
            raise RuntimeError("dashboard failed to load")
        return self._config


async def test_unloadable_dashboard_and_dangling_entity_do_not_fail_sync(
    hass, memgraph_client: MemgraphClient
) -> None:
    class _Lovelace:
        dashboards = {
            "broken": _FakeDashboard(config={}, fail=True),
            "energy": _FakeDashboard(
                config={
                    "views": [
                        {
                            "cards": [
                                {
                                    "type": "entities",
                                    "entities": ["sensor.does_not_exist_in_graph"],
                                }
                            ]
                        }
                    ]
                },
                title="Energy",
            ),
        }

    hass.data["lovelace"] = _Lovelace()

    synced = await dashboard_sync.async_sync_dashboards(hass, memgraph_client)

    # The broken dashboard is skipped; the loadable one still syncs (FR-050).
    assert synced == 1

    dashboard_rows = await memgraph_client.run_query(
        f"MATCH (d:{LABEL_DASHBOARD} {{ha_id: 'energy'}}) RETURN d.title AS title"
    )
    assert dashboard_rows[0]["title"] == "Energy"

    broken_rows = await memgraph_client.run_query(
        f"MATCH (d:{LABEL_DASHBOARD} {{ha_id: 'broken'}}) RETURN count(d) AS c"
    )
    assert broken_rows[0]["c"] == 0

    card_ha_id = "energy::0::0"
    card_rows = await memgraph_client.run_query(
        f"MATCH (c:{LABEL_DASHBOARD_CARD} {{ha_id: $ha_id}}) RETURN count(c) AS c",
        {"ha_id": card_ha_id},
    )
    assert card_rows[0]["c"] == 1

    contains_rows = await memgraph_client.run_query(
        f"MATCH (:{LABEL_DASHBOARD} {{ha_id: 'energy'}})-[r:{REL_CONTAINS_CARD}]->"
        f"(:{LABEL_DASHBOARD_CARD} {{ha_id: $ha_id}}) RETURN count(r) AS c",
        {"ha_id": card_ha_id},
    )
    assert contains_rows[0]["c"] == 1

    # The dangling entity reference produces no DISPLAYS_ENTITY relationship,
    # but the card node itself is preserved (FR-050).
    displays_rows = await memgraph_client.run_query(
        f"MATCH (:{LABEL_DASHBOARD_CARD} {{ha_id: $ha_id}})-[r:{REL_DISPLAYS_ENTITY}]->() "
        "RETURN count(r) AS c",
        {"ha_id": card_ha_id},
    )
    assert displays_rows[0]["c"] == 0

"""Unit tests for `dashboard_sync.py` (T027, FR-047-FR-050): dashboard/card
node+relationship mapping, and best-effort tolerance of unloadable
dashboards and dangling entity references. Uses `mock_memgraph_client` and a
fake in-memory `hass.data["lovelace"].dashboards` collection - no real
Lovelace/Memgraph server."""

from __future__ import annotations

from custom_components.ontology import dashboard_sync
from custom_components.ontology.const import (
    LABEL_DASHBOARD,
    LABEL_DASHBOARD_CARD,
    REL_CONTAINS_CARD,
    REL_DISPLAYS_ENTITY,
)


class _FakeDashboard:
    def __init__(self, config: dict, title: str | None = None, fail: bool = False) -> None:
        self._config = config
        self.config = {"title": title} if title else {}
        self._fail = fail

    async def async_load(self, _force: bool) -> dict:
        if self._fail:
            raise RuntimeError("dashboard failed to load")
        return self._config


def _merge_node_calls(mock_client, label: str) -> list[tuple]:
    return [
        call
        for call in mock_client.run_query_with_retry.call_args_list
        if f"MERGE (n:{label}" in call.args[0]
    ]


def _relationship_calls(mock_client, rel_type: str) -> list[tuple]:
    return [
        call
        for call in mock_client.run_query_with_retry.call_args_list
        if f":{rel_type}]" in call.args[0]
    ]


# ---------------------------------------------------------------------------
# T027: mapping and tolerance
# ---------------------------------------------------------------------------


async def test_no_lovelace_data_returns_zero_without_error(hass, mock_memgraph_client) -> None:
    hass.data.pop("lovelace", None)

    synced = await dashboard_sync.async_sync_dashboards(hass, mock_memgraph_client)

    assert synced == 0
    mock_memgraph_client.run_query_with_retry.assert_not_awaited()


async def test_missing_dashboards_collection_returns_zero(hass, mock_memgraph_client) -> None:
    class _NoDashboardsLovelace:
        pass

    hass.data["lovelace"] = _NoDashboardsLovelace()

    synced = await dashboard_sync.async_sync_dashboards(hass, mock_memgraph_client)

    assert synced == 0


async def test_sync_creates_dashboard_and_card_nodes_with_entity_link(
    hass, mock_memgraph_client
) -> None:
    class _Lovelace:
        dashboards = {
            "energy": _FakeDashboard(
                config={
                    "views": [
                        {
                            "cards": [
                                {"type": "entities", "entities": ["light.lamp"]},
                            ]
                        }
                    ]
                },
                title="Energy",
            )
        }

    hass.data["lovelace"] = _Lovelace()

    synced = await dashboard_sync.async_sync_dashboards(hass, mock_memgraph_client)

    assert synced == 1
    assert _merge_node_calls(mock_memgraph_client, LABEL_DASHBOARD)
    assert _merge_node_calls(mock_memgraph_client, LABEL_DASHBOARD_CARD)
    contains_card = _relationship_calls(mock_memgraph_client, REL_CONTAINS_CARD)
    assert contains_card
    _query, params = contains_card[0].args
    assert params["from_ha_id"] == "energy"
    assert params["to_ha_id"] == dashboard_sync.dashboard_card_ha_id("energy", 0, 0)

    displays_entity = _relationship_calls(mock_memgraph_client, REL_DISPLAYS_ENTITY)
    assert displays_entity
    _query, params = displays_entity[0].args
    assert params["to_ha_id"] == "light.lamp"
    assert params["from_ha_id"] == dashboard_sync.dashboard_card_ha_id("energy", 0, 0)


async def test_unloadable_dashboard_is_skipped_without_failing_others(
    hass, mock_memgraph_client
) -> None:
    class _Lovelace:
        dashboards = {
            "broken": _FakeDashboard(config={}, fail=True),
            "good": _FakeDashboard(config={"views": []}, title="Good"),
        }

    hass.data["lovelace"] = _Lovelace()

    synced = await dashboard_sync.async_sync_dashboards(hass, mock_memgraph_client)

    assert synced == 1
    dashboard_ha_ids = {
        call.args[1]["ha_id"]
        for call in _merge_node_calls(mock_memgraph_client, LABEL_DASHBOARD)
    }
    assert dashboard_ha_ids == {"good"}


async def test_card_with_dangling_entity_reference_is_tolerated(
    hass, mock_memgraph_client
) -> None:
    """A card referencing a deleted/unknown entity doesn't fail the sync
    (FR-050): the DISPLAYS_ENTITY relationship is omitted, the card node and
    dashboard sync count are unaffected."""

    async def run_query_with_retry_side_effect(query, params=None):
        if f":{REL_DISPLAYS_ENTITY}]" in query and params and params.get("to_ha_id") == (
            "light.missing"
        ):
            raise RuntimeError("entity does not exist")
        return []

    mock_memgraph_client.run_query_with_retry.side_effect = run_query_with_retry_side_effect

    class _Lovelace:
        dashboards = {
            "energy": _FakeDashboard(
                config={
                    "views": [
                        {"cards": [{"type": "entities", "entities": ["light.missing"]}]}
                    ]
                },
            )
        }

    hass.data["lovelace"] = _Lovelace()

    synced = await dashboard_sync.async_sync_dashboards(hass, mock_memgraph_client)

    # The write is attempted (and fails) but the exception is swallowed:
    # neither the card node nor the overall dashboard sync are affected.
    assert synced == 1
    assert _merge_node_calls(mock_memgraph_client, LABEL_DASHBOARD_CARD)


async def test_dashboard_sync_error_is_tolerated_without_failing_others(
    hass, mock_memgraph_client
) -> None:
    """If `_sync_one_dashboard` itself raises (e.g. an unexpected write
    failure for one dashboard), the overall sync continues and simply
    doesn't count that dashboard (FR-050)."""

    async def run_query_with_retry_side_effect(query, params=None):
        if f"MERGE (n:{LABEL_DASHBOARD} " in query and params and params.get("ha_id") == "bad":
            raise RuntimeError("write failed")
        return []

    mock_memgraph_client.run_query_with_retry.side_effect = run_query_with_retry_side_effect

    class _Lovelace:
        dashboards = {
            "bad": _FakeDashboard(config={"views": []}),
            "good": _FakeDashboard(config={"views": []}),
        }

    hass.data["lovelace"] = _Lovelace()

    synced = await dashboard_sync.async_sync_dashboards(hass, mock_memgraph_client)

    assert synced == 1


def test_dashboard_card_ha_id_is_stable_and_positional() -> None:
    assert dashboard_sync.dashboard_card_ha_id("energy", 0, 2) == "energy::0::2"


def test_card_entity_ids_extracts_single_and_list_and_dict_forms() -> None:
    card = {
        "entity": "light.a",
        "entities": ["light.b", {"entity": "light.c"}, {"not_entity": "ignored"}],
    }

    assert dashboard_sync._card_entity_ids(card) == ["light.a", "light.b", "light.c"]


def test_iter_cards_flattens_views_and_cards_with_index() -> None:
    config = {
        "views": [
            {"cards": [{"type": "a"}, {"type": "b"}]},
            {"cards": [{"type": "c"}]},
        ]
    }

    result = dashboard_sync._iter_cards(config)

    assert [(v, c, card["type"]) for v, c, card in result] == [
        (0, 0, "a"),
        (0, 1, "b"),
        (1, 0, "c"),
    ]

"""Best-effort Lovelace dashboard/card synchronization (FR-047-FR-050).

Reads dashboard/card structure from ``hass.data["lovelace"]`` (research.md
§8) and writes ``Dashboard``/``DashboardCard`` nodes tagged
``source = SOURCE_GENERATED``. Tolerates unloadable dashboards or dangling
entity references without failing the overall sync (FR-050).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    LABEL_DASHBOARD,
    LABEL_DASHBOARD_CARD,
    LABEL_ENTITY,
    REL_CONTAINS_CARD,
    REL_DISPLAYS_ENTITY,
    SOURCE_GENERATED,
)
from .graph_builder import merge_node, merge_relationship
from .memgraph_client import MemgraphClient

_LOGGER = logging.getLogger(__name__)


def dashboard_card_ha_id(dashboard_ha_id: str, view_index: int, card_index: int) -> str:
    """Stable positional card id (data-model.md `"<dashboard>::<view>::<card>"`)."""
    return f"{dashboard_ha_id}::{view_index}::{card_index}"


def _iter_cards(config: dict[str, Any]) -> list[tuple[int, int, dict[str, Any]]]:
    """Flatten a Lovelace dashboard config's views into (view_i, card_i, card)."""
    cards: list[tuple[int, int, dict[str, Any]]] = []
    for view_index, view in enumerate(config.get("views") or []):
        for card_index, card in enumerate(view.get("cards") or []):
            cards.append((view_index, card_index, card))
    return cards


def _card_entity_ids(card: dict[str, Any]) -> list[str]:
    """Best-effort extraction of entity ids referenced by one card's config."""
    entity_ids: list[str] = []
    single = card.get("entity")
    if isinstance(single, str):
        entity_ids.append(single)
    for entry in card.get("entities") or []:
        if isinstance(entry, str):
            entity_ids.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("entity"), str):
            entity_ids.append(entry["entity"])
    return entity_ids


async def _sync_one_dashboard(
    client: MemgraphClient, dashboard_ha_id: str, title: str | None, config: dict[str, Any]
) -> None:
    await merge_node(
        client,
        LABEL_DASHBOARD,
        dashboard_ha_id,
        {"title": title} if title else {},
        source=SOURCE_GENERATED,
    )
    for view_index, card_index, card in _iter_cards(config):
        card_ha_id = dashboard_card_ha_id(dashboard_ha_id, view_index, card_index)
        await merge_node(
            client,
            LABEL_DASHBOARD_CARD,
            card_ha_id,
            {"card_type": card.get("type")},
            source=SOURCE_GENERATED,
        )
        await merge_relationship(
            client,
            LABEL_DASHBOARD,
            dashboard_ha_id,
            REL_CONTAINS_CARD,
            LABEL_DASHBOARD_CARD,
            card_ha_id,
            source=SOURCE_GENERATED,
        )
        for entity_id in _card_entity_ids(card):
            try:
                await merge_relationship(
                    client,
                    LABEL_DASHBOARD_CARD,
                    card_ha_id,
                    REL_DISPLAYS_ENTITY,
                    LABEL_ENTITY,
                    entity_id,
                    source=SOURCE_GENERATED,
                )
            except Exception:  # noqa: BLE001
                # Card references a deleted/unknown entity (FR-050): the
                # DISPLAYS_ENTITY relationship is simply omitted, the card
                # node itself is preserved.
                _LOGGER.debug(
                    "Skipping DISPLAYS_ENTITY for unknown entity %s on card %s",
                    entity_id,
                    card_ha_id,
                )


async def async_sync_dashboards(hass: HomeAssistant, client: MemgraphClient) -> int:
    """Best-effort sync of every loadable Lovelace dashboard (FR-047-FR-050).

    Returns the number of dashboards successfully synced. Any dashboard
    whose config fails to load, or whose collection is entirely absent, is
    skipped without raising (FR-050) - Lovelace's in-memory structures are
    not a hard dependency of the integration.
    """
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return 0

    dashboards_collection = getattr(lovelace, "dashboards", None)
    if dashboards_collection is None:
        return 0

    synced = 0
    for dashboard_ha_id, dashboard in dict(dashboards_collection).items():
        key = dashboard_ha_id if isinstance(dashboard_ha_id, str) else "lovelace"
        try:
            config = await dashboard.async_load(False)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Skipping unloadable dashboard %s", key, exc_info=True)
            continue
        title = getattr(getattr(dashboard, "config", None), "get", lambda *_: None)("title")
        try:
            await _sync_one_dashboard(client, key, title, config)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Skipping dashboard %s due to sync error", key, exc_info=True)
            continue
        synced += 1
    return synced

"""Backend API for the ontology explorer (User Story 3).

Registers the read-only ``ontology/area_context``, ``ontology/entity_context``,
and ``ontology/search`` ``websocket_api`` commands (contracts/websocket-api.md).
None of these commands accept or execute Cypher, and none mutate graph or
Home Assistant state.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_SEARCH_LIMIT,
    DOMAIN,
    LABEL_AREA,
    LABEL_DEVICE,
    LABEL_ENTITY,
    MAX_QUERY_LIMIT,
    REL_CLASSIFIED_AS,
    REL_DISPLAYS_ENTITY,
    REL_HAS_AREA,
    REL_HAS_DEVICE,
    REL_HAS_ENTITY,
    REL_REFERENCES,
    WS_TYPE_AREA_CONTEXT,
    WS_TYPE_ENTITY_CONTEXT,
    WS_TYPE_SEARCH,
)
from .memgraph_client import MemgraphClient

_LOGGER = logging.getLogger(__name__)


def _first_loaded_client(hass: HomeAssistant) -> MemgraphClient | None:
    """Return the Memgraph client of the first loaded Ontology config entry.

    Mirrors `__init__._loaded_coordinators` without importing `__init__`
    (which would create a circular import, since `__init__` registers these
    websocket commands).
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and entry.runtime_data is not None:
            return entry.runtime_data.memgraph_client
    return None


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_AREA_CONTEXT,
        vol.Required("area_id"): str,
    }
)
@websocket_api.async_response
async def _handle_area_context(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return an Area plus its Devices/Entities, states, and classifications (FR-031)."""
    client = _first_loaded_client(hass)
    if client is None:
        connection.send_error(msg["id"], "not_found", "No loaded Ontology config entry")
        return

    area_id = msg["area_id"]
    query = (
        f"MATCH (a:{LABEL_AREA} {{ha_id: $area_id}}) "
        f"OPTIONAL MATCH (a)-[:{REL_HAS_DEVICE}]->(d:{LABEL_DEVICE}) "
        f"OPTIONAL MATCH (d)-[:{REL_HAS_ENTITY}]->(e1:{LABEL_ENTITY}) "
        f"OPTIONAL MATCH (a)<-[:{REL_HAS_AREA}]-(e2:{LABEL_ENTITY}) "
        "WITH a, collect(DISTINCT d) AS devices, "
        "collect(DISTINCT e1) + collect(DISTINCT e2) AS raw_entities "
        "UNWIND (CASE WHEN size(raw_entities) = 0 THEN [null] ELSE raw_entities END) AS entity "
        f"OPTIONAL MATCH (entity)-[:{REL_CLASSIFIED_AS}]->(st) "
        "RETURN a, devices, "
        "collect(DISTINCT {entity: entity, semantic_types: collect(DISTINCT st.ha_id)}) AS entities"
    )
    rows = await client.run_query(query, {"area_id": area_id})
    if not rows or rows[0].get("a") is None:
        connection.send_error(msg["id"], "not_found", f"Area {area_id} not found")
        return

    row = rows[0]
    entities = []
    for item in row.get("entities") or []:
        entity = item.get("entity")
        if entity is None:
            continue
        entity_id = entity.get("ha_id")
        state = hass.states.get(entity_id)
        entities.append(
            {
                "entity": dict(entity),
                "state": state.state if state is not None else None,
                "semantic_types": [t for t in item.get("semantic_types") or [] if t],
            }
        )

    connection.send_result(
        msg["id"],
        {
            "area": dict(row["a"]),
            "devices": [dict(d) for d in row.get("devices") or []],
            "entities": entities,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ENTITY_CONTEXT,
        vol.Required("entity_id"): str,
    }
)
@websocket_api.async_response
async def _handle_entity_context(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return an Entity plus Device/Area/classifications/dependents/cards (FR-032)."""
    client = _first_loaded_client(hass)
    if client is None:
        connection.send_error(msg["id"], "not_found", "No loaded Ontology config entry")
        return

    entity_id = msg["entity_id"]
    query = (
        f"MATCH (e:{LABEL_ENTITY} {{ha_id: $entity_id}}) "
        f"OPTIONAL MATCH (d:{LABEL_DEVICE})-[:{REL_HAS_ENTITY}]->(e) "
        f"OPTIONAL MATCH (a:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(d) "
        f"OPTIONAL MATCH (a2:{LABEL_AREA})-[:{REL_HAS_AREA}]->(e) "
        f"OPTIONAL MATCH (e)-[:{REL_CLASSIFIED_AS}]->(st) "
        f"OPTIONAL MATCH (dependent)-[:{REL_REFERENCES}]->(e) "
        f"OPTIONAL MATCH (card)-[:{REL_DISPLAYS_ENTITY}]->(e) "
        "RETURN e, d, coalesce(a, a2) AS area, "
        "collect(DISTINCT st.ha_id) AS semantic_types, "
        "collect(DISTINCT dependent) AS dependents, "
        "collect(DISTINCT card) AS cards"
    )
    rows = await client.run_query(query, {"entity_id": entity_id})
    if not rows or rows[0].get("e") is None:
        connection.send_error(msg["id"], "not_found", f"Entity {entity_id} not found")
        return

    row = rows[0]
    state = hass.states.get(entity_id)
    connection.send_result(
        msg["id"],
        {
            "entity": dict(row["e"]),
            "state": state.state if state is not None else None,
            "device": dict(row["d"]) if row.get("d") is not None else None,
            "area": dict(row["area"]) if row.get("area") is not None else None,
            "semantic_types": [t for t in row.get("semantic_types") or [] if t],
            "dependents": [dict(x) for x in row.get("dependents") or [] if x is not None],
            "cards": [dict(x) for x in row.get("cards") or [] if x is not None],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_SEARCH,
        vol.Required("query"): str,
        vol.Optional("limit"): int,
    }
)
@websocket_api.async_response
async def _handle_search(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Free-text substring search across Area/Device/Entity name/id (FR-033)."""
    client = _first_loaded_client(hass)
    if client is None:
        connection.send_error(msg["id"], "not_found", "No loaded Ontology config entry")
        return

    term = msg["query"]
    limit = min(msg.get("limit") or DEFAULT_SEARCH_LIMIT, MAX_QUERY_LIMIT)
    query = (
        f"MATCH (n) WHERE (n:{LABEL_AREA} OR n:{LABEL_DEVICE} OR n:{LABEL_ENTITY}) "
        "AND (toLower(coalesce(n.name, '')) CONTAINS toLower($term) "
        "OR toLower(n.ha_id) CONTAINS toLower($term)) "
        "RETURN labels(n) AS labels, n AS node"
    )
    rows, truncated = await client.run_query_limited(query, {"term": term}, limit)

    results = []
    for row in rows:
        labels = [
            label for label in row["labels"] if label in (LABEL_AREA, LABEL_DEVICE, LABEL_ENTITY)
        ]
        if not labels:
            continue
        node = dict(row["node"])
        results.append({"type": labels[0], "ha_id": node.get("ha_id"), "name": node.get("name")})

    connection.send_result(msg["id"], {"results": results, "truncated": truncated})


def async_register_commands(hass: HomeAssistant) -> None:
    """Register the ontology explorer's websocket_api commands (T026).

    Safe to call once per loaded config entry: guarded so the commands are
    only registered with Home Assistant's websocket_api the first time.
    """
    if hass.data.setdefault(f"{DOMAIN}_ws_registered", False):
        return
    websocket_api.async_register_command(hass, _handle_area_context)
    websocket_api.async_register_command(hass, _handle_entity_context)
    websocket_api.async_register_command(hass, _handle_search)
    hass.data[f"{DOMAIN}_ws_registered"] = True

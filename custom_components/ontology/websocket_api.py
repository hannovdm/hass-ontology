"""Backend API for the ontology explorer (User Story 3).

Registers the read-only ``ontology/area_context``, ``ontology/entity_context``,
``ontology/search``, ``ontology/graph_snapshot``, ``ontology/graph_search``,
``ontology/graph_detail``, ``ontology/graph_expand``, ``ontology/graph_subscribe``,
and ``ontology/lab_status`` ``websocket_api`` commands (contracts/websocket-api.md).
None of these commands accept or execute Cypher, and none mutate graph or
Home Assistant state.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_SEARCH_LIMIT,
    DOMAIN,
    GRAPH_EXPAND_EDGE_LIMIT,
    GRAPH_EXPAND_EDGE_MAX,
    GRAPH_EXPAND_NODE_LIMIT,
    GRAPH_EXPAND_NODE_MAX,
    GRAPH_INITIAL_NODE_LIMIT,
    GRAPH_INITIAL_REQUEST_MAX,
    GRAPH_SEARCH_LIMIT,
    GRAPH_SEARCH_MAX,
    GRAPH_UPDATE_DEBOUNCE_SECONDS,
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
    WS_TYPE_GRAPH_DETAIL,
    WS_TYPE_GRAPH_EXPAND,
    WS_TYPE_GRAPH_SEARCH,
    WS_TYPE_GRAPH_SNAPSHOT,
    WS_TYPE_GRAPH_SUBSCRIBE,
    WS_TYPE_LAB_STATUS,
    WS_TYPE_SEARCH,
)
from .memgraph_client import MemgraphClient

_LOGGER = logging.getLogger(__name__)
_STABLE_GRAPH_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*:[^\x00-\x20\x7f:][^\x00-\x1f\x7f]{0,510}$")


def _trimmed_search_term(value: Any) -> str:
    """Validate and normalize a bounded graph search term."""
    term = str(value).strip()
    if not 1 <= len(term) <= 256:
        raise vol.Invalid("search term must contain 1-256 characters")
    return term


def _is_stable_graph_id(value: Any) -> bool:
    """Return whether a value follows the public stable graph ID format."""
    return isinstance(value, str) and bool(_STABLE_GRAPH_ID.fullmatch(value))


def _node_properties(node: Any) -> dict[str, Any]:
    """Return graph properties from either a plain or serialized node."""
    if isinstance(node, dict) and "properties" in node and "labels" in node:
        return dict(node["properties"])
    return dict(node)


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


def _first_loaded_gateway(hass: HomeAssistant) -> Any | None:
    """Return the graph gateway of the first loaded Ontology config entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and entry.runtime_data is not None:
            return getattr(entry.runtime_data, "graph_gateway", None)
    return None


def _first_loaded_coordinator(hass: HomeAssistant) -> Any | None:
    """Return the coordinator of the first loaded Ontology config entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and entry.runtime_data is not None:
            return entry.runtime_data
    return None


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_GRAPH_SNAPSHOT,
        vol.Optional("limit", default=GRAPH_INITIAL_NODE_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=GRAPH_INITIAL_REQUEST_MAX)
        ),
        vol.Optional("cursor", default=None): vol.Any(None, str),
    }
)
@websocket_api.async_response
async def _handle_graph_snapshot(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return a bounded area/device graph through the selected gateway."""
    gateway = _first_loaded_gateway(hass)
    if gateway is None:
        connection.send_error(
            msg["id"], "gateway_unavailable", "Ontology graph is unavailable"
        )
        return

    result = await gateway.initial_graph(msg["limit"], msg["cursor"])
    if result.get("available") is False:
        connection.send_error(
            msg["id"], "gateway_unavailable", "Ontology graph is unavailable"
        )
        return

    connection.send_result(
        msg["id"],
        {
            "nodes": list(result.get("nodes") or []),
            "relationships": list(result.get("relationships") or []),
            "truncated": bool(result.get("truncated")),
            "next_cursor": result.get("nextCursor"),
            "revision": int(result.get("revision") or 0),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_GRAPH_SEARCH,
        vol.Required("term"): _trimmed_search_term,
        vol.Optional("limit", default=GRAPH_SEARCH_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=GRAPH_SEARCH_MAX)
        ),
    }
)
@websocket_api.async_response
async def _handle_graph_search(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Search safe graph records through the selected backend."""
    gateway = _first_loaded_gateway(hass)
    if gateway is None:
        connection.send_error(
            msg["id"], "gateway_unavailable", "Ontology graph is unavailable"
        )
        return

    result = await gateway.search_graph(msg["term"].strip(), msg["limit"])
    if result.get("available") is False:
        connection.send_error(
            msg["id"], "gateway_unavailable", "Ontology graph is unavailable"
        )
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_GRAPH_DETAIL,
        vol.Required("element_id"): str,
    }
)
@websocket_api.async_response
async def _handle_graph_detail(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return one safe graph element and bounded direct connections."""
    if not _is_stable_graph_id(msg["element_id"]):
        connection.send_error(
            msg["id"], "invalid_format", "Graph element ID is invalid"
        )
        return
    gateway = _first_loaded_gateway(hass)
    if gateway is None:
        connection.send_error(
            msg["id"], "gateway_unavailable", "Ontology graph is unavailable"
        )
        return

    result = await gateway.graph_element(msg["element_id"])
    if result is None:
        connection.send_error(
            msg["id"], "not_found", "Graph element was not found"
        )
        return
    if result.get("available") is False:
        connection.send_error(
            msg["id"], "gateway_unavailable", "Ontology graph is unavailable"
        )
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_GRAPH_EXPAND,
        vol.Required("node_id"): str,
        vol.Optional("node_limit", default=GRAPH_EXPAND_NODE_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=GRAPH_EXPAND_NODE_MAX)
        ),
        vol.Optional("edge_limit", default=GRAPH_EXPAND_EDGE_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=GRAPH_EXPAND_EDGE_MAX)
        ),
        vol.Optional("cursor", default=None): vol.Any(None, str),
    }
)
@websocket_api.async_response
async def _handle_graph_expand(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return one bounded hop around a stable graph node."""
    if not _is_stable_graph_id(msg["node_id"]):
        connection.send_error(
            msg["id"], "invalid_format", "Graph element ID is invalid"
        )
        return
    gateway = _first_loaded_gateway(hass)
    if gateway is None:
        connection.send_error(
            msg["id"], "gateway_unavailable", "Ontology graph is unavailable"
        )
        return

    result = await gateway.expand_node(
        msg["node_id"], msg["node_limit"], msg["edge_limit"], msg["cursor"]
    )
    if result.get("available") is False:
        error = result.get("error")
        if error in {"not_found", "stale_cursor"}:
            connection.send_error(
                msg["id"], error, "Graph expansion could not be completed"
            )
        else:
            connection.send_error(
                msg["id"], "gateway_unavailable", "Ontology graph is unavailable"
            )
        return
    connection.send_result(
        msg["id"],
        {
            "nodes": list(result.get("nodes") or []),
            "relationships": list(result.get("relationships") or []),
            "truncated": bool(result.get("truncated")),
            "next_cursor": result.get("nextCursor"),
            "revision": int(result.get("revision") or 0),
        },
    )


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
                "entity": _node_properties(entity),
                "state": state.state if state is not None else None,
                "semantic_types": [t for t in item.get("semantic_types") or [] if t],
            }
        )

    connection.send_result(
        msg["id"],
        {
            "area": _node_properties(row["a"]),
            "devices": [_node_properties(d) for d in row.get("devices") or []],
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
            "entity": _node_properties(row["e"]),
            "state": state.state if state is not None else None,
            "device": _node_properties(row["d"]) if row.get("d") is not None else None,
            "area": (
                _node_properties(row["area"])
                if row.get("area") is not None
                else None
            ),
            "semantic_types": [t for t in row.get("semantic_types") or [] if t],
            "dependents": [
                _node_properties(x)
                for x in row.get("dependents") or []
                if x is not None
            ],
            "cards": [
                _node_properties(x)
                for x in row.get("cards") or []
                if x is not None
            ],
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
        node = _node_properties(row["node"])
        results.append({"type": labels[0], "ha_id": node.get("ha_id"), "name": node.get("name")})

    connection.send_result(msg["id"], {"results": results, "truncated": truncated})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_GRAPH_SUBSCRIBE,
        vol.Optional("from_revision", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)
@websocket_api.async_response
async def _handle_graph_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Subscribe to live graph change events with optional replay (US3).

    Sends a reconcile event when the requested revision cannot be bridged
    from the bounded in-memory buffer.  Coalesces per-element events over
    GRAPH_UPDATE_DEBOUNCE_SECONDS before dispatching to the client.
    """
    coordinator = _first_loaded_coordinator(hass)
    if coordinator is None:
        connection.send_error(
            msg["id"], "gateway_unavailable", "Ontology graph is unavailable"
        )
        return

    change_buffer = coordinator.change_buffer
    msg_id = msg["id"]
    from_revision = msg["from_revision"]
    subscriber_id = str(uuid.uuid4())

    # ---- Replay or reconcile ----
    replay = change_buffer.events_since(from_revision)
    connection.send_result(msg_id)

    if replay is None:
        # Buffer gap: tell the client to reload the snapshot.
        connection.send_event(
            msg_id,
            {
                "revision": change_buffer.current_revision,
                "kind": "reconcile",
                "node_ids": [],
                "relationship_ids": [],
                "changed_properties": [],
                "occurred_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            },
        )
    else:
        for event in replay:
            connection.send_event(msg_id, event.to_dict())

    # ---- Streaming with per-element 250 ms coalescing ----
    loop = hass.loop
    # pending[element_id] -> coalesced event data
    pending: dict[str, dict[str, Any]] = {}
    timers: dict[str, Any] = {}

    def _flush_element(element_id: str) -> None:
        data = pending.pop(element_id, None)
        timers.pop(element_id, None)
        if data is None:
            return
        try:
            connection.send_event(msg_id, data)
        except Exception:  # noqa: BLE001
            pass

    def _on_event(event: Any) -> None:
        if event.kind == "reconcile":
            # Flush pending and send reconcile immediately
            for eid in list(pending):
                timers.pop(eid, None)
            pending.clear()
            try:
                connection.send_event(msg_id, event.to_dict())
            except Exception:  # noqa: BLE001
                pass
            return

        all_ids = event.node_ids + event.relationship_ids
        for element_id in all_ids:
            if element_id in pending:
                existing = pending[element_id]
                existing["revision"] = max(existing["revision"], event.revision)
                existing["changed_properties"] = list(
                    set(existing["changed_properties"]) | set(event.changed_properties)
                )
                if element_id in timers:
                    timers[element_id].cancel()
            else:
                pending[element_id] = {
                    "revision": event.revision,
                    "kind": event.kind,
                    "node_ids": [element_id] if element_id in event.node_ids else [],
                    "relationship_ids": [element_id] if element_id in event.relationship_ids else [],
                    "changed_properties": list(event.changed_properties),
                    "occurred_at": event.occurred_at,
                }
            timers[element_id] = loop.call_later(
                GRAPH_UPDATE_DEBOUNCE_SECONDS,
                _flush_element,
                element_id,
            )

    change_buffer.subscribe(subscriber_id, _on_event)

    def _unsubscribe() -> None:
        change_buffer.unsubscribe(subscriber_id)
        for timer in timers.values():
            timer.cancel()
        timers.clear()
        pending.clear()

    connection.subscriptions[msg_id] = _unsubscribe


@websocket_api.websocket_command({vol.Required("type"): WS_TYPE_LAB_STATUS})
@websocket_api.async_response
async def _handle_lab_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return Memgraph Lab capability for authenticated administrators only (US4)."""
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Administrator access required")
        return

    coordinator = _first_loaded_coordinator(hass)
    if coordinator is None:
        connection.send_result(
            msg["id"],
            {"available": False, "reason": "not_addon_backend", "ingress_path": None, "checked_at": None},
        )
        return

    lab_access = getattr(coordinator, "lab_access", None)
    if lab_access is None:
        connection.send_result(
            msg["id"],
            {"available": False, "reason": "not_addon_backend", "ingress_path": None, "checked_at": None},
        )
        return

    capability = await lab_access.get_capability()
    connection.send_result(
        msg["id"],
        {
            "available": capability.get("available", False),
            "reason": capability.get("reason", "not_addon_backend"),
            "ingress_path": capability.get("ingress_path") if capability.get("available") else None,
            "checked_at": capability.get("checked_at"),
        },
    )


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
    websocket_api.async_register_command(hass, _handle_graph_snapshot)
    websocket_api.async_register_command(hass, _handle_graph_search)
    websocket_api.async_register_command(hass, _handle_graph_detail)
    websocket_api.async_register_command(hass, _handle_graph_expand)
    websocket_api.async_register_command(hass, _handle_graph_subscribe)
    websocket_api.async_register_command(hass, _handle_lab_status)
    hass.data[f"{DOMAIN}_ws_registered"] = True

"""Semantic classification rule engine (User Story 1, User Story 6).

Classifies Home Assistant entities into domain-specific semantic types
(``GasCylinder``, ``Vehicle``, ``EnergyAsset``, ``SecurityDevice``,
``OccupancySensor``, ``ClimateDevice``, ``NetworkDevice``,
``BatteryPoweredDevice``) using a small, declarative, independently
unit-testable rule table (research.md §5). Every semantic node created here
is tagged ``source = SOURCE_INFERRED`` and is 1:1 with the classified
``Entity`` (data-model.md); classification never overwrites an existing
``source = SOURCE_USER`` relationship for the same (entity, type) pair
(FR-006).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    LABEL_AREA,
    LABEL_BATTERY_POWERED_DEVICE,
    LABEL_CLIMATE_DEVICE,
    LABEL_ENERGY_ASSET,
    LABEL_ENTITY,
    LABEL_GAS_CYLINDER,
    LABEL_NETWORK_DEVICE,
    LABEL_OCCUPANCY_SENSOR,
    LABEL_SECURITY_DEVICE,
    LABEL_SEMANTIC_TYPE,
    LABEL_VEHICLE,
    REL_CLASSIFIED_AS,
    REL_LOCATED_IN,
    REL_MEASURED_BY,
    REL_OBSERVED_BY,
    REL_OVERRIDE_OF,
    SOURCE_GENERATED,
    SOURCE_INFERRED,
)
from .graph_builder import merge_node, merge_relationship
from .memgraph_client import MemgraphClient

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassificationRule:
    """One semantic-type rule: a domain gate plus device_class/keyword signals.

    A rule matches an entity when its domain (if constrained) matches AND
    either its ``device_class`` or a keyword is found in the entity's
    id/name/area text, or the rule has no device_class/keyword signals at
    all (a pure domain rule).
    """

    label: str
    back_relationship: str
    domains: tuple[str, ...] = ()
    device_classes: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


# Declarative rule table (research.md §5): evaluated against every entity on
# every classification run so an entity may match more than one type (FR-005).
RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        LABEL_GAS_CYLINDER,
        REL_MEASURED_BY,
        domains=("sensor", "binary_sensor"),
        device_classes=("gas",),
        keywords=("gas", "cylinder", "propane", "lpg"),
    ),
    ClassificationRule(
        LABEL_VEHICLE,
        REL_MEASURED_BY,
        domains=("device_tracker", "sensor", "binary_sensor"),
        keywords=("car", "vehicle", "truck", "ev charger"),
    ),
    ClassificationRule(
        LABEL_ENERGY_ASSET,
        REL_MEASURED_BY,
        domains=("sensor",),
        device_classes=("energy", "power", "voltage", "current"),
        keywords=("solar", "inverter", "energy", "power meter"),
    ),
    ClassificationRule(
        LABEL_SECURITY_DEVICE,
        REL_OBSERVED_BY,
        domains=("alarm_control_panel", "lock", "binary_sensor", "camera"),
        device_classes=("lock", "door", "window", "safety"),
        keywords=("alarm", "lock", "camera", "security"),
    ),
    ClassificationRule(
        LABEL_OCCUPANCY_SENSOR,
        REL_OBSERVED_BY,
        domains=("binary_sensor",),
        device_classes=("occupancy", "motion", "presence"),
        keywords=("occupancy", "motion", "presence"),
    ),
    ClassificationRule(
        LABEL_CLIMATE_DEVICE,
        REL_MEASURED_BY,
        domains=("climate", "sensor"),
        device_classes=("temperature", "humidity"),
        keywords=("thermostat", "climate", "hvac", "heater"),
    ),
    ClassificationRule(
        LABEL_NETWORK_DEVICE,
        REL_MEASURED_BY,
        domains=("device_tracker", "sensor", "binary_sensor"),
        device_classes=("connectivity",),
        keywords=("router", "wifi", "network", "access point"),
    ),
    ClassificationRule(
        LABEL_BATTERY_POWERED_DEVICE,
        REL_MEASURED_BY,
        domains=("sensor", "binary_sensor"),
        device_classes=("battery",),
        keywords=("battery",),
    ),
)


def _entity_signals(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    """Gather domain/device_class/name/area-name signals for one entity."""
    registry = er.async_get(hass)
    entry = registry.entities.get(entity_id)
    state = hass.states.get(entity_id)
    domain = entity_id.split(".", 1)[0]
    device_class = state.attributes.get("device_class") if state is not None else None
    friendly_name = (
        state.attributes.get("friendly_name") if state is not None else None
    ) or entity_id

    area_name = ""
    area_id = _resolve_area_id(hass, entity_id)
    if area_id:
        area = ar.async_get(hass).async_get_area(area_id)
        if area is not None:
            area_name = area.name or ""

    text = f" {entity_id} {friendly_name} {area_name} ".lower()
    return {"domain": domain, "device_class": device_class, "text": text}


def _resolve_area_id(hass: HomeAssistant, entity_id: str) -> str | None:
    """Best-effort area lookup: entity's own area, else its device's area."""
    registry = er.async_get(hass)
    entry = registry.entities.get(entity_id)
    if entry is None:
        return None
    if entry.area_id:
        return entry.area_id
    if entry.device_id:
        device = dr.async_get(hass).devices.get(entry.device_id)
        if device is not None:
            return device.area_id
    return None


def _rule_matches(rule: ClassificationRule, signals: dict[str, Any]) -> bool:
    if rule.domains and signals["domain"] not in rule.domains:
        return False
    if rule.device_classes and signals["device_class"] in rule.device_classes:
        return True
    if rule.keywords and any(keyword in signals["text"] for keyword in rule.keywords):
        return True
    return not rule.device_classes and not rule.keywords


def matching_rules(hass: HomeAssistant, entity_id: str) -> list[ClassificationRule]:
    """Return every rule this entity matches (FR-005: may match more than one)."""
    signals = _entity_signals(hass, entity_id)
    return [rule for rule in RULES if _rule_matches(rule, signals)]


def semantic_ha_id(entity_id: str, label: str) -> str:
    """Stable per-entity semantic asset node id (data-model.md `<entity>::<Type>`)."""
    return f"{entity_id}::{label}"


async def _has_user_override(client: MemgraphClient, entity_id: str, type_label: str) -> bool:
    """True if a `source = "user"` OVERRIDE_OF relationship already exists
    for this (entity, type) pair (FR-006) - classification must skip it."""
    query = (
        f"MATCH (e:{LABEL_ENTITY} {{ha_id: $entity_id}})"
        f"-[r:{REL_OVERRIDE_OF}]->(:{LABEL_SEMANTIC_TYPE} {{ha_id: $type_label}}) "
        "RETURN count(r) AS c"
    )
    rows = await client.run_query(query, {"entity_id": entity_id, "type_label": type_label})
    return bool(rows and rows[0]["c"])


async def _classify_entity(hass: HomeAssistant, client: MemgraphClient, entity_id: str) -> int:
    """Classify a single entity against every rule; returns the number of
    semantic types applied (skipping any pair with a user override, FR-006)."""
    applied = 0
    for rule in matching_rules(hass, entity_id):
        if await _has_user_override(client, entity_id, rule.label):
            _LOGGER.debug(
                "Skipping %s classification for %s: user override present", rule.label, entity_id
            )
            continue
        await merge_node(
            client, LABEL_SEMANTIC_TYPE, rule.label, {"name": rule.label}, source=SOURCE_GENERATED
        )
        await merge_relationship(
            client,
            LABEL_ENTITY,
            entity_id,
            REL_CLASSIFIED_AS,
            LABEL_SEMANTIC_TYPE,
            rule.label,
            source=SOURCE_INFERRED,
        )
        asset_id = semantic_ha_id(entity_id, rule.label)
        await merge_node(client, rule.label, asset_id, {}, source=SOURCE_INFERRED)
        await merge_relationship(
            client,
            rule.label,
            asset_id,
            rule.back_relationship,
            LABEL_ENTITY,
            entity_id,
            source=SOURCE_INFERRED,
        )
        area_id = _resolve_area_id(hass, entity_id)
        if area_id:
            await merge_relationship(
                client,
                rule.label,
                asset_id,
                REL_LOCATED_IN,
                LABEL_AREA,
                area_id,
                source=SOURCE_INFERRED,
            )
        applied += 1
    return applied


async def async_classify_entities(hass: HomeAssistant, client: MemgraphClient) -> int:
    """Full-graph classification pass (User Story 1).

    Returns the number of entities matched by at least one rule.
    """
    registry = er.async_get(hass)
    matched = 0
    for entity in registry.entities.values():
        if entity.platform == DOMAIN:
            continue
        if await _classify_entity(hass, client, entity.entity_id):
            matched += 1
    return matched


async def async_refresh_semantics(
    hass: HomeAssistant, client: MemgraphClient, entity_id: str | None = None
) -> int:
    """Re-run classification for one entity or all entities (User Story 6).

    Reuses the identical rule table/matching function as the full pass;
    never touches any `source = "user"` relationship (FR-025).
    """
    if entity_id is not None:
        return await _classify_entity(hass, client, entity_id)
    return await async_classify_entities(hass, client)

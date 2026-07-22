"""Diagnostic sensors for the Ontology integration (contracts/diagnostics.md)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import OntologyCoordinator, OntologyState


@dataclass(frozen=True, kw_only=True)
class OntologySensorEntityDescription(SensorEntityDescription):
    """Describes an Ontology diagnostic sensor."""

    value_fn: Callable[[OntologyState], object]


SENSOR_DESCRIPTIONS: tuple[OntologySensorEntityDescription, ...] = (
    OntologySensorEntityDescription(
        key="health",
        translation_key="ontology_health",
        value_fn=lambda state: state.health,
    ),
    OntologySensorEntityDescription(
        key="nodes",
        translation_key="ontology_nodes",
        state_class="measurement",
        value_fn=lambda state: state.node_count,
    ),
    OntologySensorEntityDescription(
        key="relationships",
        translation_key="ontology_relationships",
        state_class="measurement",
        value_fn=lambda state: state.relationship_count,
    ),
    OntologySensorEntityDescription(
        key="last_sync",
        translation_key="ontology_last_sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda state: state.last_sync,
    ),
    OntologySensorEntityDescription(
        key="last_error",
        translation_key="ontology_last_error",
        value_fn=lambda state: state.last_error or "none",
    ),
    OntologySensorEntityDescription(
        key="schema_version",
        translation_key="ontology_schema_version",
        value_fn=lambda state: state.schema_version,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Ontology diagnostic sensors."""
    coordinator: OntologyCoordinator = entry.runtime_data
    async_add_entities(
        OntologySensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class OntologySensor(CoordinatorEntity[OntologyCoordinator], SensorEntity):
    """A single ontology diagnostic sensor backed by the coordinator's state."""

    entity_description: OntologySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OntologyCoordinator,
        entry: ConfigEntry,
        description: OntologySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> object:
        """Return the sensor's current value, read directly from coordinator state
        so it reflects the latest health/error even outside a refresh cycle."""
        return self.entity_description.value_fn(self.coordinator.state)

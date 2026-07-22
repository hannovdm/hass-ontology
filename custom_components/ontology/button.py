"""Control buttons for the Ontology integration (contracts/diagnostics.md)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import OntologyCoordinator


@dataclass(frozen=True, kw_only=True)
class OntologyButtonEntityDescription(ButtonEntityDescription):
    """Describes an Ontology control button."""

    press_fn: Callable[[OntologyCoordinator], Coroutine[Any, Any, None]]


BUTTON_DESCRIPTIONS: tuple[OntologyButtonEntityDescription, ...] = (
    OntologyButtonEntityDescription(
        key="rebuild",
        translation_key="ontology_rebuild",
        press_fn=lambda coordinator: coordinator.async_rebuild(),
    ),
    OntologyButtonEntityDescription(
        key="validate",
        translation_key="ontology_validate",
        press_fn=lambda coordinator: coordinator.async_validate(),
    ),
    OntologyButtonEntityDescription(
        key="resync",
        translation_key="ontology_resync",
        press_fn=lambda coordinator: coordinator.async_resync(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Ontology control buttons."""
    coordinator: OntologyCoordinator = entry.runtime_data
    async_add_entities(
        OntologyButton(coordinator, entry, description)
        for description in BUTTON_DESCRIPTIONS
    )


class OntologyButton(CoordinatorEntity[OntologyCoordinator], ButtonEntity):
    """A single ontology control button that invokes a coordinator operation."""

    entity_description: OntologyButtonEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OntologyCoordinator,
        entry: ConfigEntry,
        description: OntologyButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    async def async_press(self) -> None:
        """Invoke the associated coordinator operation."""
        await self.entity_description.press_fn(self.coordinator)

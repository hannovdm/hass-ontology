"""Control buttons for the Ontology integration (contracts/diagnostics.md)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import mcp_server
from .const import BUTTON_KEY_REGENERATE_MCP_TOKEN, CONF_MCP_ENABLED, DEFAULT_MCP_ENABLED
from .coordinator import OntologyCoordinator


@dataclass(frozen=True, kw_only=True)
class OntologyButtonEntityDescription(ButtonEntityDescription):
    """Describes an Ontology control button."""

    press_fn: Callable[[OntologyCoordinator], Coroutine[Any, Any, None]]


async def _async_regenerate_mcp_token(coordinator: OntologyCoordinator) -> None:
    """Regenerate the MCP local access token and surface it once (research.md §3)."""
    token = await mcp_server.async_regenerate_token(coordinator.hass, coordinator.entry.entry_id)
    persistent_notification.async_create(
        coordinator.hass,
        f"New Ontology MCP access token: {token}\n\nThis token will not be shown again.",
        title="Ontology MCP token regenerated",
        notification_id=f"ontology_mcp_token_{coordinator.entry.entry_id}",
    )


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

MCP_BUTTON_DESCRIPTION = OntologyButtonEntityDescription(
    key=BUTTON_KEY_REGENERATE_MCP_TOKEN,
    translation_key="ontology_regenerate_mcp_token",
    press_fn=_async_regenerate_mcp_token,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Ontology control buttons."""
    coordinator: OntologyCoordinator = entry.runtime_data
    descriptions = list(BUTTON_DESCRIPTIONS)
    if entry.options.get(CONF_MCP_ENABLED, DEFAULT_MCP_ENABLED):
        descriptions.append(MCP_BUTTON_DESCRIPTION)
    async_add_entities(
        OntologyButton(coordinator, entry, description) for description in descriptions
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

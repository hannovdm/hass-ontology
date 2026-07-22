"""Config flow for the Ontology integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_DATABASE,
    CONF_ENCRYPTED,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    DEFAULT_DATABASE,
    DEFAULT_ENCRYPTED,
    DEFAULT_PORT,
    DOMAIN,
)
from .memgraph_client import CannotConnect, InvalidAuth, MemgraphClient

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the connection-details schema, optionally pre-filled."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
            ): int,
            vol.Optional(
                CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")
            ): str,
            vol.Optional(
                CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")
            ): str,
            vol.Optional(
                CONF_DATABASE, default=defaults.get(CONF_DATABASE, DEFAULT_DATABASE)
            ): str,
            vol.Optional(
                CONF_ENCRYPTED, default=defaults.get(CONF_ENCRYPTED, DEFAULT_ENCRYPTED)
            ): bool,
        }
    )


async def _validate_connection(data: dict[str, Any]) -> None:
    """Attempt a single bounded-timeout connection check.

    Raises ``CannotConnect`` or ``InvalidAuth`` on failure (contracts/config-flow.md).
    """
    client = MemgraphClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        username=data.get(CONF_USERNAME) or None,
        password=data.get(CONF_PASSWORD) or None,
        database=data.get(CONF_DATABASE) or None,
        encrypted=data.get(CONF_ENCRYPTED, DEFAULT_ENCRYPTED),
    )
    try:
        await client.test_connection()
    finally:
        await client.close()


class OntologyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for the Ontology integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial `user` setup step (contracts/config-flow.md)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_try_connect(user_input)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle updating an existing connection without a restart (FR-003)."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_try_connect(user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data=user_input,
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or dict(reconfigure_entry.data)),
            errors=errors,
        )

    async def _async_try_connect(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Validate connectivity, returning a `{field: error_key}` errors dict."""
        try:
            await _validate_connection(user_input)
        except InvalidAuth:
            return {"base": "invalid_auth"}
        except CannotConnect:
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001 - normalize any unexpected driver error
            _LOGGER.exception("Unexpected error validating Memgraph connection")
            return {"base": "unknown"}
        return {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OntologyOptionsFlow()


class OntologyOptionsFlow(OptionsFlow):
    """Options flow mirroring the reconfigure step (FR-003)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle updating the connection via the options flow."""
        errors: dict[str, str] = {}
        current = dict(self.config_entry.data)
        if user_input is not None:
            try:
                await _validate_connection(user_input)
            except InvalidAuth:
                errors = {"base": "invalid_auth"}
            except CannotConnect:
                errors = {"base": "cannot_connect"}
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Memgraph connection")
                errors = {"base": "unknown"}
            if not errors:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=user_input
                )
                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(user_input or current),
            errors=errors,
        )

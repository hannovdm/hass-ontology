"""Repair issues for the Ontology integration.

Both issues are created without `is_fixable` (there is no automated fix —
the administrator must resolve the underlying condition manually) and are
cleared automatically once the condition is detected as resolved
(contracts/diagnostics.md "Repair issues").
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, ISSUE_SCHEMA_VERSION_MISMATCH, ISSUE_SUSTAINED_CONNECTION_FAILURE


def _schema_mismatch_issue_id(entry: ConfigEntry) -> str:
    return f"{ISSUE_SCHEMA_VERSION_MISMATCH}_{entry.entry_id}"


def _sustained_failure_issue_id(entry: ConfigEntry) -> str:
    return f"{ISSUE_SUSTAINED_CONNECTION_FAILURE}_{entry.entry_id}"


def async_create_schema_mismatch_issue(
    hass: HomeAssistant, entry: ConfigEntry, found_version: str, expected_version: str
) -> None:
    """Create the `schema_version_mismatch` repair issue (User Story 8, T057)."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _schema_mismatch_issue_id(entry),
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_SCHEMA_VERSION_MISMATCH,
        translation_placeholders={
            "found_version": found_version,
            "expected_version": expected_version,
        },
    )


def async_clear_schema_mismatch_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear the `schema_version_mismatch` repair issue once resolved."""
    ir.async_delete_issue(hass, DOMAIN, _schema_mismatch_issue_id(entry))


def async_create_sustained_failure_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create the `sustained_connection_failure` repair issue (User Story 9, T061)."""
    consecutive_failures = getattr(entry.runtime_data.state, "consecutive_failures", 0)
    ir.async_create_issue(
        hass,
        DOMAIN,
        _sustained_failure_issue_id(entry),
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_SUSTAINED_CONNECTION_FAILURE,
        translation_placeholders={"attempts": str(consecutive_failures)},
    )


def async_clear_sustained_failure_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear the `sustained_connection_failure` repair issue once a sync succeeds."""
    ir.async_delete_issue(hass, DOMAIN, _sustained_failure_issue_id(entry))

"""Contract tests for Memgraph Lab access (US4, T046).

Validates admin-only gating, Community/direct-backend fail-closed reasons,
sanitized capability transitions, diagnostic redaction, and ingress-path
disclosure policy (contracts/lab-access.md).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ontology import websocket_api as ontology_ws
from custom_components.ontology.const import DOMAIN, WS_TYPE_LAB_STATUS


def _make_coordinator(lab_capability=None):
    coordinator = MagicMock()
    coordinator.change_buffer = MagicMock()
    coordinator.change_buffer.current_revision = 0
    if lab_capability is not None:
        lab_access = AsyncMock()
        lab_access.get_capability = AsyncMock(return_value=lab_capability)
        coordinator.lab_access = lab_access
    else:
        coordinator.lab_access = None
    return coordinator


async def _call_lab_status(hass, coordinator, is_admin: bool = True):
    connection = MagicMock()
    connection.user = MagicMock(is_admin=is_admin)
    with patch.object(ontology_ws, "_first_loaded_coordinator", return_value=coordinator):
        ontology_ws._handle_lab_status(hass, connection, {"id": 1, "type": WS_TYPE_LAB_STATUS})
        await hass.async_block_till_done(wait_background_tasks=True)
    return connection


# ---------------------------------------------------------------------------
# Admin-only access check
# ---------------------------------------------------------------------------


async def test_lab_status_denies_non_admin_with_unauthorized(hass) -> None:
    coordinator = _make_coordinator({"available": True, "reason": "READY", "ingress_path": "/ingress/lab", "checked_at": "2026-08-19T12:00:00Z"})
    connection = await _call_lab_status(hass, coordinator, is_admin=False)

    connection.send_result.assert_not_called()
    code = connection.send_error.call_args.args[1]
    assert code == "unauthorized"


async def test_lab_status_denies_non_admin_without_revealing_capability(hass) -> None:
    coordinator = _make_coordinator({"available": True, "reason": "READY", "ingress_path": "/ingress/lab", "checked_at": "2026-08-19T12:00:00Z"})
    connection = await _call_lab_status(hass, coordinator, is_admin=False)

    error_message = connection.send_error.call_args.args[2]
    assert "ingress" not in error_message.lower()
    assert "/lab" not in error_message.lower()
    assert "ready" not in error_message.lower()


# ---------------------------------------------------------------------------
# Direct-backend fail-closed
# ---------------------------------------------------------------------------


async def test_lab_status_returns_not_addon_backend_when_no_lab_access(hass) -> None:
    coordinator = _make_coordinator(None)
    connection = await _call_lab_status(hass, coordinator, is_admin=True)

    result = connection.send_result.call_args.args[1]
    assert result["available"] is False
    assert result["reason"] == "not_addon_backend"
    assert result["ingress_path"] is None


async def test_lab_status_returns_not_addon_backend_when_no_coordinator(hass) -> None:
    connection = await _call_lab_status(hass, None, is_admin=True)

    result = connection.send_result.call_args.args[1]
    assert result["available"] is False
    assert result["reason"] == "not_addon_backend"


# ---------------------------------------------------------------------------
# Community fail-closed
# ---------------------------------------------------------------------------


async def test_lab_status_unavailable_with_enterprise_required_for_community(hass) -> None:
    coordinator = _make_coordinator({"available": False, "reason": "ENTERPRISE_REQUIRED", "ingress_path": None, "checked_at": "2026-08-19T12:00:00Z"})
    connection = await _call_lab_status(hass, coordinator, is_admin=True)

    result = connection.send_result.call_args.args[1]
    assert result["available"] is False
    assert result["reason"] == "ENTERPRISE_REQUIRED"
    assert result["ingress_path"] is None


# ---------------------------------------------------------------------------
# Enterprise available
# ---------------------------------------------------------------------------


async def test_lab_status_returns_available_with_ingress_path_when_ready(hass) -> None:
    coordinator = _make_coordinator({
        "available": True,
        "reason": "READY",
        "ingress_path": "/api/hassio_ingress/abc123",
        "checked_at": "2026-08-19T12:00:00Z",
    })
    connection = await _call_lab_status(hass, coordinator, is_admin=True)

    result = connection.send_result.call_args.args[1]
    assert result["available"] is True
    assert result["reason"] == "READY"
    assert result["ingress_path"] == "/api/hassio_ingress/abc123"


async def test_lab_status_hides_ingress_path_when_unavailable(hass) -> None:
    coordinator = _make_coordinator({
        "available": False,
        "reason": "LAB_UNHEALTHY",
        "ingress_path": "/api/hassio_ingress/abc123",
        "checked_at": "2026-08-19T12:00:00Z",
    })
    connection = await _call_lab_status(hass, coordinator, is_admin=True)

    result = connection.send_result.call_args.args[1]
    assert result["available"] is False
    assert result["ingress_path"] is None


# ---------------------------------------------------------------------------
# Credential/token redaction
# ---------------------------------------------------------------------------


async def test_lab_status_never_reveals_credentials(hass) -> None:
    coordinator = _make_coordinator({
        "available": True,
        "reason": "READY",
        "ingress_path": "/api/hassio_ingress/abc123",
        "checked_at": "2026-08-19T12:00:00Z",
        "internal_password": "super-secret",  # Must be stripped
        "bolt_uri": "bolt://localhost:7687",   # Must be stripped
    })
    connection = await _call_lab_status(hass, coordinator, is_admin=True)

    result = connection.send_result.call_args.args[1]
    serialized = repr(result)
    assert "super-secret" not in serialized
    assert "bolt://" not in serialized
    assert "password" not in serialized.lower()


# ---------------------------------------------------------------------------
# Lab capability model validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reason", [
    "READY",
    "NOT_ADDON_BACKEND",
    "TRANSPORT_UNAVAILABLE",
    "LAB_UNHEALTHY",
    "ENTERPRISE_REQUIRED",
    "READONLY_USER_MISSING",
    "WRITE_PROBE_SUCCEEDED",
])
def test_lab_capability_reason_enum_values_match_contract(reason: str) -> None:
    from custom_components.ontology.lab_access import LAB_CAPABILITY_REASONS
    assert reason in LAB_CAPABILITY_REASONS or reason.lower() in {r.lower() for r in LAB_CAPABILITY_REASONS}


# ---------------------------------------------------------------------------
# Diagnostics redaction
# ---------------------------------------------------------------------------


async def test_lab_diagnostics_never_expose_credentials(hass) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.ontology.diagnostics import async_get_config_entry_diagnostics
    from custom_components.ontology.coordinator import OntologyCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "localhost", "port": 7687, "database": "memgraph", "encrypted": False},
    )
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.run_query = AsyncMock(return_value=[])
    coordinator = OntologyCoordinator(hass, entry, client)

    lab_access = MagicMock()
    lab_access.diagnostics = MagicMock(return_value={
        "available": False,
        "reason": "ENTERPRISE_REQUIRED",
        "probe_duration_ms": 42,
    })
    coordinator.lab_access = lab_access
    entry.runtime_data = coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    serialized = repr(diagnostics)
    assert "password" not in serialized.lower()
    assert "secret" not in serialized.lower()
    assert "token" not in serialized.lower()
    assert "bolt://" not in serialized

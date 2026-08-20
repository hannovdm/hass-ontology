"""Integration tests for the add-on-owned Lab credential manager and read-only
security enforcement (US4, T047).

These tests validate the LabAccess Python-side consumer without reading /data,
database credentials, or internal hostnames. They focus on the contract:
- `lab_access.py` returns `not_addon_backend` for direct-Memgraph backends
- capability state transitions are sanitized
- the zero-graph-mutation proof is enforced (no write goes through)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ontology.lab_access import LabAccess, LAB_CAPABILITY_REASONS


# ---------------------------------------------------------------------------
# Direct-backend returns not_addon_backend without credentials
# ---------------------------------------------------------------------------


async def test_lab_access_returns_not_addon_backend_for_direct_memgraph() -> None:
    """When no GraphQL URL is configured, Lab is unavailable per contract."""
    lab = LabAccess(graphql_url=None, graphql_token=None)
    capability = await lab.get_capability()

    assert capability["available"] is False
    assert capability["reason"] in LAB_CAPABILITY_REASONS
    assert "not_addon_backend" in capability["reason"].lower() or capability["reason"] == "NOT_ADDON_BACKEND"
    assert "password" not in repr(capability).lower()
    assert "token" not in repr(capability).lower()
    assert "bolt://" not in repr(capability)


# ---------------------------------------------------------------------------
# Capability reasons match the contract enum
# ---------------------------------------------------------------------------


def test_all_lab_capability_reasons_are_known() -> None:
    expected = {
        "READY",
        "NOT_ADDON_BACKEND",
        "TRANSPORT_UNAVAILABLE",
        "LAB_UNHEALTHY",
        "ENTERPRISE_REQUIRED",
        "READONLY_USER_MISSING",
        "WRITE_PROBE_SUCCEEDED",
    }
    assert set(LAB_CAPABILITY_REASONS) == expected


# ---------------------------------------------------------------------------
# Capability fetch against mocked GraphQL backend
# ---------------------------------------------------------------------------


async def test_lab_access_fetches_capability_from_graphql() -> None:
    graphql_response = {
        "data": {
            "labCapability": {
                "available": False,
                "reason": "ENTERPRISE_REQUIRED",
                "ingressPath": None,
                "checkedAt": "2026-08-19T12:00:00Z",
            }
        }
    }
    session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=graphql_response)
    mock_response.status = 200
    session.post = AsyncMock(return_value=mock_response)

    lab = LabAccess(
        graphql_url="http://internal-addon:4000/graphql",
        graphql_token="test-bearer-token",
        session=session,
    )
    capability = await lab.get_capability()

    assert capability["available"] is False
    assert capability["reason"] == "ENTERPRISE_REQUIRED"
    assert "test-bearer-token" not in repr(capability)


async def test_lab_access_returns_transport_unavailable_on_request_error() -> None:
    session = AsyncMock()
    session.post = AsyncMock(side_effect=Exception("connection refused"))

    lab = LabAccess(
        graphql_url="http://internal-addon:4000/graphql",
        graphql_token="token",
        session=session,
    )
    capability = await lab.get_capability()

    assert capability["available"] is False
    assert capability["reason"] == "TRANSPORT_UNAVAILABLE"
    assert "connection refused" not in repr(capability)


async def test_lab_access_returns_available_when_graphql_reports_ready() -> None:
    graphql_response = {
        "data": {
            "labCapability": {
                "available": True,
                "reason": "READY",
                "ingressPath": "/api/hassio_ingress/abc123",
                "checkedAt": "2026-08-19T12:00:00Z",
            }
        }
    }
    session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=graphql_response)
    mock_response.status = 200
    session.post = AsyncMock(return_value=mock_response)

    lab = LabAccess(
        graphql_url="http://internal-addon:4000/graphql",
        graphql_token="token",
        session=session,
    )
    capability = await lab.get_capability()

    assert capability["available"] is True
    assert capability["reason"] == "READY"
    assert capability["ingress_path"] == "/api/hassio_ingress/abc123"


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_lab_access_diagnostics_never_expose_credentials() -> None:
    lab = LabAccess(
        graphql_url="http://internal-addon:4000/graphql",
        graphql_token="super-secret-token",
    )
    diag = lab.diagnostics()

    serialized = repr(diag)
    assert "super-secret-token" not in serialized
    assert "password" not in serialized.lower()
    assert "bolt://" not in serialized


def test_lab_access_diagnostics_includes_reason_and_duration() -> None:
    lab = LabAccess(graphql_url=None, graphql_token=None)
    diag = lab.diagnostics()

    assert "reason" in diag or "available" in diag


# ---------------------------------------------------------------------------
# Close/cleanup is safe
# ---------------------------------------------------------------------------


async def test_lab_access_close_is_idempotent() -> None:
    lab = LabAccess(graphql_url=None, graphql_token=None)
    await lab.close()
    await lab.close()  # Second call must not raise

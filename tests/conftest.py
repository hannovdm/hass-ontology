"""Shared pytest fixtures for unit/contract tests.

Provides a mocked Home Assistant core, a mocked config entry, and a mocked
Memgraph client so unit tests never need a real Home Assistant instance or a
real Memgraph server (research.md §3).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

if sys.platform == "win32":
    # Windows-only test-environment shim (must run before the
    # `pytest_homeassistant_custom_component` plugin below is imported, since
    # that import chain unconditionally does `import fcntl` / `import resource`,
    # both POSIX-only stdlib modules. `tests/_winstubs/` provides no-op stand-ins;
    # putting that directory first on `sys.path` lets Windows dev machines import
    # the plugin at all. CI (Linux) has the real modules and never uses this path.
    _winstubs_dir = str(Path(__file__).parent / "_winstubs")
    if _winstubs_dir not in sys.path:
        sys.path.insert(0, _winstubs_dir)

import pytest  # noqa: E402

pytest_plugins = ["pytest_homeassistant_custom_component"]

if sys.platform == "win32":
    # Windows-only test-environment shim.
    #
    # `pytest-homeassistant-custom-component` calls `pytest_socket.disable_socket()`
    # before every test. On POSIX, asyncio's event-loop "self-pipe" is a real
    # `os.pipe()` (unaffected by the socket guard). On Windows, asyncio only has
    # `ProactorEventLoop`/`SelectorEventLoop`, both of which build their self-pipe
    # via `socket.socketpair()`, which itself falls back to a real loopback
    # `socket.socket()` (Windows lacks AF_UNIX socketpair support). pytest-socket's
    # guard blocks that call unconditionally, so *every* async test using the
    # `hass` fixture fails with `SocketBlockedError` before the test body even runs.
    # This is a pre-existing Windows/asyncio/pytest-socket incompatibility, not a
    # bug in this project. CI (Linux) never hits this path, so the shim is scoped
    # to `win32` only.
    import pytest_socket

    def _allow_socket_for_asyncio_self_pipe(*_args: object, **_kwargs: object) -> None:
        """No-op replacement for `pytest_socket.disable_socket` on Windows."""

    pytest_socket.disable_socket = _allow_socket_for_asyncio_self_pipe

from homeassistant.core import State  # noqa: E402

from custom_components.ontology.const import (  # noqa: E402
    CONF_DATABASE,
    CONF_ENCRYPTED,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make `custom_components/ontology` discoverable by Home Assistant's loader.

    Home Assistant's test harness ignores `custom_components/` by default so
    that core-integration tests aren't polluted by a developer's local custom
    components. This project *is* a custom component, so every test needs it
    re-enabled.
    """


@pytest.fixture
def mock_memgraph_client() -> AsyncMock:
    """A fully-mocked async MemgraphClient."""
    client = AsyncMock()
    client.connect = AsyncMock(return_value=None)
    client.close = AsyncMock(return_value=None)
    client.test_connection = AsyncMock(return_value=None)
    client.run_query = AsyncMock(return_value=[])
    client.run_query_with_retry = AsyncMock(return_value=[])
    client.execute_write = AsyncMock(return_value=None)
    return client


@pytest.fixture
def battery_state_builder() -> Callable[..., State]:
    """Build battery states with explicit source timestamps and units."""

    def _build(
        entity_id: str = "sensor.test_battery",
        value: str = "20",
        *,
        unit: str = "%",
        last_updated: datetime | None = None,
        **attributes: object,
    ) -> State:
        return State(
            entity_id,
            value,
            {
                "device_class": "battery",
                "unit_of_measurement": unit,
                "friendly_name": "Test battery",
                **attributes,
            },
            last_updated=last_updated or datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        )

    return _build


@pytest.fixture
def power_state_builder() -> Callable[..., State]:
    """Build power states covering strict W/kW normalization."""

    def _build(
        entity_id: str = "sensor.test_power",
        value: str = "1",
        *,
        unit: str = "W",
        last_updated: datetime | None = None,
        **attributes: object,
    ) -> State:
        return State(
            entity_id,
            value,
            {
                "device_class": "power",
                "unit_of_measurement": unit,
                "friendly_name": "Test power",
                **attributes,
            },
            last_updated=last_updated or datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        )

    return _build


@pytest.fixture
def ambiguous_target_rows() -> Callable[..., list[dict[str, object]]]:
    """Build deterministic duplicate-name resolver rows."""

    def _build(name: str = "Garage sensor") -> list[dict[str, object]]:
        return [
            {"target_type": "device", "target_id": "device-b", "name": name, "area_name": None},
            {
                "target_type": "entity",
                "target_id": "sensor.garage_a",
                "name": name,
                "area_name": "Garage",
            },
        ]

    return _build


@pytest.fixture
def automation_dependency_rows() -> list[dict[str, object]]:
    """Return overlapping entity-level automation dependency rows."""
    return [
        {
            "automation_id": "automation.garage_light",
            "name": "Garage light",
            "entity_id": "binary_sensor.garage_motion",
            "relationship_type": "REFERENCES",
        },
        {
            "automation_id": "automation.garage_light",
            "name": "Garage light",
            "entity_id": "sensor.garage_illuminance",
            "relationship_type": "REFERENCES",
        },
    ]


@pytest.fixture
def gas_cylinder_record() -> dict[str, object]:
    """Return a canonical gas-cylinder fixture used by later statement tests."""
    return {
        "ha_id": "sensor.gas_cylinder_weight::GasCylinder",
        "name": "48kg gas cylinder",
        "source": "inferred",
    }


@pytest.fixture
def mock_config_entry_data() -> dict:
    return {
        CONF_HOST: "localhost",
        CONF_PORT: 7687,
        CONF_USERNAME: "",
        CONF_PASSWORD: "",
        CONF_DATABASE: "",
        CONF_ENCRYPTED: False,
    }


@pytest.fixture
def mock_config_entry(mock_config_entry_data: dict) -> MagicMock:
    entry = MagicMock()
    entry.domain = DOMAIN
    entry.data = mock_config_entry_data
    entry.options = {}
    entry.entry_id = "test_entry_id"
    return entry

"""Shared pytest fixtures for unit/contract tests.

Provides a mocked Home Assistant core, a mocked config entry, and a mocked
Memgraph client so unit tests never need a real Home Assistant instance or a
real Memgraph server (research.md §3).
"""

from __future__ import annotations

import sys
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
    return client


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

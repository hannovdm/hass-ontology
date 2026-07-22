"""Integration-test fixtures: a real Memgraph instance via testcontainers.

Integration tests validate idempotent-MERGE behavior, schema-version
detection, and end-to-end sync behavior that mocks cannot fully verify
(research.md §3).
"""

from __future__ import annotations

import socket
import time
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from custom_components.ontology.memgraph_client import MemgraphClient

MEMGRAPH_IMAGE = "memgraph/memgraph:latest"
BOLT_PORT = 7687


def _wait_for_bolt_port(host: str, port: int, timeout: float = 30) -> None:
    """Block until the Bolt TCP port actually accepts connections.

    Memgraph emits its "You are running Memgraph" log line slightly before
    the Bolt listener is ready to complete a handshake, which produces a
    flaky ``ServiceUnavailable`` on the very first connection attempt.
    """
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError as err:
            last_error = err
            time.sleep(0.25)
    raise TimeoutError(f"Bolt port {host}:{port} not accepting connections") from last_error


@pytest.fixture(scope="session")
def memgraph_container() -> DockerContainer:
    container = DockerContainer(MEMGRAPH_IMAGE).with_exposed_ports(BOLT_PORT)
    container.start()
    wait_for_logs(container, "You are running Memgraph", timeout=60)
    _wait_for_bolt_port(
        container.get_container_host_ip(), int(container.get_exposed_port(BOLT_PORT))
    )
    yield container
    container.stop()


@pytest_asyncio.fixture
async def memgraph_client(memgraph_container: DockerContainer) -> AsyncGenerator[MemgraphClient]:
    host = memgraph_container.get_container_host_ip()
    port = int(memgraph_container.get_exposed_port(BOLT_PORT))
    client = MemgraphClient(host=host, port=port)
    await client.connect()
    # Ensure each test starts from a clean graph.
    await client.run_query("MATCH (n) DETACH DELETE n")
    yield client
    await client.close()

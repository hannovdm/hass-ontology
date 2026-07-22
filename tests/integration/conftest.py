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


_BOLT_MAGIC = b"\x60\x60\xb0\x17"
# Propose Bolt versions 5.4 down to 4.0, mirroring what the neo4j driver sends.
_BOLT_HANDSHAKE = _BOLT_MAGIC + b"\x00\x04\x04\x00" + b"\x00\x02\x04\x04" + (b"\x00" * 8)


def _wait_for_bolt_port(host: str, port: int, timeout: float = 30) -> None:
    """Block until the Bolt listener actually completes a handshake.

    Memgraph emits its "You are running Memgraph" log line slightly before
    the Bolt listener is ready to complete a handshake. A bare TCP connect
    can succeed against Docker's port-forwarding layer before the Bolt
    protocol negotiation itself is serviceable, so this performs the real
    magic-byte handshake and requires a non-empty version response,
    retrying until it succeeds (or the timeout elapses).
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1) as sock:
                sock.sendall(_BOLT_HANDSHAKE)
                response = sock.recv(4)
                if len(response) == 4:
                    return
                raise ConnectionError("Bolt handshake closed with an incomplete response")
        except OSError as err:
            last_error = err
            time.sleep(0.25)
    raise TimeoutError(f"Bolt port {host}:{port} not accepting handshakes") from last_error


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

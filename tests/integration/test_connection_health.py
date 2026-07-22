"""Integration test: memgraph_client.test_connection() against a real Memgraph
container (User Story 2)."""

from __future__ import annotations

from custom_components.ontology.memgraph_client import MemgraphClient


async def test_connection_succeeds_against_real_memgraph(memgraph_client: MemgraphClient) -> None:
    """A bounded-timeout connectivity check succeeds against a reachable
    Memgraph instance (contracts/config-flow.md, FR-002)."""
    await memgraph_client.test_connection()

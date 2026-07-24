"""Integration test: a validation finding's full lifecycle - created on
detection, marked resolved when the underlying issue is fixed, and removed
only after remaining resolved across one full subsequent validation run
(User Story 5, T036, spec.md Assumptions/FR-016)."""

from __future__ import annotations

from custom_components.ontology import validation
from custom_components.ontology.const import (
    FINDING_MISSING_AREA,
    FINDING_STATUS_OPEN,
    FINDING_STATUS_RESOLVED,
    LABEL_AREA,
    LABEL_DEVICE,
    LABEL_VALIDATION_FINDING,
)
from custom_components.ontology.memgraph_client import MemgraphClient

_FINDING_ID = f"{FINDING_MISSING_AREA}::device-1"


async def _finding_status(client: MemgraphClient) -> str | None:
    rows = await client.run_query(
        f"MATCH (f:{LABEL_VALIDATION_FINDING} {{ha_id: $ha_id}}) RETURN f.status AS status",
        {"ha_id": _FINDING_ID},
    )
    return rows[0]["status"] if rows else None


async def test_validation_finding_created_resolved_then_removed(
    hass, memgraph_client: MemgraphClient
) -> None:
    # A Device with no HAS_AREA relationship triggers `missing_area`.
    await memgraph_client.run_query(
        f"MERGE (d:{LABEL_DEVICE} {{ha_id: 'device-1'}}) SET d.name = 'Device 1'"
    )

    await validation.async_run_validation(hass, memgraph_client)
    assert await _finding_status(memgraph_client) == FINDING_STATUS_OPEN

    # Fix the underlying issue: attach the device to an area.
    await memgraph_client.run_query(
        f"MATCH (d:{LABEL_DEVICE} {{ha_id: 'device-1'}}) "
        f"MERGE (a:{LABEL_AREA} {{ha_id: 'area-1'}}) "
        "MERGE (a)-[:HAS_DEVICE]->(d)"
    )

    # Run 1 after the fix: the finding is no longer detected, so it is
    # marked resolved - but NOT removed yet (must remain resolved across
    # one full subsequent run first).
    await validation.async_run_validation(hass, memgraph_client)
    assert await _finding_status(memgraph_client) == FINDING_STATUS_RESOLVED

    # Run 2 after the fix (the finding has now remained resolved across a
    # full subsequent run): it is removed entirely.
    await validation.async_run_validation(hass, memgraph_client)
    assert await _finding_status(memgraph_client) is None

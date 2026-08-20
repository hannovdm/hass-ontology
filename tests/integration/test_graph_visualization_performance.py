"""Backend-neutral initial graph bounds and performance tests for US1."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pytest

from custom_components.ontology.graph_backends import (
    AddonGraphQLBackend,
    DirectMemgraphBackend,
)

_FIXTURE_NODE_COUNT = 5_000
_INITIAL_LIMIT = 500
_P95_BUDGET_SECONDS = 3.0
_SAMPLE_COUNT = 20


def _node(index: int) -> dict[str, Any]:
    node_type = "Area" if index < 50 else "Device"
    return {
        "labels": [node_type],
        "properties": {
            "ha_id": f"{node_type.lower()}-{index}",
            "name": f"{node_type} {index}",
            "source": "home_assistant",
        },
    }


class _DirectFixtureClient:
    def __init__(self) -> None:
        self.nodes = [_node(index) for index in range(_FIXTURE_NODE_COUNT)]

    async def run_query(self, _query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        requested = parameters["node_limit"]
        return [{"nodes": self.nodes[:requested], "relationships": []}]


@dataclass
class _GraphQLResponse:
    payload: dict[str, Any]
    status: int = 200

    async def json(self) -> dict[str, Any]:
        return self.payload


class _GraphQLFixtureSession:
    def __init__(self) -> None:
        self.nodes = [
            {
                "id": f"{'Area' if index < 50 else 'Device'}:{'area' if index < 50 else 'device'}-{index}",
                "haId": f"{'area' if index < 50 else 'device'}-{index}",
                "type": "AREA" if index < 50 else "DEVICE",
                "label": f"{'Area' if index < 50 else 'Device'} {index}",
                "icon": None,
                "state": None,
                "unavailable": False,
                "findingSeverity": None,
                "properties": [],
            }
            for index in range(_FIXTURE_NODE_COUNT)
        ]

    async def post(self, _url: str, **kwargs: Any) -> _GraphQLResponse:
        limit = kwargs["json"]["variables"]["limit"]
        return _GraphQLResponse(
            {
                "data": {
                    "initialGraph": {
                        "nodes": self.nodes[:limit],
                        "relationships": [],
                        "pageInfo": {
                            "truncated": len(self.nodes) > limit,
                            "nextCursor": "fixture-page-2",
                        },
                        "revision": 11,
                    }
                }
            }
        )


@pytest.fixture(params=("direct", "graphql"))
def initial_graph_backend(request):
    if request.param == "direct":
        return request.param, DirectMemgraphBackend(_DirectFixtureClient())
    return request.param, AddonGraphQLBackend(
        "http://fixture.invalid/graphql",
        "fixture-token",
        session=_GraphQLFixtureSession(),
    )


async def test_initial_area_device_graph_is_bounded_for_5000_node_fixture(
    initial_graph_backend,
) -> None:
    backend_name, backend = initial_graph_backend

    result = await backend.initial_graph(limit=50_000)

    assert len(result["nodes"]) == _INITIAL_LIMIT, backend_name
    assert result["truncated"] is True
    assert result["nextCursor"] in {None, "fixture-page-2"}
    assert all(node["id"].startswith(("Area:", "Device:")) for node in result["nodes"])


async def test_initial_area_device_graph_meets_three_second_p95(
    initial_graph_backend,
) -> None:
    backend_name, backend = initial_graph_backend
    samples: list[float] = []

    for _ in range(_SAMPLE_COUNT):
        started = time.perf_counter()
        result = await backend.initial_graph(limit=_INITIAL_LIMIT)
        samples.append(time.perf_counter() - started)
        assert result["nodes"]

    p95 = sorted(samples)[int(_SAMPLE_COUNT * 0.95) - 1]
    assert p95 < _P95_BUDGET_SECONDS, f"{backend_name} initial graph p95 was {p95:.3f}s"
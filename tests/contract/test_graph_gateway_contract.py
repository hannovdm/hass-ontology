"""Contract tests for the Home Assistant internal graph gateway boundary."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.ontology.graph_backends import AddonGraphQLBackend


@pytest.mark.asyncio
async def test_addon_backend_sends_bearer_auth_and_named_document_only() -> None:
    response = AsyncMock()
    response.status = 200
    response.json.return_value = {
        "data": {
            "graphHealth": {"status": "HEALTHY", "revision": 7, "latencyMs": 3}
        }
    }
    response.__aenter__.return_value = response
    response.__aexit__.return_value = None
    session = AsyncMock()
    session.post.return_value = response
    backend = AddonGraphQLBackend(
        "http://addon:4000/graphql", "top-secret", session=session
    )

    result = await backend.graph_health()

    assert result["revision"] == 7
    call = session.post.call_args
    assert call.kwargs["headers"] == {"Authorization": "Bearer top-secret"}
    assert call.kwargs["json"]["operationName"] == "GraphHealth"
    assert "mutation" not in call.kwargs["json"]["query"].lower()
    assert "top-secret" not in repr(backend)
    assert "addon:4000" not in repr(backend)


def test_backend_has_no_arbitrary_document_or_query_method() -> None:
    public = {name for name in dir(AddonGraphQLBackend) if not name.startswith("_")}
    assert "execute" not in public
    assert "query" not in public
    assert "cypher" not in public

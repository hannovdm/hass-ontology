"""Transport checks for the authenticated internal GraphQL backend."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.ontology.graph_backends import AddonGraphQLBackend, GraphBackendUnavailable


@pytest.mark.asyncio
async def test_graphql_auth_failure_is_sanitized_and_does_not_fallback() -> None:
    response = AsyncMock()
    response.status = 401
    response.text.return_value = "token bad-token rejected by http://addon:4000"
    response.__aenter__.return_value = response
    response.__aexit__.return_value = None
    session = AsyncMock()
    session.post.return_value = response
    backend = AddonGraphQLBackend(
        "http://addon:4000/graphql", "bad-token", session=session
    )

    with pytest.raises(GraphBackendUnavailable, match="authentication failed") as error:
        await backend.graph_health()

    assert "bad-token" not in str(error.value)
    assert "addon:4000" not in str(error.value)
    assert session.post.call_count == 1

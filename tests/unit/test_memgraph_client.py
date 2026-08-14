"""Tests for the managed Memgraph write-transaction boundary."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from neo4j.exceptions import ServiceUnavailable

from custom_components.ontology.memgraph_client import CannotConnect, MemgraphClient


class _ManagedSession:
    """Small execute_write double that exposes commit/rollback outcomes."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.transaction = MagicMock()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _ManagedSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute_write(self, work: Any) -> Any:
        if self.failure is not None:
            raise self.failure
        try:
            result = await work(self.transaction)
        except BaseException:
            self.rolled_back = True
            raise
        self.committed = True
        return result


def _client_with_session(session: _ManagedSession) -> MemgraphClient:
    client = MemgraphClient("localhost", 7687)
    driver = MagicMock()
    driver.session.return_value = session
    client._driver = driver
    return client


async def test_execute_write_returns_result_and_commits() -> None:
    session = _ManagedSession()
    client = _client_with_session(session)

    async def _work(transaction: object) -> str:
        assert transaction is session.transaction
        return "written"

    assert await client.execute_write(_work) == "written"
    assert session.committed is True
    assert session.rolled_back is False


async def test_execute_write_rolls_back_and_preserves_callback_exception() -> None:
    session = _ManagedSession()
    client = _client_with_session(session)

    async def _work(_transaction: object) -> None:
        raise ValueError("invalid migration step")

    with pytest.raises(ValueError, match="invalid migration step"):
        await client.execute_write(_work)

    assert session.committed is False
    assert session.rolled_back is True


async def test_execute_write_normalizes_driver_availability_failure() -> None:
    client = _client_with_session(_ManagedSession(ServiceUnavailable("bolt unavailable")))

    with pytest.raises(CannotConnect):
        await client.execute_write(MagicMock())


async def test_execute_write_preserves_cancellation() -> None:
    session = _ManagedSession()
    client = _client_with_session(session)

    async def _work(_transaction: object) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await client.execute_write(_work)

    assert session.committed is False
    assert session.rolled_back is True
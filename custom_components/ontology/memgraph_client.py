"""Async Memgraph (Bolt) client wrapper for the Ontology integration.

Memgraph is wire-compatible with the Bolt protocol, so the official ``neo4j``
async driver is used directly rather than introducing an OGM dependency
(research.md §2).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from .const import (
    CONNECTION_TIMEOUT_SECONDS,
    RETRY_INITIAL_DELAY_SECONDS,
    RETRY_MAX_ATTEMPTS,
    RETRY_MAX_DELAY_SECONDS,
)
from .redact import redact_exception

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Raised when the client cannot reach Memgraph (network/refused/timeout)."""


class InvalidAuth(Exception):
    """Raised when Memgraph rejects the supplied credentials."""


class MemgraphClient:
    """Thin async wrapper around the Bolt driver used to reach Memgraph."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
        encrypted: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username or ""
        self._password = password or ""
        self._database = database or None
        self._encrypted = encrypted
        self._driver: AsyncDriver | None = None

    @property
    def _uri(self) -> str:
        scheme = "bolt+s" if self._encrypted else "bolt"
        return f"{scheme}://{self._host}:{self._port}"

    async def connect(self) -> None:
        """Open the driver connection. Idempotent."""
        if self._driver is not None:
            return
        auth = (self._username, self._password) if self._username else None
        self._driver = AsyncGraphDatabase.driver(self._uri, auth=auth)

    async def close(self) -> None:
        """Close the driver connection."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def test_connection(self) -> None:
        """Perform a single bounded-timeout connectivity/auth check.

        Raises ``CannotConnect`` for network-level failures/timeouts and
        ``InvalidAuth`` when the server rejects the supplied credentials.
        Used both by config-flow validation (a single attempt, no retry) and
        as the basis for the ongoing health check (User Story 2).
        """
        try:
            async with asyncio.timeout(CONNECTION_TIMEOUT_SECONDS):
                await self.connect()
                assert self._driver is not None
                await self._driver.verify_connectivity()
        except AuthError as err:
            raise InvalidAuth(redact_exception(err)) from err
        except TimeoutError as err:
            raise CannotConnect("Connection to Memgraph timed out") from err
        except ServiceUnavailable as err:
            raise CannotConnect(redact_exception(err)) from err
        except Exception as err:  # noqa: BLE001 - normalize any driver failure
            raise CannotConnect(redact_exception(err)) from err

    async def run_query(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Run a single Cypher query and return the result records as dicts.

        Bounded by ``CONNECTION_TIMEOUT_SECONDS`` so an unreachable or
        unresponsive host fails fast with ``CannotConnect`` instead of
        hanging indefinitely and wedging the coordinator's serialization
        lock (every subsequent sync would otherwise fail immediately with
        "An ontology sync operation is already in progress" and never
        recover, even after connectivity is restored).
        """
        try:
            async with asyncio.timeout(CONNECTION_TIMEOUT_SECONDS):
                await self.connect()
                assert self._driver is not None
                async with self._driver.session(database=self._database) as session:
                    result = await session.run(query, parameters or {})
                    records = [dict(record) async for record in result]
                    return records
        except AuthError as err:
            raise InvalidAuth(redact_exception(err)) from err
        except TimeoutError as err:
            raise CannotConnect("Connection to Memgraph timed out") from err
        except ServiceUnavailable as err:
            raise CannotConnect(redact_exception(err)) from err

    async def run_query_with_retry(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Run a query with exponential backoff retry (research.md §6).

        Retries transient connectivity failures up to ``RETRY_MAX_ATTEMPTS``
        times, doubling the delay each time up to ``RETRY_MAX_DELAY_SECONDS``.
        Re-raises the last failure once attempts are exhausted so the caller
        (coordinator) can mark the operation failed/pending rather than
        silently dropping it (FR-020).
        """
        delay = RETRY_INITIAL_DELAY_SECONDS
        last_error: Exception | None = None
        for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
            try:
                return await self.run_query(query, parameters)
            except (CannotConnect, ServiceUnavailable, TimeoutError) as err:
                last_error = err
                _LOGGER.debug(
                    "Memgraph query attempt %s/%s failed: %s",
                    attempt,
                    RETRY_MAX_ATTEMPTS,
                    redact_exception(err),
                )
                if attempt == RETRY_MAX_ATTEMPTS:
                    break
                await asyncio.sleep(delay)
                delay = min(delay * 2, RETRY_MAX_DELAY_SECONDS)
        assert last_error is not None
        raise last_error


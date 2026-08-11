"""Async Memgraph (Bolt) client wrapper for the Ontology integration.

Memgraph is wire-compatible with the Bolt protocol, so the official ``neo4j``
async driver is used directly rather than introducing an OGM dependency
(research.md §2).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, Record
from neo4j.exceptions import AuthError, ServiceUnavailable
from neo4j.graph import Node, Path, Relationship

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


def _serialize_value(value: Any) -> Any:
    """Recursively convert a raw Bolt-driver value into a JSON-serializable one.

    ``ontology.query`` lets callers ``RETURN`` whole nodes/relationships/paths
    (e.g. ``MATCH (e:Entity) RETURN e``), which the ``neo4j`` driver decodes
    into ``Node``/``Relationship``/``Path`` graph objects rather than plain
    dicts. Home Assistant's service-response machinery JSON-encodes the
    return value, and those graph objects (along with temporal types like
    ``DateTime``/``Duration``) are not JSON-serializable, which previously
    surfaced to the caller as an opaque "Invalid JSON in response" error.
    """
    if isinstance(value, Node):
        return {
            "element_id": value.element_id,
            "labels": sorted(value.labels),
            "properties": {k: _serialize_value(v) for k, v in value.items()},
        }
    if isinstance(value, Relationship):
        return {
            "element_id": value.element_id,
            "type": value.type,
            "start_node_element_id": (
                value.start_node.element_id if value.start_node is not None else None
            ),
            "end_node_element_id": (
                value.end_node.element_id if value.end_node is not None else None
            ),
            "properties": {k: _serialize_value(v) for k, v in value.items()},
        }
    if isinstance(value, Path):
        return {
            "nodes": [_serialize_value(node) for node in value.nodes],
            "relationships": [_serialize_value(rel) for rel in value.relationships],
        }
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "iso_format"):  # neo4j.time Date/Time/DateTime/Duration
        return value.iso_format()
    return str(value)  # fallback (e.g. spatial Point types)


def _serialize_record(record: Record) -> dict[str, Any]:
    """Convert a driver `Record` into a plain, JSON-serializable dict."""
    return {key: _serialize_value(value) for key, value in record.items()}


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
                    records = [_serialize_record(record) async for record in result]
                    return records
        except AuthError as err:
            raise InvalidAuth(redact_exception(err)) from err
        except TimeoutError as err:
            raise CannotConnect("Connection to Memgraph timed out") from err
        except ServiceUnavailable as err:
            raise CannotConnect(redact_exception(err)) from err

    async def run_query_limited(
        self, query: str, parameters: dict[str, Any] | None, limit: int
    ) -> tuple[list[dict[str, Any]], bool]:
        """Run a query, streaming results and stopping early at `limit` rows.

        Returns `(rows, truncated)` where `truncated` is True if at least
        one additional row existed beyond `limit` (User Story 2, FR-018/
        FR-021). Used by the read-only query service and websocket search so
        an unexpectedly large result set never has to be materialized in
        full before being cut down.
        """
        try:
            async with asyncio.timeout(CONNECTION_TIMEOUT_SECONDS):
                await self.connect()
                assert self._driver is not None
                async with self._driver.session(database=self._database) as session:
                    result = await session.run(query, parameters or {})
                    rows: list[dict[str, Any]] = []
                    truncated = False
                    async for record in result:
                        if len(rows) >= limit:
                            truncated = True
                            break
                        rows.append(_serialize_record(record))
                    return rows, truncated
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


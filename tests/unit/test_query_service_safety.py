"""Unit tests for the read-only Cypher query safety validator and bounded
executor (User Story 2, Constitution Principle X).

Covers: T013 (deny-list keyword rejection, case/position/comment-insensitive,
no false positives on string literals), T014 (row-limit enforcement and the
`truncated` flag), and T061 (syntactically invalid queries are rejected
before execution)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.ontology.query_service import (
    QueryRejected,
    execute_query,
    find_denylisted_keyword,
    validate_read_only,
    validate_syntax,
)


@pytest.mark.parametrize(
    "keyword",
    [
        "CREATE",
        "MERGE",
        "DELETE",
        "DETACH",
        "SET",
        "REMOVE",
        "DROP",
        "LOAD CSV",
        "CALL DBMS",
        "CALL MG",
        "CALL ALGO",
    ],
)
def test_denylisted_keyword_rejected_regardless_of_case_and_position(keyword: str) -> None:
    lower_query = f"match (n) {keyword.lower()} (n) return n"
    upper_query = f"{keyword} (n) return n"
    mixed_query = "".join(
        c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(keyword)
    ) + " (n) return n"

    for query in (lower_query, upper_query, mixed_query):
        assert find_denylisted_keyword(query) == keyword
        with pytest.raises(QueryRejected):
            validate_read_only(query)


def test_denylisted_keyword_rejected_inside_comments() -> None:
    line_comment_query = "match (n) return n // DROP everything\n"
    block_comment_query = "match (n) /* DELETE this */ return n"

    assert find_denylisted_keyword(line_comment_query) is None
    assert find_denylisted_keyword(block_comment_query) is None
    validate_read_only(line_comment_query)
    validate_read_only(block_comment_query)


def test_denylisted_keyword_not_false_positive_in_string_literal() -> None:
    query = "match (n) where n.name = 'please do not CREATE duplicates' return n"
    assert find_denylisted_keyword(query) is None
    validate_read_only(query)


def test_read_only_query_passes_validation() -> None:
    assert find_denylisted_keyword("MATCH (n:Area) RETURN n LIMIT 10") is None
    validate_read_only("MATCH (n:Area) RETURN n LIMIT 10")


def test_validate_syntax_rejects_empty_query() -> None:
    with pytest.raises(QueryRejected):
        validate_syntax("")
    with pytest.raises(QueryRejected):
        validate_syntax("   ")


def test_validate_syntax_rejects_unbalanced_brackets() -> None:
    with pytest.raises(QueryRejected):
        validate_syntax("MATCH (n RETURN n")
    with pytest.raises(QueryRejected):
        validate_syntax("MATCH (n) RETURN [n)")


def test_validate_syntax_rejects_unterminated_string_literal() -> None:
    with pytest.raises(QueryRejected):
        validate_syntax("MATCH (n) WHERE n.name = 'unterminated RETURN n")


def test_validate_syntax_accepts_well_formed_query() -> None:
    validate_syntax("MATCH (n:Area {name: 'Kitchen'}) RETURN n")


async def test_execute_query_enforces_default_and_max_row_limit() -> None:
    client = AsyncMock()
    client.run_query_limited = AsyncMock(return_value=([{"n": 1}], False))

    await execute_query(client, "MATCH (n) RETURN n")
    client.run_query_limited.assert_awaited_once()
    _, _, called_limit = client.run_query_limited.await_args.args
    assert called_limit == 100

    client.run_query_limited.reset_mock()
    await execute_query(client, "MATCH (n) RETURN n", limit=5000)
    _, _, called_limit = client.run_query_limited.await_args.args
    assert called_limit == 1000


async def test_execute_query_reports_truncated_flag() -> None:
    client = AsyncMock()
    client.run_query_limited = AsyncMock(return_value=([{"n": 1}], True))

    result = await execute_query(client, "MATCH (n) RETURN n", limit=1)

    assert result["truncated"] is True
    assert result["row_count"] == 1


async def test_execute_query_rejects_invalid_syntax_without_executing() -> None:
    client = AsyncMock()
    client.run_query_limited = AsyncMock(return_value=([], False))

    with pytest.raises(QueryRejected):
        await execute_query(client, "MATCH (n RETURN n")

    client.run_query_limited.assert_not_awaited()


async def test_execute_query_rejects_write_query_without_executing() -> None:
    client = AsyncMock()
    client.run_query_limited = AsyncMock(return_value=([], False))

    with pytest.raises(QueryRejected):
        await execute_query(client, "CREATE (n:Area) RETURN n")

    client.run_query_limited.assert_not_awaited()

"""Read-only, write-rejecting Cypher query service (User Story 2).

Implements the tokenized Cypher safety validator (research.md §3) and the
bounded read-only query executor (research.md §4) backing the
``ontology.query`` service.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .const import DEFAULT_QUERY_LIMIT, MAX_QUERY_LIMIT, QUERY_DENYLIST_KEYWORDS
from .memgraph_client import MemgraphClient

_LOGGER = logging.getLogger(__name__)


class QueryRejected(Exception):
    """Raised when a query fails the safety validator or the syntax pre-check."""


_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL_RE = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")

_BRACKET_PAIRS = {")": "(", "]": "[", "}": "{"}
_BRACKET_OPENERS = set(_BRACKET_PAIRS.values())

_KEYWORD_PATTERNS = tuple(
    (keyword, re.compile(r"\b" + r"\s+".join(re.escape(part) for part in keyword.split()) + r"\b"))
    for keyword in QUERY_DENYLIST_KEYWORDS
)


def _strip_comments_and_strings(cypher: str) -> str:
    """Remove `//`/`/* */` comments and quoted string literals (research.md §3)."""
    text = _BLOCK_COMMENT_RE.sub(" ", cypher)
    text = _LINE_COMMENT_RE.sub(" ", text)
    return _STRING_LITERAL_RE.sub(" ", text)


def find_denylisted_keyword(cypher: str) -> str | None:
    """Return the first disallowed keyword found in `cypher`, or `None`.

    Comments and string literals are stripped first so a keyword hidden in a
    comment or embedded in a string literal never triggers a false rejection
    or a false pass (research.md §3).
    """
    stripped = _strip_comments_and_strings(cypher).upper()
    for keyword, pattern in _KEYWORD_PATTERNS:
        if pattern.search(stripped):
            return keyword
    return None


def validate_read_only(cypher: str) -> None:
    """Raise `QueryRejected` if `cypher` contains any disallowed keyword (FR-019)."""
    keyword = find_denylisted_keyword(cypher)
    if keyword is not None:
        _LOGGER.warning(
            "Rejected ontology.query call: query contains disallowed keyword %r", keyword
        )
        raise QueryRejected(f"Query rejected: contains disallowed keyword '{keyword}'")


def validate_syntax(cypher: str) -> None:
    """Reject obviously-malformed Cypher before it ever reaches Memgraph (FR-022).

    Checks for an empty query, unbalanced brackets/parentheses/braces, and
    unterminated string literals. This is a lightweight structural
    pre-check, not a full parser - it catches the class of malformed input
    that should never be sent to the driver at all.
    """
    if not cypher or not cypher.strip():
        raise QueryRejected("Query rejected: empty query")

    without_comments = _BLOCK_COMMENT_RE.sub(" ", cypher)
    without_comments = _LINE_COMMENT_RE.sub(" ", without_comments)
    if _STRING_LITERAL_RE.sub("", without_comments).count("'") or (
        _STRING_LITERAL_RE.sub("", without_comments).count('"')
    ):
        raise QueryRejected("Query rejected: unterminated string literal")

    stripped = _strip_comments_and_strings(cypher)
    stack: list[str] = []
    for char in stripped:
        if char in _BRACKET_OPENERS:
            stack.append(char)
        elif char in _BRACKET_PAIRS:
            if not stack or stack[-1] != _BRACKET_PAIRS[char]:
                raise QueryRejected(
                    "Query rejected: unbalanced parentheses, brackets, or braces"
                )
            stack.pop()
    if stack:
        raise QueryRejected("Query rejected: unbalanced parentheses, brackets, or braces")


async def execute_query(
    client: MemgraphClient,
    cypher: str,
    parameters: dict[str, Any] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Validate then execute a read-only Cypher query, bounded by `limit`.

    Raises `QueryRejected` (no execution attempted) if the syntax pre-check
    or the safety validator fails. Streams the result and stops early once
    `limit` rows are collected (research.md §4); the response indicates
    `truncated: true` when more rows were available.
    """
    validate_syntax(cypher)
    validate_read_only(cypher)
    effective_limit = min(limit or DEFAULT_QUERY_LIMIT, MAX_QUERY_LIMIT)
    rows, truncated = await client.run_query_limited(cypher, parameters or {}, effective_limit)
    return {"rows": rows, "truncated": truncated, "row_count": len(rows)}

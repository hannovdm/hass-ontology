"""Contract tests for deterministic Home Assistant dependencies."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_runtime_requirements_are_exact_and_synchronized() -> None:
    manifest = json.loads(
        (ROOT / "custom_components" / "ontology" / "manifest.json").read_text()
    )
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert manifest["requirements"] == ["neo4j==6.2.0"]
    assert pyproject["project"]["dependencies"] == manifest["requirements"]
"""Windows-only stub for the POSIX `resource` module.

Home Assistant core's `homeassistant.util.resource` unconditionally imports
`resource` (used to raise the open-file-descriptor soft limit at process
startup), which does not exist on Windows. This test-only stub lets
`pytest-homeassistant-custom-component` be imported on Windows dev machines.
"""

from __future__ import annotations

RLIMIT_NOFILE = 7


def getrlimit(resource_id: int) -> tuple[int, int]:
    """Return a fixed, generous (soft, hard) limit pair."""
    return (4096, 4096)


def setrlimit(resource_id: int, limits: tuple[int, int]) -> None:
    """No-op stand-in for `resource.setrlimit`."""
    return None

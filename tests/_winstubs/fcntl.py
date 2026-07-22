"""Windows-only stub for the POSIX `fcntl` module.

Home Assistant core's `homeassistant.runner` module unconditionally imports
`fcntl` (used for a single-instance advisory file lock), which does not
exist on Windows. This test-only stub lets `pytest-homeassistant-custom-component`
be imported on Windows dev machines; it is never exercised by our test
suite's actual behavior. Not used in CI (which runs on Linux, where the real
stdlib `fcntl` is used instead since this directory is not on `sys.path` there).
"""

from __future__ import annotations

LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def flock(fd: int, operation: int) -> None:
    """No-op stand-in for `fcntl.flock` (advisory locking not needed in tests)."""
    return None

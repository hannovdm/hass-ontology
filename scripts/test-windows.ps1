# Windows dev-machine test runner.
#
# Home Assistant core / pytest-homeassistant-custom-component assume a POSIX
# host (`fcntl`, `resource` stdlib modules). `tests/_winstubs/` provides no-op
# stand-ins for those two modules; putting that directory first on
# PYTHONPATH lets the test suite import and run on Windows.
#
# This script is Windows-only dev convenience. CI (Linux) runs `pytest`
# directly with no special setup, since the real `fcntl`/`resource` modules
# exist there and this directory is never added to `sys.path`.
#
# TC_HOST=127.0.0.1 works around a Docker Desktop for Windows quirk where
# testcontainers' Ryuk "Reaper" connects to the literal host "localhost"
# instead of a resolved IP. pytest-homeassistant-custom-component enables
# pytest-socket with an allow-list of only "127.0.0.1" (not "localhost"),
# so without this override, the Reaper connection is blocked and every
# integration test (tests/integration/) fails at fixture setup.
#
# Usage: .\scripts\test-windows.ps1 [pytest args...]

$env:PYTHONPATH = "$PSScriptRoot\..\tests\_winstubs"
$env:TC_HOST = "127.0.0.1"
& "$PSScriptRoot\..\.venv\Scripts\python.exe" -m pytest @args

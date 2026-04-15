# apps/backend/test_backend_cli.py
"""
Integration tests for backend.py CLI lifecycle (SIDE-01, SIDE-02).

Spawns backend.py as a subprocess, exercises the ready-file contract,
verifies clean shutdown. The release workflow runs an additional copy
of these tests against dist/backend-*.exe.
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests
import socketio  # python-socketio[client]


BACKEND_PY = Path(__file__).parent / "backend.py"
DEV_TIMEOUT_S = 10.0
SHUTDOWN_TIMEOUT_S = 2.0


@pytest.fixture(scope="session", autouse=True)
def _ensure_lolalytics_api_installed():
    """Fail fast with a helpful message if the editable package isn't installed.

    Running ``python backend.py`` from the test requires ``lolalytics_api`` to
    be importable from site-packages. See start.ps1 line 78 for the dev-setup
    pattern (``pip install -e .`` from apps/backend/).
    """
    if importlib.util.find_spec("lolalytics_api") is None:
        pytest.skip(
            "lolalytics_api not installed. Run `pip install -e .` from "
            "counterpick-app/apps/backend/ before running these tests."
        )


def _free_port() -> int:
    """Bind 127.0.0.1:0 and return the OS-assigned port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _spawn_backend(port: int, ready_file: Path) -> subprocess.Popen:
    """Spawn backend.py with given port and ready-file path."""
    return subprocess.Popen(
        [
            sys.executable,
            str(BACKEND_PY),
            "--port", str(port),
            "--ready-file", str(ready_file),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # CREATE_NEW_PROCESS_GROUP so we can later send CTRL_BREAK_EVENT.
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt" else 0
        ),
        cwd=BACKEND_PY.parent,
    )


def _wait_for_ready_file(
    path: Path, timeout_s: float, required_keys: set[str] | None = None
) -> dict:
    """Poll the ready-file until it contains the expected contract.

    When ``required_keys`` is given, poll until the parsed JSON contains ALL of
    those keys — this lets callers distinguish a pre-existing stale file from
    a freshly-written one (D-05 stale-cleanup test).
    """
    required = required_keys if required_keys is not None else {"port", "pid", "ready_at"}
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                # Atomic-write contract should prevent this; tolerate one retry.
                time.sleep(0.05)
                continue
            if required.issubset(payload.keys()):
                return payload
        time.sleep(0.05)
    raise TimeoutError(f"ready-file did not appear within {timeout_s}s: {path}")


def _shutdown(proc: subprocess.Popen) -> int:
    """Send graceful shutdown signal and wait for exit."""
    if os.name == "nt":
        proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
    else:
        proc.send_signal(signal.SIGTERM)
    try:
        return proc.wait(timeout=SHUTDOWN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2.0)
        pytest.fail(f"backend did not exit within {SHUTDOWN_TIMEOUT_S}s")


def test_ready_file_contract(tmp_path: Path) -> None:
    """SIDE-01 + SIDE-02: ready-file exists, contains JSON with matching pid.

    Also verifies that ``/api/health`` returns a JSON body containing a
    ``version`` field — this is the load-bearing Plan 02 contract that
    Plan 03's assertion depends on (revision W-1).
    """
    port = _free_port()
    ready = tmp_path / "ready.json"
    proc = _spawn_backend(port, ready)
    try:
        payload = _wait_for_ready_file(ready, DEV_TIMEOUT_S)
        assert payload["port"] == port
        assert payload["pid"] == proc.pid
        assert "ready_at" in payload
        # Verify health endpoint is actually live (probe-isn't-lying check)
        r = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
        assert r.status_code == 200
        body = r.json()
        # W-1: Plan 02 ships `version` as a load-bearing key — assert it.
        assert "version" in body, f"version field missing: {body}"
    finally:
        rc = _shutdown(proc)
        # rc == 0 on POSIX SIGTERM; -signal on POSIX kill; 1/255 on Windows
        # CTRL_BREAK_EVENT depending on Flask shutdown handler. Don't assert
        # exact value — assert non-hang.
        _ = rc


def test_stale_ready_file_is_cleaned(tmp_path: Path) -> None:
    """D-05: pre-existing ready-file is deleted before fresh probe."""
    port = _free_port()
    ready = tmp_path / "ready.json"
    ready.write_text('{"stale": true}', encoding="utf-8")
    proc = _spawn_backend(port, ready)
    try:
        payload = _wait_for_ready_file(ready, DEV_TIMEOUT_S)
        assert "stale" not in payload
        assert payload["pid"] == proc.pid
    finally:
        _shutdown(proc)


def test_socketio_round_trip(tmp_path: Path) -> None:
    """SIDE-04 partial: Socket.IO client connects, server responds.

    This mirrors the harder-to-build hidden-imports test that the release
    workflow runs against dist/backend.exe. Here we run against python.exe
    to confirm the contract works with the unbundled code first.
    """
    port = _free_port()
    ready = tmp_path / "ready.json"
    proc = _spawn_backend(port, ready)
    try:
        _wait_for_ready_file(ready, DEV_TIMEOUT_S)
        client = socketio.Client(logger=False, engineio_logger=False)
        client.connect(f"http://127.0.0.1:{port}", wait_timeout=5)
        assert client.connected
        client.disconnect()
    finally:
        _shutdown(proc)

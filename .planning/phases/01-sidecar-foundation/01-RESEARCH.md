# Phase 1: Sidecar Foundation — Research

**Researched:** 2026-04-14
**Domain:** PyInstaller 6.19 onefile build of a Flask + Flask-SocketIO sidecar on Windows; CLI lifecycle protocol (argparse + ready-file + in-process health probe); resource resolution via `_MEIPASS` and `platformdirs`; CI smoke test against the built `.exe`.
**Confidence:** HIGH

## Summary

Phase 1 introduces three artifacts — a CLI delta to `backend.py`, a new `resources.py` helper, and a `backend.spec` — plus one CI workflow and one pytest integration test. All five `SIDE-*` requirements collapse into work that is mechanically simple but pitfall-dense: PyInstaller's onefile mode hides three classes of failure (missing hidden imports, missing `certifi` data files, and `__file__` paths in a `_MEIPASS` temp directory) that all manifest only AFTER `pyinstaller --clean --noconfirm` completes successfully and only on a machine without a Python dev environment. The single most important architectural decision is the **probe-thread-then-blocking-`socketio.run`** pattern: because `socketio.run()` blocks the calling thread for the lifetime of the server, the probe MUST run on a background thread spawned BEFORE `socketio.run()` is called. Inverting that order deadlocks (probe never reaches the server) and is the most common implementation mistake.

The CONTEXT.md locked 23 decisions covering CLI shape, ready-file protocol, spec contents, hidden-import seed, exclude list, dependency additions, and CI gates. Research below converts those decisions into concrete, copy-paste skeletons the planner can task against.

**Primary recommendation:** Land four files in this order — (1) `apps/backend/src/resources.py` (no dependencies); (2) `apps/backend/backend.spec` (no Python code dependency); (3) `apps/backend/backend.py` `main()` rewrite (depends on `resources.py`); (4) `apps/backend/test_backend_cli.py` (depends on the new `main()`). CI workflow is added last and gates everything via the built `.exe`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**CLI & Health Probe**
- **D-01:** `backend.py` uses stdlib `argparse` for `--port <int>` (default 5000 for native dev) and `--ready-file <path>` (default None). Also expose `--cache-dir <path>` (default `platformdirs.user_cache_dir("lol-draft-analyzer")`) and `--log-dir <path>` (default `platformdirs.user_log_dir("lol-draft-analyzer")`) so Phase 3 / tests can override without env vars.
- **D-02:** Ready-file protocol: Tauri (or test harness) provides a writable path. Python MUST NOT create the ready-file until an in-process HTTP `GET http://127.0.0.1:<port>/api/health` returns 200. This verifies the Flask threaded server has actually entered `accept()`, not merely that `socketio.init_app()` completed.
- **D-03:** Health-probe implementation: a new `/api/health` route returning `{"status": "ok", "version": "<app-version>"}`. A background probe thread (started before `socketio.run`) polls `127.0.0.1:<port>/api/health` on a 50 ms interval with a 5 s overall timeout; on first 200 it writes the ready-file atomically (`open(path + ".tmp", "w") ... os.replace(...)`). On timeout the process exits non-zero.
- **D-04:** Ready-file content is the JSON `{"port": <n>, "pid": <pid>, "ready_at": "<iso8601>"}`.
- **D-05:** On startup, if the ready-file path already exists, delete it first.

**PyInstaller Spec (`apps/backend/backend.spec`)**
- **D-06:** `--onefile` output; output name `backend-x86_64-pc-windows-msvc.exe` to match Tauri sidecar naming conventions.
- **D-07:** `upx=False` at spec level AND enforced by a CI grep check in the release workflow.
- **D-08:** Initial `hiddenimports` seed: `['engineio.async_drivers.threading', 'httpx.socks', 'websocket', 'charset_normalizer', 'urllib3', 'certifi']`. Expand iteratively via first CI failure — spec comments document the discovery process.
- **D-09:** `excludes=['supabase', 'gotrue', 'postgrest', 'realtime', 'storage3', 'supabase_functions', 'supabase_auth']`.
- **D-10:** `certifi` data files bundled via `datas=[(certifi.where(), 'certifi')]` and `SSL_CERT_FILE` env var set on startup to the resolved bundled path via the `resources.py` helper.
- **D-11:** No binary-file embedding of `cache_data.json` or other runtime-mutable files. Static assets remain bundled via `datas=[...]`.
- **D-12:** Build command: `pyinstaller --clean --noconfirm apps/backend/backend.spec`.

**Resource Resolution Helper (`apps/backend/src/resources.py`)**
- **D-13:** New module exporting `bundled_resource()`, `user_cache_dir()`, `user_log_dir()`, `user_data_dir()`. Uses `sys._MEIPASS` when frozen, `__file__`-anchored fallback in dev mode. `platformdirs` used with directory auto-create.
- **D-14:** No `__file__`-relative path resolution or `os.getcwd()` remains in the runtime code path. Grep-enforced.
- **D-15:** `LOL_DRAFT_APP_NAME = "lol-draft-analyzer"` lives in `resources.py` as a mutable placeholder (Phase 3 will swap it for the finalized Tauri identifier).

**Dependencies & Python Version**
- **D-16:** CI Python version: **3.12** (pinned via `actions/setup-python@v5` with `python-version: "3.12.x"`).
- **D-17:** PyInstaller installed in CI via `pip install pyinstaller==6.19.0` — version pinned.
- **D-18:** Add `platformdirs>=4.0.0` to `apps/backend/requirements.txt`.
- **D-19:** **Do not** remove `supabase-py` from `requirements.txt` in Phase 1.

**CI Smoke Test**
- **D-20:** New pytest integration test `test_backend_cli.py`: spawns `python backend.py --port 0 --ready-file <tmp>`, waits up to 10 s for ready-file, asserts JSON content matches pid, then sends SIGTERM and asserts clean exit within 2 s.
- **D-21:** Release-workflow smoke test launches the BUILT `backend.exe`, verifies Socket.IO round-trip via a Python test client, and performs one HTTPS `GET https://example.com/`.
- **D-22:** VirusTotal scan: optional CI step gated on `VT_API_KEY` secret. Skipped with warning if absent; fails if detections > 3 when present. **Not blocking for Phase 1 acceptance.**
- **D-23:** Smoke test runs on `windows-latest` GitHub runner.

### Claude's Discretion

- Exact probe interval inside `/api/health` polling loop (50 ms is the documented default; bump to 25 ms if CI flakes).
- Retry structure inside the CI smoke test (number of retries around the subprocess spawn, etc.).
- Whether to collapse `user_cache_dir` / `user_log_dir` / `user_data_dir` into a single helper with a `kind=` argument vs. three separate functions.
- Exact `log` level/handlers setup in `backend.py` initialization (spec says structured + daily-rotating, but the concrete `logging.handlers.TimedRotatingFileHandler` configuration is planner's call).

### Deferred Ideas (OUT OF SCOPE)

- **Seed dataset for offline-first-run** — bundling ~1–5 MB snapshot. Deferred to v1.1.
- **Nuitka migration** as PyInstaller alternative — only if AV friction becomes dominant after launch.
- **Rebuilding the PyInstaller bootloader from source** — deferred to Phase 6 / post-launch.
- **VirusTotal API hard-gate in CI** — Phase 4 decision; Phase 1 wires the integration but keeps threshold advisory.
- **Moving log-handler / LCU-auth redaction logic into Phase 1** — deferred to Phase 3 (LOG-01..05). Phase 1 lands only the bare `TimedRotatingFileHandler`.
- **Finalizing `{bundle_id}` to a concrete identifier** — Phase 3 concern (TAURI-01).

### Anti-Decisions (explicitly NOT done in this phase)

- **N-01:** No Tauri-side code, no Rust.
- **N-02:** No `--cache-dir` being wired up to `json_repo.py` yet (Phase 2). Phase 1 adds the CLI flag and the `resources.user_cache_dir()` helper, but nothing reads from the cache directory yet.
- **N-03:** No removal of `supabase_repo.py` imports from `backend.py`. Phase 1 ships with Supabase code path intact.
- **N-04:** No seed-dataset bundling.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **SIDE-01** | `backend.py` accepts `--port <int>` and `--ready-file <path>` and binds Flask-SocketIO on `127.0.0.1:<port>` | §"backend.py CLI Skeleton" — concrete `argparse` setup, `socketio.run(host='127.0.0.1', port=args.port)` in `main()` wrapper |
| **SIDE-02** | Backend writes ready-file only AFTER in-process HTTP health probe confirms Flask is accepting connections | §"Ready-File Protocol & Probe-Thread Pattern" — pre-`socketio.run` thread spawn, atomic write via `os.replace`, deadlock-free order |
| **SIDE-03** | PyInstaller `backend.spec` produces single-file `backend.exe` with `upx=False`, hidden imports, `certifi` data files, supabase excluded | §"backend.spec Skeleton" — full block layout with verified hidden-import seed and exclude list |
| **SIDE-04** | Built `backend.exe` passes CI smoke test: standalone launch, Socket.IO round-trip, HTTPS CDN fetch, VirusTotal ≤ 3 | §"CI Workflow YAML" + §"Integration Test Skeleton" — windows-latest job, python-socketio test client, HTTPS GET probe |
| **SIDE-05** | Resource resolution uses `sys._MEIPASS` for bundled read-only files and `platformdirs.user_data_dir()` for read/write — no hardcoded `__file__` paths | §"resources.py Skeleton" — `bundled_resource()` with `getattr(sys, '_MEIPASS', __file__-fallback)` + `platformdirs` wrappers with auto-mkdir |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

CLAUDE.md is the project-level rollup of PROJECT.md, codebase/STACK.md, codebase/CONVENTIONS.md, and codebase/ARCHITECTURE.md. Directives that constrain Phase 1:

| Constraint | Source | Impact on Phase 1 |
|------------|--------|-------------------|
| Windows-only v1; no code signing | PROJECT.md / Constraints | CI runs only on `windows-latest`; AV mitigation is `upx=False` + hash publish + future README walkthrough |
| Tech stack locked: Flask + Flask-SocketIO; PyInstaller for sidecar | PROJECT.md / Constraints | Do NOT switch to FastAPI, eventlet, or gevent. `async_mode='threading'` is locked. |
| Minimum-invasive change | PROJECT.md / Constraints | `backend.py` keeps existing Supabase imports; Phase 1 only adds the `main()` wrapper, ready-file plumbing, and `--port` plumbing |
| Installer size ≤ 100 MB | PROJECT.md / Constraints | PyInstaller `excludes=[...]` carries weight here — every Supabase transitive dep keeps the bundle smaller |
| Privacy: no telemetry, no network beyond CDN + LCU | PROJECT.md / Constraints | The Phase 1 CI smoke test's HTTPS GET to verify `certifi` should target a stable benign URL (e.g. `https://example.com/`), NOT a real telemetry endpoint |
| `snake_case` for Python files; 4-space indent; double-quote docstrings; `:param:` / `:return:` | CONVENTIONS.md | New `resources.py`, new `main()` in `backend.py`, new `test_backend_cli.py` follow these |
| Python type hints throughout | CONVENTIONS.md | All new functions in `resources.py` and `backend.py` `main()` should have type hints |
| Print-based logging is the existing convention; structured logging with `[MODULE]` prefixes | CONVENTIONS.md | Phase 1 introduces `logging.handlers.TimedRotatingFileHandler` (per §147 of CONTEXT) — keep `print()` calls for human-readable startup banner; route everything else via `logging` |
| GSD workflow enforcement | CLAUDE.md / GSD section | All Phase 1 work happens inside `/gsd-execute-phase 1` |
| `host='127.0.0.1'` (not `0.0.0.0`) | PITFALLS.md §Sec-7 | Existing `socketio.run(... host='0.0.0.0' ...)` MUST flip to `127.0.0.1` in the new `main()` wrapper. Security-critical: leaving `0.0.0.0` exposes the LCU bridge over LAN. |

## Standard Stack

### Core (NEW for Phase 1)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pyinstaller` | `6.19.0` | Bundle Python + Flask + Socket.IO into a single Windows `.exe` | De facto standard; spec-file model gives precise control over hidden imports and UPX opt-out. Released 2026-02-14. `[VERIFIED: PyPI + .planning/research/STACK.md]` |
| `platformdirs` | `>= 4.0.0` (latest 4.9.4) | Cross-platform `user_cache_dir`, `user_log_dir`, `user_data_dir` with `ensure_exists` parameter (added in 4.0) | Standard Python package for OS-correct app data paths. On Windows resolves to `%LOCALAPPDATA%\<name>\Cache`, `%LOCALAPPDATA%\<name>\Logs`, `%APPDATA%\<name>\Data`. `[VERIFIED: PyPI 4.9.4 latest, 4.0+ has ensure_exists]` |
| `certifi` | (already pinned via `requests`/`urllib3`) | TLS root CA bundle that ships with `requests`; mandatory for HTTPS to work in PyInstaller bundle | Required to override Windows certificate store quirks. `[VERIFIED: PITFALLS.md Pitfall #7 + PyInstaller #7229]` |
| `python-socketio[client]` | match server version (currently `>= 5.9.0`); install matching `socketio` package on the test side | Test-side Socket.IO client for the round-trip integration test | Server↔client protocol compatibility is by minor version; pin client to same minor. `[VERIFIED: python-socketio docs intro.rst]` |

### Supporting (already in repo, used by Phase 1)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `flask` | (existing) | Web framework | All routes |
| `flask-socketio` | `>= 5.3.0` | WebSocket layer | `socketio.run()` in `main()` |
| `flask-cors` | (existing) | CORS for frontend dev | Existing — no Phase 1 changes |
| `python-socketio` | `>= 5.9.0` | Underlying Socket.IO server | Existing |
| `requests` | (existing, `>= 2.32`) | In-process probe HTTP GET to `/api/health` | New `_probe_health()` thread |
| `python-dotenv` | (existing) | `.env` loading for dev mode | Existing — `.env` ignored in frozen mode |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `requests` for in-process probe | `urllib.request` (stdlib) | Saves zero MB (already a dep). `requests` is already imported in `backend.py`; consistency wins. |
| `platformdirs` | `appdirs` (deprecated predecessor) | `appdirs` has been unmaintained since 2020. `platformdirs` is the active fork with identical API. |
| Three separate helpers (`user_cache_dir`, `user_log_dir`, `user_data_dir`) | Single `app_dir(kind: Literal["cache","log","data"])` | Three named functions read better at the call site (`resources.user_log_dir() / "backend.log"`) and grep more clearly. CONTEXT-D-13 explicitly lists three; planner has discretion to collapse. |
| `argparse` (stdlib) | `click` / `typer` | Adds a dep; CONTEXT-D-01 locks stdlib argparse for zero-dep + matches existing conventions. |
| Threading-based probe | Subprocess-based probe | Threading is in-process so it can `os._exit(1)` on timeout cleanly; subprocess adds another moving part. |

**Installation:**

```bash
# In CI (release workflow), NOT in runtime requirements.txt:
pip install pyinstaller==6.19.0

# In apps/backend/requirements.txt — ADD:
platformdirs>=4.0.0

# python-socketio[client] for the integration test — pin to server version
# (read live from the existing requirement, currently >=5.9.0)
# ADD to apps/backend/requirements.txt for the test extra OR install ad-hoc in CI:
pip install "python-socketio[client]>=5.9.0,<6"
```

**Version verification (run before plan-freeze):**

```bash
pip index versions pyinstaller    # confirm 6.19.0 is current latest
pip index versions platformdirs   # confirm 4.x line
pip index versions python-socketio # confirm minor matches server
```

## Architecture Patterns

### Recommended File Layout (Phase 1 additions in **bold**)

```
counterpick-app/apps/backend/
├── backend.py                       # MODIFIED: argparse + main() + probe thread
├── backend.spec                     # NEW: PyInstaller spec
├── requirements.txt                 # MODIFIED: + platformdirs>=4.0.0
├── pyproject.toml                   # MODIFIED: optional [test] extra includes python-socketio[client]
├── test_backend_cli.py              # NEW: pytest integration test
├── src/
│   ├── resources.py                 # NEW: _MEIPASS + platformdirs helpers
│   └── lolalytics_api/              # existing, untouched
└── ...

.github/workflows/
└── build-smoke.yml                  # NEW: BUILD-05 partial — build on every push to main
```

### Pattern 1: backend.py CLI Skeleton

**What:** Convert the bottom-of-file `if __name__ == '__main__':` block into a `main()` function that parses args, configures logging, spawns the probe thread, and calls `socketio.run`. Keep the existing module-level `app = Flask(__name__)`, `socketio = SocketIO(app, ...)` exactly as they are — they are imported by the existing route decorators above.

**When to use:** Always — this is the SIDE-01 implementation.

**Concrete sketch (canonical):**

```python
# bottom of backend.py — replaces existing if __name__ == '__main__': block
import argparse
import json
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.resources import (
    LOL_DRAFT_APP_NAME,
    bundled_resource,
    user_cache_dir,
    user_log_dir,
)


def _configure_logging(log_dir: Path) -> None:
    """
    Set up daily-rotating file logging.

    :param log_dir: Directory to write backend-<YYYY-MM-DD>.log into.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "backend.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _atomic_write_ready_file(path: Path, payload: dict) -> None:
    """
    Write `payload` to `path` atomically via temp + os.replace.

    :param path: Final destination of the ready-file.
    :param payload: JSON-serializable dict.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)  # atomic on Windows + POSIX


def _probe_health_then_signal_ready(
    port: int,
    ready_file: Path | None,
    interval_s: float = 0.05,
    timeout_s: float = 5.0,
) -> None:
    """
    Background thread: poll /api/health until 200 or timeout.

    On 200, write the ready-file (if requested) and return.
    On timeout, log + os._exit(1) — non-zero exit propagates to Tauri / CI.

    :param port: Port the Flask server is binding to.
    :param ready_file: Path to write the ready JSON into; None to skip.
    :param interval_s: Polling interval.
    :param timeout_s: Total budget for the probe.
    """
    deadline = time.monotonic() + timeout_s
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            r = requests.get(url, timeout=0.5)
            if r.status_code == 200:
                if ready_file is not None:
                    payload = {
                        "port": port,
                        "pid": os.getpid(),
                        "ready_at": datetime.now(timezone.utc).isoformat(),
                    }
                    _atomic_write_ready_file(ready_file, payload)
                logging.getLogger(__name__).info(
                    "[READY] port=%d pid=%d", port, os.getpid()
                )
                return
        except requests.RequestException:
            pass
        time.sleep(interval_s)
    logging.getLogger(__name__).error(
        "[READY] /api/health did not return 200 within %.1fs", timeout_s
    )
    # Force-exit; cannot return normally because socketio.run is blocking the main thread.
    os._exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="backend",
        description="LoL Draft Analyzer backend sidecar.",
    )
    parser.add_argument(
        "--port", type=int, default=5000,
        help="TCP port to bind 127.0.0.1 on (default: 5000 for native dev).",
    )
    parser.add_argument(
        "--ready-file", type=Path, default=None,
        help="Path to write JSON ready-marker after /api/health returns 200.",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=None,
        help="Override platformdirs.user_cache_dir().",
    )
    parser.add_argument(
        "--log-dir", type=Path, default=None,
        help="Override platformdirs.user_log_dir().",
    )
    args = parser.parse_args()

    log_dir = args.log_dir or user_log_dir()
    _configure_logging(log_dir)

    # Make bundled certifi the source of truth for SSL — fixes Pitfall #7.
    cacert = bundled_resource("certifi/cacert.pem")
    if cacert.exists():
        os.environ.setdefault("SSL_CERT_FILE", str(cacert))
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(cacert))

    # D-05: idempotent cleanup of stale ready-file
    if args.ready_file is not None and args.ready_file.exists():
        args.ready_file.unlink()

    # D-02 + D-03: probe thread MUST be spawned BEFORE socketio.run
    # because socketio.run blocks the main thread until shutdown.
    probe = threading.Thread(
        target=_probe_health_then_signal_ready,
        args=(args.port, args.ready_file),
        name="health-probe",
        daemon=True,
    )
    probe.start()

    # Bind 127.0.0.1 explicitly — never 0.0.0.0 (PITFALLS.md security row).
    # debug=False because the Werkzeug reloader spawns a child process that
    # confuses the ready-file protocol and PyInstaller --onefile.
    socketio.run(
        app,
        host="127.0.0.1",
        port=args.port,
        debug=False,
        allow_unsafe_werkzeug=True,  # Flask-SocketIO >=5 demands this in production
    )


if __name__ == "__main__":
    main()
```

**Key invariants this skeleton enforces:**

1. **Probe thread spawned BEFORE `socketio.run`** — inverting causes deadlock (probe never reaches a server that hasn't started yet, but `socketio.run` blocks the main thread so probe-from-main-thread-after-run is impossible).
2. **Probe thread is a `daemon=True`** — so when `socketio.run` exits (Ctrl+C / SIGTERM), the probe doesn't keep the process alive.
3. **`os._exit(1)` on probe timeout** — `sys.exit(1)` would only kill the probe thread (raises `SystemExit`, caught by thread machinery); `os._exit` terminates the whole process.
4. **`debug=False`** — Werkzeug's auto-reloader spawns a subprocess that breaks both PyInstaller `--onefile` AND the ready-file protocol.
5. **`allow_unsafe_werkzeug=True`** — Flask-SocketIO 5+ raises `RuntimeError` in production mode without it; for a single-user localhost desktop sidecar this is the correct choice.
6. **`host="127.0.0.1"`** — never `0.0.0.0`. The existing code is `host='0.0.0.0'`; this MUST flip.
7. **`SSL_CERT_FILE` is set BEFORE any `requests.get(...)` call elsewhere in the import graph** — so the environment is correct by the time `requests` imports `urllib3` and reads its CA bundle. The probe thread itself would fail on HTTPS otherwise (it doesn't, because it's HTTP to localhost, but other code paths in `backend.py` do hit HTTPS).

`[CITED: PyInstaller #7229; Flask-SocketIO #259; PITFALLS.md Pitfall #4 + #7]`

### Pattern 2: backend.spec Skeleton

**What:** PyInstaller spec file living at `apps/backend/backend.spec`. Imports `certifi` to compute the data-files path at build time.

**When to use:** Always — this is the SIDE-03 implementation.

**Concrete sketch (canonical):**

```python
# apps/backend/backend.spec
# Build with:  pyinstaller --clean --noconfirm apps/backend/backend.spec
#
# Spec discoveries belong here, NOT in CLI flags, so the discovery process
# is captured in git history.

import certifi
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['backend.py'],
    pathex=['src'],  # so `from src.resources import ...` resolves at analysis time
    binaries=[],
    datas=[
        # certifi: bundle the CA bundle into the _MEIPASS/certifi/ directory.
        # SSL_CERT_FILE is set at runtime in backend.main() to point here.
        (certifi.where(), 'certifi'),
        # If/when Phase 2/3 needs to ship static assets (champion images, etc.),
        # add tuples here. Mutable runtime files (cache_data.json) belong in
        # platformdirs.user_cache_dir(), NOT in this list.
    ],
    hiddenimports=[
        # ----- Locked seed (CONTEXT D-08) -----
        # Flask-SocketIO + engineio dynamic async driver loader.
        # Without this: "Invalid async_mode specified" on first Socket.IO connect.
        'engineio.async_drivers.threading',
        # httpx's optional SOCKS proxy support — referenced conditionally by some deps.
        'httpx.socks',
        # websocket-client is used by league_client_websocket.py; collect every
        # submodule because it lazy-loads protocol handlers.
        *collect_submodules('websocket'),
        # requests sometimes needs these on trimmed bundles.
        'charset_normalizer',
        'urllib3',
        'certifi',
        # ----- Discovery list (uncomment as CI surfaces failures) -----
        # 'engineio.async_drivers',  # parent package, defensive
        # 'engineio',
        # 'socketio',
        # 'flask_socketio',
        # 'dns',  # if any dep pulls dnspython
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Supabase — never bundle (CONTEXT D-09). Eliminates credential leak surface
        # and trims ~3-5 MB from the bundle. supabase_repo.py imports STAY in source
        # for dev mode; the bundled .exe simply cannot import them.
        'supabase',
        'gotrue',
        'postgrest',
        'realtime',
        'storage3',
        'supabase_functions',
        'supabase_auth',
        # Locked async_mode='threading' — exclude the alternatives so PyInstaller
        # doesn't waste cycles trying to bundle them.
        'eventlet',
        'gevent',
        # Heavy stdlib leaves we never use:
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='backend-x86_64-pc-windows-msvc',  # Tauri externalBin target-triple
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # CRITICAL — Pitfall #2. Never flip to True.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # No black terminal flash on sidecar spawn.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

**`[CITED: .planning/research/STACK.md PyInstaller Spec Patterns; Pitfall #2 (UPX); Pitfall #5 (hidden imports)]`**

### Pattern 3: resources.py Skeleton

**What:** Single source of truth for path resolution. Three separate functions per CONTEXT-D-13 (planner may collapse if preferred — see Discretion).

**When to use:** Every path-resolution call site in Phase 1 and forward. Grep-enforced (CONTEXT-D-14).

**Concrete sketch (canonical):**

```python
# apps/backend/src/resources.py
"""
Path resolution helpers for both dev mode and PyInstaller --onefile bundles.

In a frozen bundle, sys._MEIPASS is the absolute path to the temp directory
the bootloader extracted resources into. In dev mode, __file__ anchors paths
to the source tree.

User-writable directories (cache, logs, persistent data) are NEVER inside
_MEIPASS — that directory is wiped on process exit and is per-launch.
They live under platformdirs.user_*_dir().
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import platformdirs

# Mutable placeholder — Phase 3 (TAURI-01) will swap this for the finalized
# Tauri identifier (e.g. "dev.till.lol-draft-analyzer"). Do NOT inline this
# string anywhere else; import it from here.
LOL_DRAFT_APP_NAME = "lol-draft-analyzer"


def _is_frozen() -> bool:
    """Return True if running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundled_resource(relative_path: str) -> Path:
    """
    Resolve a read-only resource that ships inside the bundle.

    :param relative_path: Path relative to the bundle root,
        e.g. "certifi/cacert.pem" or "static/champion_roles.json".
    :return: Absolute path. The file may or may not exist; the caller
        verifies existence.

    In dev mode, the base is the parent of this file's parent (i.e.
    apps/backend/), so `bundled_resource("cache_data.json")` resolves
    to apps/backend/cache_data.json.
    """
    if _is_frozen():
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # apps/backend/src/resources.py -> apps/backend/
        base = Path(__file__).resolve().parent.parent
    return base / relative_path


def user_cache_dir() -> Path:
    """
    Return the per-user cache directory, creating it if missing.

    Windows: %LOCALAPPDATA%\\lol-draft-analyzer\\Cache
    """
    p = Path(platformdirs.user_cache_dir(LOL_DRAFT_APP_NAME, ensure_exists=True))
    return p


def user_log_dir() -> Path:
    """
    Return the per-user log directory, creating it if missing.

    Windows: %LOCALAPPDATA%\\lol-draft-analyzer\\Logs
    """
    p = Path(platformdirs.user_log_dir(LOL_DRAFT_APP_NAME, ensure_exists=True))
    return p


def user_data_dir() -> Path:
    """
    Return the per-user persistent-data directory, creating it if missing.

    Windows: %APPDATA%\\lol-draft-analyzer
    """
    p = Path(platformdirs.user_data_dir(LOL_DRAFT_APP_NAME, ensure_exists=True))
    return p
```

**Notes:**

- `platformdirs.user_*_dir()` accepts `ensure_exists=True` since version 4.0 (verified). Before 4.0 you had to call `mkdir(parents=True, exist_ok=True)` manually. CONTEXT-D-18 pins `>= 4.0.0` precisely to enable this.
- The `_is_frozen()` predicate uses BOTH `sys.frozen` AND `hasattr(sys, '_MEIPASS')` because some packagers (cx_Freeze, py2exe) set `sys.frozen` without `_MEIPASS`. This is the canonical PyInstaller idiom per the official docs.
- `bundled_resource("certifi/cacert.pem")` returns `<_MEIPASS>/certifi/cacert.pem` in frozen mode (the spec's `datas=[(certifi.where(), 'certifi')]` tuple drops the bundle into the `certifi/` subdir of `_MEIPASS`).

`[CITED: PyInstaller runtime-information.md docs; platformdirs API 4.x docs]`

### Pattern 4: Probe-Then-Server Order (Critical Path)

**What:** The probe thread MUST be spawned before `socketio.run()` is called. Both happen on different threads. The probe makes HTTP requests to localhost; the server answers them.

**Why:** `socketio.run()` is a blocking call — it does not return until the server shuts down. If the probe runs on the main thread and `socketio.run` on a sub-thread, the sub-thread's Werkzeug threading server still works, BUT the natural-feeling code (probe inline, then `socketio.run`) deadlocks because the server hasn't started yet.

**Correct order (in `main()`):**

```python
probe = threading.Thread(target=_probe_health_then_signal_ready, ...)
probe.start()                # spawned but server not yet up
socketio.run(app, ...)       # blocks here; meanwhile probe polls and writes ready-file
```

**Wrong order (deadlocks):**

```python
_probe_health_then_signal_ready(port, ready_file, ...)   # blocks forever — no server
socketio.run(app, ...)                                   # never reached
```

**Wrong order (probe never sees the server):**

```python
socketio.run(app, ...)                                   # blocks here
probe = threading.Thread(target=_probe_health_then_signal_ready, ...)
probe.start()                                            # never reached
```

**Why daemon thread:** When the server gets `SIGTERM` / `CTRL_BREAK_EVENT` and `socketio.run` returns, the process should exit cleanly. A non-daemon probe thread that's already returned (after writing the ready-file) is fine — but during cold-start cancellation, daemon mode guarantees the process exits.

### Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Correct Approach |
|--------------|--------------|------------------|
| Calling `socketio.run(host='0.0.0.0', ...)` | Exposes the LCU bridge over LAN; leaks Riot auth tokens to any device on the user's Wi-Fi | `host='127.0.0.1'` always |
| Calling `socketio.run(app, debug=True, ...)` in the main path | Werkzeug auto-reloader spawns a subprocess that doubles every log line, breaks the ready-file protocol, and breaks PyInstaller `--onefile` | `debug=False` in `main()`; debug REPL is a separate developer escape hatch |
| Using `__file__`-relative paths after Phase 1 | In a frozen bundle, `__file__` is inside the ephemeral `_MEIPASS` temp dir — anything written there is wiped on process exit | All path resolution goes through `resources.bundled_resource()` (read-only) or `resources.user_*_dir()` (writable) |
| `sys.exit(1)` from inside a thread to fail-fast | Only kills the thread; main thread keeps running `socketio.run` | `os._exit(1)` from non-main threads |
| Probe checking only `socket.connect_ex((host, port))` returns 0 | A bound socket without an `accept()` loop returns 0 → false positive | Probe with `requests.get('/api/health')` — verifies the Flask threading server is in the accept loop |
| Writing the ready-file directly (no temp + rename) | A reader can see a half-written file → JSON parse error → crash | `_atomic_write_ready_file()` uses `os.replace` |
| Leaving `upx=True` in the spec | UPX-compressed PyInstaller stubs trigger AV false positives at ~3× the rate of uncompressed | `upx=False`, locked, CI grep-enforced |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-platform user data dirs | Custom `%APPDATA%` resolution via `os.environ` | `platformdirs.user_*_dir()` with `ensure_exists=True` | Handles Windows/macOS/Linux correctly; `%LOCALAPPDATA%` vs `%APPDATA%` distinction; respects roaming-profile rules; opinionated `Cache`/`Logs` subdirectory naming on Windows |
| TLS cert bundle | Vendored `cacert.pem` | `certifi` package + `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` env vars | `certifi` ships with Mozilla's root CA bundle; auto-updated via `pip install -U certifi`; vendoring means rotating roots manually |
| HTTP probe with retries | `socket.connect_ex` loop | `requests.get('/api/health')` with timeout | Verifies the server is in the `accept()` loop AND can serve requests, not just that the socket is bound |
| Atomic file write | Plain `open(path, 'w').write(data)` | `tmp.write_text(...)` + `os.replace(tmp, path)` | `os.replace` is atomic on both Windows (since Python 3.3) and POSIX; raw write is visible mid-write to a polling reader |
| Daily log rotation | Custom date-stamped filename + cleanup | `logging.handlers.TimedRotatingFileHandler(when="midnight", backupCount=14)` | Stdlib handler handles renames atomically and prunes by count automatically |
| Frozen-vs-dev mode detection | Checking for any single attribute | `getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")` | Other packagers (cx_Freeze, py2exe) set `sys.frozen` without `_MEIPASS`; checking both disambiguates |
| Argument parsing | `sys.argv` slicing | `argparse` (stdlib) | Free `--help`, type coercion (`type=int`, `type=Path`), error messages |
| Socket.IO test client | Hand-rolled WebSocket frames | `socketio.Client()` from `python-socketio[client]` | Server protocol negotiation is brittle; the official client matches versions |

**Key insight:** Phase 1 has many small custom-solution temptations (manual atomic write, custom probe, custom path detection). Each one has a one-line standard answer. The code is shorter when the standards are used — and won't break on the next Python release.

## Runtime State Inventory

> Phase 1 is a **greenfield-within-existing-codebase** phase: it ADDS code, doesn't rename, doesn't migrate data, and doesn't refactor existing modules. The Runtime State Inventory section is included for completeness but every category resolves to "nothing pre-existing to migrate."

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — Phase 1 introduces `user_cache_dir()` / `user_log_dir()` paths; nothing reads or writes them yet. The existing `cache_data.json` lives at `apps/backend/cache_data.json` (relative to source) and stays there for dev mode; CONTEXT-N-02 explicitly defers any cache-dir wiring to Phase 2. | None for Phase 1 |
| Live service config | None — no external services configured for Phase 1. Tauri / Job Object / port allocation all defer to Phase 3. | None |
| OS-registered state | None — no Windows Task Scheduler, no pm2, no systemd, no launchd. PyInstaller produces a single executable; no installation step in Phase 1 (installer is Phase 4). | None |
| Secrets / env vars | `.env` loading via `python-dotenv` continues to work in dev mode (`.env` lives at `apps/backend/.env`, untouched). The frozen `.exe` does NOT include `.env` (excluded from `datas=[...]`). `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` env vars are read only by the existing `supabase_client.py` which is now in `excludes=[...]` — bundle never imports it, so missing env vars in the bundle are not an error. New env var read at runtime: `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` (set BY `main()`, not consumed from outside). | None |
| Build artifacts / installed packages | None pre-existing. Phase 1 will create `dist/backend-x86_64-pc-windows-msvc.exe` and `build/` directories (PyInstaller artifacts) — both must be added to `.gitignore`. | Add `dist/`, `build/`, `*.spec.bak` to `.gitignore` (verify it's not already there). |

**Verification recipe for the planner:** none required for Phase 1 (no data migration, no rename). The acceptance test is the CI smoke test: it asserts the built `.exe` is functional, which is the only "runtime state" Phase 1 produces.

## Common Pitfalls

These map 1:1 to `.planning/research/PITFALLS.md` Pitfalls #2 (UPX), #3 (ready-file race), #5 (hidden imports), #6 (`__file__` vs `_MEIPASS`), and #7 (`certifi`).

### Pitfall 1: Probe Thread / Server Deadlock

**What goes wrong:** The probe runs on the main thread before `socketio.run` is called → probe loops forever waiting for a server that never starts. OR the probe runs after `socketio.run` (which blocks) → probe is never spawned.

**Why it happens:** Natural reading order is "set up the server, then probe it" — but `socketio.run` is a blocking call. Need to spawn the probe in a thread BEFORE the blocking call.

**How to avoid:** Always: `probe = threading.Thread(...); probe.start(); socketio.run(...)`. Probe thread is `daemon=True` so it doesn't survive server shutdown.

**Warning signs:** `python backend.py --port 0 --ready-file /tmp/foo` hangs forever; no ready-file appears; CI smoke test times out at 10 s.

### Pitfall 2: Ready-File Visible Mid-Write

**What goes wrong:** Reader (Tauri host or test) opens the ready-file just as Python is writing it → reads partial JSON → `json.loads` raises `JSONDecodeError`.

**Why it happens:** A naive `path.write_text(json.dumps(...))` is not atomic; on Windows it's two syscalls (create + write).

**How to avoid:** Write to `path + ".tmp"`, then `os.replace(tmp, path)`. `os.replace` is atomic on Windows (NTFS) and POSIX.

**Warning signs:** Intermittent CI flake where the test reads `{"port"` (truncated) and crashes; very rare in practice but happens on slow disks.

### Pitfall 3: UPX Compression Bumping AV False Positives

**What goes wrong:** PyInstaller default behavior tries `upx=True` if UPX is in PATH. UPX-compressed binaries match malware signatures used by Defender, Kaspersky, Avast, Norton. Result: mass quarantine on first install for non-technical users who can't recover.

**Why it happens:** UPX itself is benign, but ~most UPX-packed PE files in the wild are malware, so AV vendors flag them on prior-art heuristics.

**How to avoid:** `upx=False` in `backend.spec`. CI grep check in the workflow:

```bash
grep -E "^\s*upx\s*=\s*True" apps/backend/backend.spec && exit 1 || true
```

**Warning signs:** VirusTotal scan of `dist/backend.exe` returns >3 vendor flags; user reports "the installer disappeared after I downloaded it" (Defender quarantines silently on download).

### Pitfall 4: Missing Hidden Imports — Socket.IO Silently Broken in Frozen Mode

**What goes wrong:** PyInstaller statically analyzes imports; it can't see `importlib.import_module(f"engineio.async_drivers.{mode}")`. Result: `python backend.py` works fine; `dist/backend.exe` starts, accepts the first Socket.IO upgrade, fails with `Invalid async_mode specified`, then transport-close-loops.

**Why it happens:** engineio dynamically loads its driver module by name string at runtime; PyInstaller's bytecode walker doesn't know to include `engineio.async_drivers.threading`.

**How to avoid:** Hidden-imports list in `backend.spec` (see seed in §"backend.spec Skeleton"). The CI smoke test exercises a real Socket.IO round-trip against the BUILT `.exe` — this is the only test that catches missing hidden imports.

**Warning signs:** Test passes locally with `python backend.py`; fails only against `dist/backend.exe`; backend log shows `Invalid async_mode specified` exactly once then silence.

### Pitfall 5: Missing `certifi` Bundle — HTTPS Fails in Frozen Mode

**What goes wrong:** `requests.get("https://...")` in the bundled `.exe` raises `SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]`. Looks like a network problem; isn't.

**Why it happens:** `_ssl.c` checks Windows cert store first → not found → falls back to `certifi` → `cacert.pem` not on disk because PyInstaller didn't bundle it.

**How to avoid:** `datas=[(certifi.where(), 'certifi')]` in the spec; `os.environ.setdefault("SSL_CERT_FILE", str(bundled_resource("certifi/cacert.pem")))` at the top of `main()`.

**Warning signs:** First-run error banner "Cannot load champion data. Check internet connection." with the user's network actually working fine. CI smoke test: built `.exe` cannot `requests.get("https://example.com/")`.

### Pitfall 6: `__file__`-Relative Paths in Frozen Mode

**What goes wrong:** Code that worked in dev because `Path(__file__).parent` resolved to `apps/backend/` now resolves to `C:\Users\...\AppData\Local\Temp\_MEI12345\` — which is wiped on process exit. Cache writes vanish; logs vanish; user reports "data disappears between launches."

**Why it happens:** PyInstaller `--onefile` extracts everything to a per-launch temp directory. `__file__` points there.

**How to avoid:** All path resolution through `resources.bundled_resource()` (read-only) or `resources.user_*_dir()` (writable). CONTEXT-D-14 mandates a grep check after Phase 1 lands.

**Warning signs:** "Cache disappears after app restart" reports; `_MEI*` directories accumulating in `%TEMP%` (separate cleanup hook needed in Phase 3); tests pass with `python backend.py` but fail when run against `dist/backend.exe`.

### Pitfall 7: Werkzeug Reloader Subprocess Confuses PyInstaller

**What goes wrong:** `socketio.run(app, debug=True)` → Werkzeug spawns a child process for hot-reload → PyInstaller `--onefile` re-executes itself → infinite spawn loop.

**Why it happens:** Werkzeug's `use_reloader=True` (implied by `debug=True`) re-execs the parent with `WERKZEUG_RUN_MAIN=true`. With `--onefile`, that re-exec means re-extracting the bundle.

**How to avoid:** `debug=False` in `main()` always. Add a `--debug` CLI flag if a developer escape hatch is desired (Phase 2/3 — not Phase 1).

**Warning signs:** Multiple `backend.exe` processes in Task Manager after a single launch; `_MEI*` directories multiplying.

### Pitfall 8: Probe Targets Wrong Localhost Address

**What goes wrong:** Server binds `127.0.0.1`; probe targets `localhost`. On some Windows configurations (IPv6-first DNS), `localhost` resolves to `::1` (IPv6 loopback) and the probe never connects.

**Why it happens:** Windows hosts file or DNS resolves `localhost` differently from the explicit `127.0.0.1` literal.

**How to avoid:** Probe URL hardcoded as `http://127.0.0.1:{port}/api/health` — never `localhost`.

**Warning signs:** `connect timeout` in probe logs; CI flake on a runner with IPv6 quirks.

### Pitfall 9: python-socketio Client Version Mismatch

**What goes wrong:** Test client is `python-socketio` 4.x, server is 5.x → "The client is using an unsupported version of the Socket.IO or Engine.IO protocols" (issue #578).

**Why it happens:** Socket.IO protocol revisions are not always backwards compatible across major versions.

**How to avoid:** Pin the test client to the same minor as the server: `pip install "python-socketio[client]>=5.9.0,<6"`. The current server is `>=5.9.0` (per `requirements.txt`). Ideally pin to the same exact version installed in the venv.

**Warning signs:** Integration test connects and immediately disconnects; backend log shows `Invalid Socket.IO protocol version`.

`[CITED: python-socketio #578]`

## Code Examples

### Integration Test Skeleton (test_backend_cli.py)

```python
# apps/backend/test_backend_cli.py
"""
Integration tests for backend.py CLI lifecycle (SIDE-01, SIDE-02).

Spawns backend.py as a subprocess, exercises the ready-file contract,
verifies clean shutdown. The release workflow runs an additional copy
of these tests against dist/backend-*.exe.
"""

from __future__ import annotations

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


def _wait_for_ready_file(path: Path, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Atomic-write contract should prevent this; tolerate one retry.
                time.sleep(0.05)
                continue
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
    """SIDE-01 + SIDE-02: ready-file exists, contains JSON with matching pid."""
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
    finally:
        rc = _shutdown(proc)
        # rc == 0 on POSIX SIGTERM; -signal on POSIX kill; 1/255 on Windows
        # CTRL_BREAK_EVENT depending on Flask shutdown handler. Don't assert
        # exact value — assert non-hang.


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
```

**Notes on the test:**

- `_free_port()` binds-and-drops a socket to find a port (TOCTOU race window of microseconds; acceptable for tests). The CONTEXT mentions Phase 3 will use the same pattern from Rust.
- On Windows, `signal.CTRL_BREAK_EVENT` requires `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` at spawn time — without it, the signal is silently ignored. POSIX uses `SIGTERM` directly.
- `socketio.Client(...)` is the canonical test pattern for Socket.IO. Pin the package via `pip install "python-socketio[client]>=5.9.0,<6"` in the test extra to match the server's protocol.
- The release workflow runs an analogous test, but launches the BUILT `dist/backend-x86_64-pc-windows-msvc.exe` instead of `python backend.py` — same test logic, different binary. This is the test that catches missing hidden imports and missing `certifi` data.

`[CITED: PITFALLS.md verification recipe; python-socketio client docs]`

### CI Workflow YAML

```yaml
# .github/workflows/build-smoke.yml
# BUILD-05 partial — build smoke check on every push to main and on PRs.
# The full release workflow (BUILD-01..04, BUILD-06) is Phase 4.
name: Build Smoke

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build-and-smoke:
    runs-on: windows-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12.x"
          cache: pip
          cache-dependency-path: counterpick-app/apps/backend/requirements.txt

      - name: Install runtime + build deps
        working-directory: counterpick-app/apps/backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pyinstaller==6.19.0
          pip install "python-socketio[client]>=5.9.0,<6"

      # CONTEXT D-07: hard CI guard against UPX being re-enabled.
      - name: Enforce upx=False in spec
        working-directory: counterpick-app/apps/backend
        shell: bash
        run: |
          if grep -E '^\s*upx\s*=\s*True' backend.spec; then
            echo "::error file=backend.spec::upx=True is not allowed (Pitfall #2)"
            exit 1
          fi

      - name: Unit + dev-mode integration tests
        working-directory: counterpick-app/apps/backend
        run: pytest test_backend_cli.py -v

      - name: PyInstaller build
        working-directory: counterpick-app/apps/backend
        run: pyinstaller --clean --noconfirm backend.spec

      - name: Verify supabase NOT in bundle
        working-directory: counterpick-app/apps/backend
        shell: bash
        run: |
          # Spec-level excludes should make this empty.
          if strings dist/backend-x86_64-pc-windows-msvc.exe | grep -i supabase; then
            echo "::error::supabase strings leaked into the bundle"
            exit 1
          fi

      # SIDE-04: Smoke-test the BUILT .exe — Socket.IO round-trip + HTTPS GET.
      - name: Smoke test built .exe
        working-directory: counterpick-app/apps/backend
        shell: pwsh
        run: |
          $port = 5755  # arbitrary high port; can be 0 for OS-assigned
          $ready = Join-Path $env:RUNNER_TEMP "ready.json"
          if (Test-Path $ready) { Remove-Item $ready }
          $exe = "dist/backend-x86_64-pc-windows-msvc.exe"
          $proc = Start-Process -FilePath $exe `
            -ArgumentList @("--port", $port, "--ready-file", $ready) `
            -PassThru -NoNewWindow
          # Wait up to 10 s for ready-file
          $deadline = (Get-Date).AddSeconds(10)
          while ((Get-Date) -lt $deadline -and -not (Test-Path $ready)) {
            Start-Sleep -Milliseconds 100
          }
          if (-not (Test-Path $ready)) {
            Stop-Process -Id $proc.Id -Force
            throw "ready-file never appeared"
          }
          # Run the round-trip + HTTPS test
          python smoke_test_exe.py --port $port
          $exit = $LASTEXITCODE
          Stop-Process -Id $proc.Id -Force
          exit $exit

      # CONTEXT D-22: VirusTotal gated on secret being present.
      - name: VirusTotal scan (advisory)
        if: ${{ env.VT_API_KEY != '' }}
        env:
          VT_API_KEY: ${{ secrets.VT_API_KEY }}
        working-directory: counterpick-app/apps/backend
        run: python scripts/virustotal_check.py dist/backend-x86_64-pc-windows-msvc.exe --max-detections 3

      - name: Upload built .exe artifact
        uses: actions/upload-artifact@v4
        with:
          name: backend-exe
          path: counterpick-app/apps/backend/dist/backend-x86_64-pc-windows-msvc.exe
          retention-days: 7
```

**Companion script `smoke_test_exe.py`:**

```python
# apps/backend/smoke_test_exe.py
# Tiny CI helper: runs after the .exe is already spawned and the ready-file
# has appeared. Verifies Socket.IO + HTTPS, exits 0 on success / non-zero on failure.

import argparse
import sys

import requests
import socketio


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    # 1. Socket.IO round-trip (verifies engineio.async_drivers.threading hidden import).
    client = socketio.Client(logger=False, engineio_logger=False)
    try:
        client.connect(f"http://127.0.0.1:{args.port}", wait_timeout=5)
        assert client.connected, "Socket.IO did not connect"
        client.disconnect()
    except Exception as e:
        print(f"FAIL socket.io: {e}", file=sys.stderr)
        return 1

    # 2. HTTPS GET (verifies certifi bundling).
    try:
        r = requests.get("https://example.com/", timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"FAIL https: {e}", file=sys.stderr)
        return 1

    print("smoke OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Notes:**

- The CI smoke step targets `https://example.com/` for the HTTPS check — stable, benign, no dependency on infrastructure that doesn't exist yet (Phase 2 lands the real CDN URL).
- VirusTotal step is wired but gated on `VT_API_KEY` secret being present per CONTEXT-D-22; absent secret means warning, not failure. The `virustotal_check.py` companion script is a Phase 1 stretch goal — if not implemented in Phase 1, leave the step out and add in Phase 4 (the gate is non-blocking either way).
- `actions/setup-python@v5` `cache: pip` caches pip wheels keyed on `requirements.txt` contents — speeds up CI runs significantly.
- `timeout-minutes: 20` is generous; PyInstaller build on a cold runner takes ~3-5 minutes; warm runner ~1-2 minutes.

`[CITED: GitHub Actions docs setup-python@v5; CONTEXT D-16, D-17, D-22, D-23]`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `appdirs` | `platformdirs` | `appdirs` unmaintained since 2020; `platformdirs` is the official fork | Identical API; `ensure_exists=True` keyword added in 4.0 |
| `getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))` (one-liner) | `if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):` (two-attr check) | PyInstaller docs updated post-v6 to recommend the explicit check | Disambiguates from cx_Freeze / py2exe which also set `sys.frozen` |
| `socketio.run(app, debug=True)` for dev | `socketio.run(app, debug=False, allow_unsafe_werkzeug=True)` for production sidecar | Flask-SocketIO 5+ rejects production-mode Werkzeug without explicit opt-in | Required flag for desktop-localhost-only use |
| Eventlet / Gevent monkey-patching for Socket.IO | `async_mode='threading'` (default in Flask-SocketIO 5+ when neither installed) | Threading is adequate for single-user local; eventlet/gevent collide with PyInstaller bytecode analysis | Reliable PyInstaller bundle; ~2-10 concurrent clients fine |
| `requests-cache` | Hand-written `If-None-Match` / `If-Modified-Since` cache | Phase 2 concern, not Phase 1 — listed for context | Smaller bundle, no SQLite dep, fewer AV signatures |

**Deprecated/outdated:**
- `appdirs` package (use `platformdirs`)
- PyInstaller pre-5.3 (lacks proper console-control-signal handling on Windows onefile)
- Tauri v1 (EOL 2026; out of scope but worth flagging — `.planning/research/STACK.md` covers this)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The current `python-socketio` server version in the venv is `>= 5.9.0` (per `requirements.txt` lower bound) and the matching client is in the same major | Standard Stack / Pitfall 9 | If the actual installed version is older or newer than the test client, the integration test fails with "unsupported protocol version" — easy to detect, easy to fix by aligning versions in CI |
| A2 | `actions/setup-python@v5` provides Python 3.12.x with `cache: pip` keyed on `requirements.txt` | CI Workflow YAML | If keyed differently, CI runs cold every time — slower, not broken |
| A3 | `os.replace(tmp, path)` is atomic on Windows for cross-volume moves on the same drive | Pattern 1 / Pitfall 2 | If TMPDIR is on a different drive than the ready-file path, `os.replace` raises `OSError`. Mitigation: write tmp adjacent to the ready-file (`path + ".tmp"`, not `tempfile.NamedTemporaryFile`). Skeleton uses adjacent-tmp pattern. |
| A4 | The frozen-mode check `getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")` is sufficient for PyInstaller 6.19. Newer versions don't change this contract | Pattern 3 | If PyInstaller 7+ changes the convention, dev-mode and frozen-mode start diverging silently. Pinning PyInstaller to 6.19.0 (CONTEXT D-17) makes this irrelevant for v1. |
| A5 | The integration test running on `windows-latest` does NOT need real LCU (League Client) availability — it just exercises CLI / Socket.IO / HTTPS | Integration Test Skeleton | If `backend.py` import fails because LCU bridge raises during import, the test cannot even start. Verified by reading existing `backend.py` — LCU connection is lazy via `connect_to_league_client_websocket()` called from a Socket.IO handler, not at import time. SAFE. |
| A6 | `host="127.0.0.1"` (not `0.0.0.0`) does not break Tauri's spawn-and-discover protocol planned for Phase 3 | backend.py CLI Skeleton | Tauri spawns the sidecar with `--port` from a `127.0.0.1:0` allocation and connects to `127.0.0.1` — same loopback, same family. SAFE. |
| A7 | `engineio.async_drivers.threading` is the only async-driver hidden import needed when `async_mode='threading'` is explicitly set | backend.spec / Pitfall 4 | If engineio internals also import a sibling `engineio.async_drivers` package init, missing a transitive submodule causes runtime failure. The seed list includes `*collect_submodules('websocket')` defensively for `websocket-client`; consider adding `*collect_submodules('engineio.async_drivers')` if first CI run fails. CONTEXT-D-08 explicitly authorizes iterative expansion of the seed list. |

## Open Questions

1. **Should the integration test pin `python-socketio[client]` to a specific version, or to the same version as the server?**
   - What we know: Server is `python-socketio >= 5.9.0`. Client must match the major.
   - What's unclear: Whether to `pip install python-socketio[client]==X.Y.Z` (exact match) or `pip install "python-socketio[client]>=5.9.0,<6"` (band).
   - Recommendation: Use the band in `requirements.txt` for dev flexibility; in CI install the exact same version that the server uses by reading the resolved lockfile or by adding `python-socketio[client]` to `requirements.txt` (so pip resolves both server and client to the same version automatically). Cleanest: add `python-socketio[client]>=5.9.0,<6` to a new `[test]` extra in `pyproject.toml`.

2. **Should `--port 0` be allowed in dev mode (OS-assigned port)?**
   - What we know: CONTEXT D-01 says default is 5000 for native dev. Doesn't explicitly forbid `--port 0`.
   - What's unclear: With `--port 0`, the client doesn't know the actual port until it reads the ready-file (which has `"port": <actual>`). Dev workflow `python backend.py` (no args) defaults to 5000 and there's no ready-file.
   - Recommendation: Allow `--port 0`; document that `--port 0` ALWAYS requires `--ready-file`; integration test uses this combination. Native-dev workflow uses `--port 5000` (the default), which is what the existing frontend hardcodes.

3. **What's the right Python version pin notation in `actions/setup-python@v5`: `"3.12"` or `"3.12.x"`?**
   - What we know: CONTEXT D-16 says `"3.12.x"`.
   - What's unclear: Whether `"3.12"` (which `setup-python@v5` resolves to "latest 3.12.x") is preferable for getting security patches automatically.
   - Recommendation: Honor CONTEXT — `"3.12.x"`. Aligns with "pinning is cheap" (D-17).

4. **Is the `virustotal_check.py` script in Phase 1 scope or Phase 4?**
   - What we know: CONTEXT D-22 says "wired but advisory in Phase 1; hard-gate is Phase 4."
   - What's unclear: "Wired" could mean (a) the workflow step exists with no script (a no-op `echo`), or (b) the script exists and queries the VT API.
   - Recommendation: Phase 1 ships the workflow step gated on `VT_API_KEY`; if `VT_API_KEY` secret is not configured (the default state until release time), the step skips. Implementing the actual `virustotal_check.py` is fine in Phase 1 if cheap (one HTTP POST + status check), but not blocking — can defer to Phase 4. Planner picks.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12.x | CI smoke build, dev-mode test | Provided by `actions/setup-python@v5` on `windows-latest` | as set | — |
| pip | Install runtime + build deps | Bundled with Python | latest | — |
| PyInstaller 6.19.0 | Build `backend.exe` | Installed in CI step | 6.19.0 (pinned) | — |
| `windows-latest` GitHub runner | CI smoke test, future release builds | Available on free GitHub Actions tier | rolling (Win Server 2022) | None — Windows-only build is a CONTEXT lock (D-23) |
| WebView2 Runtime | Tauri (Phase 3) — not needed in Phase 1 | n/a | n/a | n/a |
| WiX Toolset v3 | `.msi` build (Phase 4) — not needed in Phase 1 | Auto-provisioned by Tauri at build time | n/a | n/a |
| UPX | Must NOT be in PATH on build machine | n/a | n/a | n/a — `upx=False` is the lock |
| `VT_API_KEY` GitHub secret | VirusTotal scan step | Optional; absent by default | n/a | Step skips silently with warning per CONTEXT D-22 |
| Network egress to `https://example.com/` | CI smoke test HTTPS verification | GitHub Actions runners have unrestricted outbound HTTPS | n/a | If example.com flakes, swap to `https://www.gstatic.com/generate_204` (returns 204; ~7 ms) |

**Missing dependencies with no fallback:**

- None — every Phase 1 dependency is either provided by the runner or pip-installable.

**Missing dependencies with fallback:**

- `VT_API_KEY` secret: absent → step skipped (advisory). This is intentional per CONTEXT D-22.

## Sources

### Primary (HIGH confidence)

- **PyInstaller 6.19.0 docs** — `https://pyinstaller.org/en/stable/runtime-information.html`, `https://pyinstaller.org/en/stable/spec-files.html` — release date confirmed 2026-02-14 via PyPI; `_MEIPASS` semantics; `frozen` attribute convention. `[VERIFIED: WebSearch 2026-04-14 + .planning/research/STACK.md cross-check]`
- **Flask-SocketIO #259** — `https://github.com/miguelgrinberg/Flask-SocketIO/issues/259` — canonical reference for "how to pack flask-socketio app with pyinstaller"; documents the `engineio.async_drivers.threading` hidden-import requirement. `[CITED: PITFALLS.md + STACK.md]`
- **python-socketio #633** — `https://github.com/miguelgrinberg/python-socketio/issues/633` — "Invalid async_mode specified" failure mode in PyInstaller bundles; pin async_mode + hidden-import the matching driver. `[CITED: PITFALLS.md]`
- **PyInstaller #7229** — `https://github.com/pyinstaller/pyinstaller/issues/7229` — `certifi` bundling regression and the `datas=[(certifi.where(), 'certifi')]` workaround. `[CITED: PITFALLS.md]`
- **python-socketio docs intro.rst** — `https://python-socketio.readthedocs.io/en/latest/intro.html` — server↔client version-compatibility chart; recommendation to pin same version both sides. `[VERIFIED: WebSearch 2026-04-14]`
- **platformdirs API docs** — `https://platformdirs.readthedocs.io/en/latest/api.html` — `user_cache_dir` / `user_log_dir` / `user_data_dir` signatures; `ensure_exists` keyword added in 4.0. `[VERIFIED: WebSearch 2026-04-14]`
- **Project research files** — `.planning/research/STACK.md`, `.planning/research/SUMMARY.md`, `.planning/research/PITFALLS.md` — all cited inline above. Confidence inherited from project-level research effort.
- **Project codebase maps** — `.planning/codebase/STACK.md`, `.planning/codebase/STRUCTURE.md`, `.planning/codebase/CONVENTIONS.md` — verified against actual `apps/backend/backend.py` and `apps/backend/requirements.txt`. `[VERIFIED via Read of source files]`

### Secondary (MEDIUM confidence)

- **GitHub Actions `setup-python@v5`** — pip cache behavior, version-pin syntax. `[VERIFIED: WebSearch + standard usage]`
- **`os.replace` atomicity on Windows** — Python 3.3+ docs confirm cross-platform atomic rename behavior on same volume. `[CITED: Python stdlib docs]`
- **`signal.CTRL_BREAK_EVENT` requires `CREATE_NEW_PROCESS_GROUP`** — Python `subprocess` docs + multiple StackOverflow confirmations. `[CITED: Python stdlib docs]`

### Tertiary (LOW confidence — flag for validation)

- **Exact `python-socketio` minor in repo at plan-freeze time** — `requirements.txt` says `>=5.9.0` (lower bound only). Run `pip install -r requirements.txt && pip show python-socketio` to read the resolved version, then pin the test client to it. `[ASSUMED]` until verified.
- **Whether `actions/setup-python@v5` `cache: pip` keys correctly when `cache-dependency-path` is a backend-relative path** — works in standard layouts; verify with first CI run. `[ASSUMED]`
- **Whether `https://example.com/` is the right HTTPS smoke target** — stable, benign, returns HTTP 200 with HTML body. Alternative `https://www.gstatic.com/generate_204` returns 204 (faster, no body). `[ASSUMED — either works]`

## Validation Architecture

> Skipped per `.planning/config.json` workflow.nyquist_validation = false.

## Security Domain

`security_enforcement` is not set in `.planning/config.json` — treating as enabled per default. Phase 1's security surface is narrow but real:

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth in Phase 1 (Tauri-localhost trust model arrives in Phase 3). |
| V3 Session Management | no | No sessions; localhost-only HTTP. |
| V4 Access Control | yes | `host="127.0.0.1"` enforces loopback-only — anything else exposes the LCU bridge over LAN. |
| V5 Input Validation | yes | `argparse` `type=int` / `type=Path` coerces CLI args; `--port` value should be sanity-checked (range 0-65535) before passing to `socketio.run`. |
| V6 Cryptography | yes | `certifi` bundling for TLS root CAs — never hand-roll cert validation. `SSL_CERT_FILE` env var is the standard override mechanism. |
| V12 Files & Resources | yes | Atomic ready-file write prevents partial-state reads; `os.replace` is the standard idiom. |

### Known Threat Patterns for Flask + PyInstaller Sidecar on Windows

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Backend bound to `0.0.0.0` instead of `127.0.0.1` → LAN-accessible LCU bridge leaks Riot auth tokens to other Wi-Fi devices | Information Disclosure | Hardcode `host="127.0.0.1"` in `socketio.run`; assert at startup if non-loopback bind requested. |
| `SUPABASE_SERVICE_ROLE_KEY` accidentally bundled into `backend.exe` (any user with a hex editor extracts it → full DB write access) | Tampering / Privilege Escalation | PyInstaller `excludes=['supabase', 'gotrue', ...]` (CONTEXT D-09) + CI grep check `strings dist/backend.exe | grep -i supabase` must return empty. |
| Werkzeug debug mode in production sidecar exposes the debugger PIN endpoint, allowing arbitrary code execution from any local browser | Elevation of Privilege | `debug=False` in `socketio.run`; lint check could enforce. |
| Ready-file written world-readable could leak the port to other local users | Information Disclosure | Low risk on per-user Windows install; `tmp_path` from pytest is in user-private dir. Phase 3 (Tauri) writes the ready-file to a Tauri-managed temp dir which inherits user-private ACLs. |
| TLS cert bundle (`certifi`) goes stale over years → expired root → CDN fetch fails → silent loss of users | Denial of Service (eventual) | Pin `certifi` in `requirements.txt` AND add a release-checklist item to `pip install -U certifi` every 6 months. Phase 4 release procedure tracks this. |

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version verified via PyPI search 2026-04-14; `.planning/research/STACK.md` is recent and authoritative.
- Architecture: HIGH — patterns derived from existing `backend.py` source (read directly), known PyInstaller idioms verified against official docs, ready-file/probe pattern lifted from `.planning/research/PITFALLS.md` Pitfall #4 mitigation.
- Pitfalls: HIGH — every pitfall traces to either an upstream issue tracker (Flask-SocketIO #259, python-socketio #633, PyInstaller #7229) or a verified Python stdlib semantic (`os.replace`, `signal.CTRL_BREAK_EVENT`).
- CI shape: MEDIUM-HIGH — workflow YAML follows standard `windows-latest` + `setup-python@v5` patterns; only flag is whether `cache-dependency-path` works exactly as written for the monorepo's backend-relative `requirements.txt`.

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (30 days; PyInstaller, Flask-SocketIO, python-socketio are all stable; platformdirs is stable). Re-verify if any of the four core packages release a new minor before plan-freeze.

---

*Phase 1: Sidecar Foundation — researched 2026-04-14. Five SIDE-* requirements covered. Ready for `/gsd-plan-phase 1`.*
